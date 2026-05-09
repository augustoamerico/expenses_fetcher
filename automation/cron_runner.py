#!/usr/bin/env python3
"""
Automated cron runner for expenses_fetcher.

This script is designed to run as a daily cron job. It:
1. Loads configuration from YAML
2. Filters to Nordigen-only accounts
3. Pulls transactions from each account
4. Handles auth expiration gracefully (skip and continue)
5. Pushes successful transactions to Google Sheets
6. Sends summary notifications via ntfy

Usage:
    python automation/cron_runner.py --config-file config/config.yaml

Environment variables:
    NTFY_TOPIC: ntfy.sh topic for notifications (required)
    NTFY_SERVER: ntfy server URL (optional, defaults to https://ntfy.sh)
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from random import randint
from typing import Dict, List, Any, Optional

import requests
import yaml

DEFAULT_PENDING_FILE = "data/pending_reauths.json"
REAUTH_EXPIRY_HOURS = 24

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.notifiers import NtfyNotifier
from src.infrastructure.bank_account_transactions_fetchers.exceptions import (
    NordigenAuthExpiredException,
)
from src.application.expenses_fetcher.expenses_fetcher import ExpensesFetcher
from src.service.configuration import configuration_parser as cfg_parser
from src.infrastructure.bank_account_transactions_fetchers.nordigen_token_provider import (
    NordigenTokenProvider,
)
from src.repository.google_sheet_repository import GoogleSheetRepository


log = logging.getLogger(__name__)

NORDIGEN_BASE_URL = "https://bankaccountdata.gocardless.com/api/v2"


def get_account_iban(account_id: str, access_token: str) -> Optional[str]:
    """
    Fetch IBAN for an account from Nordigen API.

    Args:
        account_id: Nordigen account UUID
        access_token: Valid Nordigen access token

    Returns:
        IBAN string or None if not available
    """
    try:
        response = requests.get(
            f"{NORDIGEN_BASE_URL}/accounts/{account_id}/details/",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            timeout=30,
        )
        if response.status_code == 200:
            iban = response.json().get("account", {}).get("iban")
            if iban:
                log.info(f"Got IBAN for account {account_id}: {iban[:4]}...{iban[-4:]}")
            return iban
    except requests.RequestException as e:
        log.error(f"Error fetching IBAN for account {account_id}: {e}")
    return None


def get_reauth_link(secret_id: str, secret_key: str, account_id: str) -> Optional[Dict[str, str]]:
    """
    Generate a bank re-authorization link for an expired Nordigen account.

    This creates a new agreement and requisition, returning the bank's OAuth URL
    and requisition ID for tracking.

    Args:
        secret_id: Nordigen API secret ID
        secret_key: Nordigen API secret key
        account_id: The Nordigen account UUID

    Returns:
        Dict with 'link' and 'requisition_id', or None if generation failed
    """
    try:
        # Step 1: Get access token
        token_response = requests.post(
            f"{NORDIGEN_BASE_URL}/token/new/",
            headers={"Content-Type": "application/json", "accept": "application/json"},
            data=json.dumps({"secret_id": secret_id, "secret_key": secret_key}),
            timeout=30,
        )
        if token_response.status_code != 200:
            log.error(f"Failed to get Nordigen token: {token_response.text}")
            return None

        access_token = token_response.json().get("access")
        if not access_token:
            log.error("No access token in Nordigen response")
            return None

        auth_headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

        # Step 2: Get institution_id from account details
        account_response = requests.get(
            f"{NORDIGEN_BASE_URL}/accounts/{account_id}/",
            headers=auth_headers,
            timeout=30,
        )
        if account_response.status_code != 200:
            log.error(f"Failed to get account details: {account_response.text}")
            return None

        institution_id = account_response.json().get("institution_id")
        if not institution_id:
            log.error("No institution_id in account details")
            return None

        log.info(f"Found institution_id: {institution_id} for account {account_id}")

        # Step 3: Create end-user agreement
        agreement_response = requests.post(
            f"{NORDIGEN_BASE_URL}/agreements/enduser/",
            headers=auth_headers,
            data=json.dumps({
                "institution_id": institution_id,
                "max_historical_days": "90",
                "access_valid_for_days": "90",
                "access_scope": ["balances", "details", "transactions"],
            }),
            timeout=30,
        )
        if agreement_response.status_code not in (200, 201):
            log.error(f"Failed to create agreement: {agreement_response.text}")
            return None

        agreement_id = agreement_response.json().get("id")
        if not agreement_id:
            log.error("No agreement ID in response")
            return None

        # Step 4: Create requisition with redirect to google.com
        reference = f"reauth-{randint(10000000, 99999999)}"
        requisition_response = requests.post(
            f"{NORDIGEN_BASE_URL}/requisitions/",
            headers=auth_headers,
            data=json.dumps({
                "redirect": "https://www.google.com",
                "institution_id": institution_id,
                "reference": reference,
                "agreement": agreement_id,
                "user_language": "EN",
            }),
            timeout=30,
        )
        if requisition_response.status_code not in (200, 201):
            log.error(f"Failed to create requisition: {requisition_response.text}")
            return None

        requisition_data = requisition_response.json()
        link = requisition_data.get("link")
        requisition_id = requisition_data.get("id")

        if not link or not requisition_id:
            log.error("No link or requisition_id in requisition response")
            return None

        log.info(f"Generated re-auth link for account {account_id}, requisition_id: {requisition_id}")
        return {"link": link, "requisition_id": requisition_id}

    except requests.RequestException as e:
        log.error(f"Request error generating re-auth link: {e}")
        return None
    except Exception as e:
        log.error(f"Unexpected error generating re-auth link: {e}")
        return None


def load_pending_reauths(file_path: str) -> Dict[str, Any]:
    """Load pending re-auths from JSON file."""
    if not os.path.exists(file_path):
        return {"pending": [], "history": []}

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            if "pending" not in data:
                data["pending"] = []
            if "history" not in data:
                data["history"] = []
            return data
    except (json.JSONDecodeError, IOError) as e:
        log.warning(f"Error loading pending reauths file: {e}")
        return {"pending": [], "history": []}


def save_pending_reauths(file_path: str, data: Dict[str, Any]) -> None:
    """Save pending re-auths to JSON file."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def add_pending_reauth(
    file_path: str,
    requisition_id: str,
    accounts: List[Dict[str, str]],
    secret_id: str,
    secret_key: str,
) -> None:
    """
    Add a pending re-auth entry to the JSON file.

    Args:
        file_path: Path to pending reauths JSON file
        requisition_id: Nordigen requisition ID
        accounts: List of account dicts with keys: account_name, old_account_id, iban
        secret_id: Nordigen secret ID
        secret_key: Nordigen secret key
    """
    data = load_pending_reauths(file_path)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=REAUTH_EXPIRY_HOURS)

    account_names = [a["account_name"] for a in accounts]

    data["pending"].append({
        "requisition_id": requisition_id,
        "accounts": accounts,
        "secret_id": secret_id,
        "secret_key": secret_key,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
    })

    save_pending_reauths(file_path, data)
    log.info(f"Added pending re-auth for {', '.join(account_names)}, expires at {expires_at.isoformat()}")


def setup_logging(log_dir: str = "/app/logs") -> None:
    """
    Configure logging to both stdout and rotating file.

    Args:
        log_dir: Directory for log files
    """
    os.makedirs(log_dir, exist_ok=True)

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers
    root_logger.handlers = []

    # Console handler (stdout - captured by docker logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # File handler with rotation (10MB max, keep 5 backups)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "cron_runner.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)


def load_config(config_path: str) -> Dict[str, Any]:
    """Load YAML configuration file."""
    with open(config_path, "r") as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def filter_nordigen_accounts(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filter configuration to only include Nordigen accounts.

    Args:
        config: Full configuration dictionary

    Returns:
        Modified config with only Nordigen accounts
    """
    if "accounts" not in config:
        return config

    filtered_accounts = {}
    for account_name, account_config in config["accounts"].items():
        account_type = account_config.get("type", "").lower().strip()
        if account_type == "nordigen-account":
            filtered_accounts[account_name] = account_config
            log.info(f"Including Nordigen account: {account_name}")
        else:
            log.debug(f"Skipping non-Nordigen account: {account_name} (type: {account_type})")

    config["accounts"] = filtered_accounts
    return config


def build_expense_fetcher(config: Dict[str, Any]) -> ExpensesFetcher:
    """
    Build ExpensesFetcher from configuration.

    This is a simplified version that doesn't require TTY password input.
    """
    if "expense_fetcher_options" in config:
        tmp_dir = config["expense_fetcher_options"].get("tmp_dir_path")
        if tmp_dir:
            os.makedirs(tmp_dir, exist_ok=True)
    else:
        tmp_dir = None

    # Build repositories
    repositories = {}
    if "repositories" in config:
        for repo_name, repo_config in config["repositories"].items():
            if repo_name == "googlesheet":
                repositories[repo_name] = GoogleSheetRepository(**repo_config)
            # Skip other repository types for automation

    if not repositories:
        raise ValueError("No valid repositories configured")

    # Build accounts
    accounts = {}
    if "accounts" in config:
        nordigen_token_provider = NordigenTokenProvider()
        for account_name, account_config in config["accounts"].items():
            try:
                account = cfg_parser.parse_account(
                    account_config,
                    account_name,
                    repositories.values(),
                    tmp_dir,
                    None,  # No password getter needed for Nordigen
                    nordigen_token_provider=nordigen_token_provider,
                )
                accounts[account_name] = account
            except Exception as e:
                log.error(f"Failed to initialize account {account_name}: {e}")
                raise

    # Transaction config
    transactions_cfg = {}
    if "transactions" in config:
        transactions_cfg["debt_description"] = config["transactions"].get("debt")
        transactions_cfg["income_description"] = config["transactions"].get("income")
        transactions_cfg["transfer_description"] = config["transactions"].get("transfer")
        transactions_cfg["investment_description"] = config["transactions"].get("investment")
        transactions_cfg["date_format"] = config["transactions"].get("date_format")

    return ExpensesFetcher(repositories, accounts, **transactions_cfg)


def _resolve_env_var(value: Optional[str]) -> Optional[str]:
    """Resolve environment variable syntax like ${VAR_NAME}."""
    if value and value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        return os.environ.get(env_var)
    return value


def _group_accounts_by_credentials(
    auth_expired: List[tuple],
) -> Dict[tuple, List[Dict[str, Any]]]:
    """
    Group expired accounts by (secret_id, secret_key) for shared requisitions.

    Returns:
        Dict mapping (secret_id, secret_key) -> list of account info dicts
    """
    groups: Dict[tuple, List[Dict[str, Any]]] = {}

    for account_name, account_config in auth_expired:
        secret_id = _resolve_env_var(account_config.get("secret_id"))
        secret_key = _resolve_env_var(account_config.get("secret_key"))
        account_id = account_config.get("account")

        if not all([secret_id, secret_key, account_id]):
            log.warning(f"Missing credentials for {account_name}, skipping")
            continue

        key = (secret_id, secret_key)
        if key not in groups:
            groups[key] = []

        groups[key].append({
            "account_name": account_name,
            "old_account_id": account_id,
            "config": account_config,
        })

    return groups


def send_summary_notification(
    notifier: NtfyNotifier,
    results: Dict[str, List],
    transaction_count: int,
    pending_file: str = DEFAULT_PENDING_FILE,
) -> None:
    """
    Send summary notification based on results.

    Args:
        notifier: NtfyNotifier instance
        results: Dict with "success", "auth_expired", and "errors" lists
                 auth_expired contains (account_name, account_config) tuples
        transaction_count: Number of transactions staged
        pending_file: Path to pending re-auths JSON file
    """
    success_count = len(results["success"])
    auth_count = len(results["auth_expired"])
    error_count = len(results["errors"])

    # Group expired accounts by credentials (same bank = same requisition)
    credential_groups = _group_accounts_by_credentials(results["auth_expired"])

    for (secret_id, secret_key), account_group in credential_groups.items():
        # Use first account to generate re-auth link (all share same institution)
        first_account = account_group[0]
        first_account_id = first_account["old_account_id"]
        account_names = [a["account_name"] for a in account_group]

        log.info(f"Generating re-auth link for group: {', '.join(account_names)}")
        reauth_result = get_reauth_link(secret_id, secret_key, first_account_id)

        if reauth_result:
            reauth_link = reauth_result["link"]
            requisition_id = reauth_result["requisition_id"]

            # Get access token for IBAN fetching
            token_response = requests.post(
                f"{NORDIGEN_BASE_URL}/token/new/",
                headers={"Content-Type": "application/json", "accept": "application/json"},
                data=json.dumps({"secret_id": secret_id, "secret_key": secret_key}),
                timeout=30,
            )
            access_token = None
            if token_response.status_code == 200:
                access_token = token_response.json().get("access")

            # Build accounts list with IBANs for pending entry
            pending_accounts = []
            for acc in account_group:
                iban = None
                if access_token:
                    iban = get_account_iban(acc["old_account_id"], access_token)

                pending_accounts.append({
                    "account_name": acc["account_name"],
                    "old_account_id": acc["old_account_id"],
                    "iban": iban,
                })

            # Save pending re-auth for polling
            add_pending_reauth(
                file_path=pending_file,
                requisition_id=requisition_id,
                accounts=pending_accounts,
                secret_id=secret_id,
                secret_key=secret_key,
            )

            # Send notification
            if len(account_names) == 1:
                title = f"Re-auth needed: {account_names[0]}"
            else:
                title = f"Re-auth needed: {len(account_names)} accounts"

            notifier.send(
                title=title,
                message=f"Tap to authorize: {', '.join(account_names)}",
                priority="high",
                tags=["warning", "link"],
                click=reauth_link,
            )
        else:
            for acc in account_group:
                notifier.send(
                    title=f"Re-auth needed: {acc['account_name']}",
                    message="Could not generate re-auth link. Check logs.",
                    priority="high",
                    tags=["warning"],
                )

    # Notify about accounts with missing credentials
    for account_name, account_config in results["auth_expired"]:
        secret_id = _resolve_env_var(account_config.get("secret_id"))
        secret_key = _resolve_env_var(account_config.get("secret_key"))
        account_id = account_config.get("account")
        if not all([secret_id, secret_key, account_id]):
            notifier.send(
                title=f"Re-auth needed: {account_name}",
                message="Missing credentials in config. Manual re-auth required.",
                priority="high",
                tags=["warning"],
            )

    # Send summary notification
    if auth_count > 0 or error_count > 0:
        # Partial success or failures
        title = "Sync partial" if success_count > 0 else "Sync FAILED"
        priority = "high" if auth_count > 0 else "urgent"
        tags = ["warning"] if auth_count > 0 else ["x"]

        lines = [f"{success_count} accounts OK, {transaction_count} transactions"]
        if auth_count:
            auth_names = [name for name, _ in results["auth_expired"]]
            lines.append(f"{auth_count} need re-auth: {', '.join(auth_names)}")
        if error_count:
            error_names = [e[0] for e in results["errors"]]
            lines.append(f"{error_count} errors: {', '.join(error_names)}")

        notifier.send(title=title, message="\n".join(lines), priority=priority, tags=tags)
    else:
        # All good
        notifier.send(
            title="Daily sync complete",
            message=f"{success_count} accounts, {transaction_count} transactions",
            priority="default",
            tags=["white_check_mark"],
        )


def run_automation(
    config_path: str,
    notifier: NtfyNotifier,
    pending_file: str = DEFAULT_PENDING_FILE,
) -> bool:
    """
    Main automation entry point.

    Args:
        config_path: Path to YAML configuration file
        notifier: NtfyNotifier instance for sending notifications
        pending_file: Path to pending re-auths JSON file

    Returns:
        True if all accounts succeeded, False otherwise
    """
    log.info(f"Starting automated sync at {datetime.now().isoformat()}")

    results = {
        "success": [],
        "auth_expired": [],  # List of (account_name, account_config) tuples
        "errors": [],
    }

    try:
        # Load and filter config
        config = load_config(config_path)
        config = filter_nordigen_accounts(config)

        if not config.get("accounts"):
            log.warning("No Nordigen accounts found in configuration")
            notifier.send(
                title="Sync skipped",
                message="No Nordigen accounts configured",
                priority="low",
                tags=["information_source"],
            )
            return True

        # Keep reference to account configs for re-auth link generation
        account_configs = config.get("accounts", {})

        # Build fetcher
        expense_fetcher = build_expense_fetcher(config)

        # Pull from each account
        for account_name in list(expense_fetcher.accounts.keys()):
            log.info(f"Processing account: {account_name}")
            try:
                expense_fetcher.pull_transactions(account_name=account_name, apply_categories=True)
                results["success"].append(account_name)
                log.info(f"Successfully pulled from {account_name}")
            except NordigenAuthExpiredException as e:
                log.warning(f"Auth expired for {account_name}: {e}")
                # Store account config for re-auth link generation
                results["auth_expired"].append((account_name, account_configs.get(account_name, {})))
            except Exception as e:
                log.error(f"Error pulling from {account_name}: {e}", exc_info=True)
                results["errors"].append((account_name, str(e)))

        # Sort transactions
        if expense_fetcher.staged_transactions:
            expense_fetcher.sort_transactions()

        transaction_count = len(expense_fetcher.staged_transactions)
        log.info(f"Total transactions staged: {transaction_count}")

        # Push to Google Sheets
        if transaction_count > 0:
            try:
                expense_fetcher.push_transactions()
                log.info("Successfully pushed transactions to Google Sheets")
            except Exception as e:
                log.error(f"Failed to push to Google Sheets: {e}", exc_info=True)
                notifier.send(
                    title="Sync FAILED - Sheets error",
                    message=f"Could not push {transaction_count} transactions: {e}",
                    priority="urgent",
                    tags=["x", "rotating_light"],
                )
                return False

        # Send summary notification
        send_summary_notification(notifier, results, transaction_count, pending_file)

        # Close connections
        expense_fetcher.close_all_connections()

        log.info("Automated sync completed")
        return len(results["auth_expired"]) == 0 and len(results["errors"]) == 0

    except Exception as e:
        log.error(f"Unexpected error during automation: {e}", exc_info=True)
        notifier.send(
            title="Sync FAILED - unexpected error",
            message=f"Check logs: {e}",
            priority="urgent",
            tags=["x", "rotating_light"],
        )
        return False


def main():
    parser = argparse.ArgumentParser(description="Automated expenses fetcher cron runner")
    parser.add_argument(
        "--config-file",
        dest="config_file",
        required=True,
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--log-dir",
        dest="log_dir",
        default="/app/logs",
        help="Directory for log files (default: /app/logs)",
    )
    parser.add_argument(
        "--pending-file",
        dest="pending_file",
        default=DEFAULT_PENDING_FILE,
        help=f"Path to pending re-auths JSON file (default: {DEFAULT_PENDING_FILE})",
    )
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_dir)

    # Get ntfy configuration from environment
    ntfy_topic = os.environ.get("NTFY_TOPIC")
    if not ntfy_topic:
        log.error("NTFY_TOPIC environment variable is required")
        sys.exit(1)

    ntfy_server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
    notifier = NtfyNotifier(topic=ntfy_topic, server=ntfy_server)

    # Run automation
    success = run_automation(args.config_file, notifier, args.pending_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
