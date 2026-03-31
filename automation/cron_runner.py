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
from datetime import datetime
from logging.handlers import RotatingFileHandler
from random import randint
from typing import Dict, List, Any, Optional

import requests
import yaml

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


def get_reauth_link(secret_id: str, secret_key: str, account_id: str) -> Optional[str]:
    """
    Generate a bank re-authorization link for an expired Nordigen account.

    This creates a new agreement and requisition, returning the bank's OAuth URL.
    The redirect is set to google.com since we don't need the callback -
    the account ID typically stays the same after re-auth.

    Args:
        secret_id: Nordigen API secret ID
        secret_key: Nordigen API secret key
        account_id: The Nordigen account UUID

    Returns:
        The bank OAuth URL, or None if generation failed
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

        link = requisition_response.json().get("link")
        if not link:
            log.error("No link in requisition response")
            return None

        log.info(f"Generated re-auth link for account {account_id}")
        return link

    except requests.RequestException as e:
        log.error(f"Request error generating re-auth link: {e}")
        return None
    except Exception as e:
        log.error(f"Unexpected error generating re-auth link: {e}")
        return None


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


def send_summary_notification(
    notifier: NtfyNotifier,
    results: Dict[str, List],
    transaction_count: int,
) -> None:
    """
    Send summary notification based on results.

    Args:
        notifier: NtfyNotifier instance
        results: Dict with "success", "auth_expired", and "errors" lists
                 auth_expired contains (account_name, account_config) tuples
        transaction_count: Number of transactions staged
    """
    success_count = len(results["success"])
    auth_count = len(results["auth_expired"])
    error_count = len(results["errors"])

    # Send individual re-auth notifications with bank links
    for account_name, account_config in results["auth_expired"]:
        secret_id = account_config.get("secret_id")
        secret_key = account_config.get("secret_key")
        account_id = account_config.get("account")

        # Resolve environment variables if needed (e.g., ${NORDIGEN_SECRET_ID})
        if secret_id and secret_id.startswith("${") and secret_id.endswith("}"):
            env_var = secret_id[2:-1]
            secret_id = os.environ.get(env_var)
        if secret_key and secret_key.startswith("${") and secret_key.endswith("}"):
            env_var = secret_key[2:-1]
            secret_key = os.environ.get(env_var)

        if secret_id and secret_key and account_id:
            log.info(f"Generating re-auth link for {account_name}")
            reauth_link = get_reauth_link(secret_id, secret_key, account_id)

            if reauth_link:
                notifier.send(
                    title=f"Re-auth needed: {account_name}",
                    message=f"Tap to authorize:\n{reauth_link}",
                    priority="high",
                    tags=["warning", "link"],
                )
            else:
                notifier.send(
                    title=f"Re-auth needed: {account_name}",
                    message="Could not generate re-auth link. Check logs.",
                    priority="high",
                    tags=["warning"],
                )
        else:
            log.warning(f"Missing credentials for {account_name}, cannot generate re-auth link")
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


def run_automation(config_path: str, notifier: NtfyNotifier) -> bool:
    """
    Main automation entry point.

    Args:
        config_path: Path to YAML configuration file
        notifier: NtfyNotifier instance for sending notifications

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
        send_summary_notification(notifier, results, transaction_count)

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
    success = run_automation(args.config_file, notifier)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
