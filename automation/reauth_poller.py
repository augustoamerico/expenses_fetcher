#!/usr/bin/env python3
"""
Re-auth poller for Nordigen accounts.

This script runs periodically (e.g., every 30 min via cron) to check if
pending re-authorizations have been completed. When completed:
- If account ID changed: update config file with sed, record in history
- If account ID same: do nothing
- Send notification with result

Pending re-auths are stored in a JSON file and expire after 24 hours.
History of account ID replacements is kept for 7 days.

Usage:
    python automation/reauth_poller.py --config-file config/accounts_cfg.yaml

Cron example (every 30 min):
    */30 * * * * cd /path/to/expenses_fetcher && python automation/reauth_poller.py --config-file config/accounts_cfg.yaml
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

import requests

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.notifiers import NtfyNotifier

log = logging.getLogger(__name__)

NORDIGEN_BASE_URL = "https://bankaccountdata.gocardless.com/api/v2"
DEFAULT_PENDING_FILE = "data/pending_reauths.json"
REAUTH_EXPIRY_HOURS = 24
HISTORY_RETENTION_DAYS = 180  # ~6 months, covers 2 re-auth cycles (90 days each)


def setup_logging() -> None:
    """Configure logging to stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def load_pending_reauths(file_path: str) -> Dict[str, Any]:
    """Load pending re-auths from JSON file."""
    if not os.path.exists(file_path):
        return {"pending": [], "history": []}

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            # Ensure both keys exist
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


def cleanup_old_history(data: Dict[str, Any]) -> None:
    """Remove history entries older than HISTORY_RETENTION_DAYS."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=HISTORY_RETENTION_DAYS)

    original_count = len(data.get("history", []))
    data["history"] = [
        entry for entry in data.get("history", [])
        if datetime.fromisoformat(entry["replaced_at"].replace("Z", "+00:00")) > cutoff
    ]
    removed = original_count - len(data["history"])
    if removed > 0:
        log.info(f"Cleaned up {removed} old history entries")


def add_to_history(
    data: Dict[str, Any],
    account_name: str,
    old_account_id: str,
    new_account_id: str,
) -> None:
    """Add a replacement entry to history."""
    now = datetime.now(timezone.utc)
    data["history"].append({
        "account_name": account_name,
        "old_account_id": old_account_id,
        "new_account_id": new_account_id,
        "replaced_at": now.isoformat().replace("+00:00", "Z"),
    })


def get_nordigen_token(secret_id: str, secret_key: str) -> Optional[str]:
    """Get a fresh Nordigen access token."""
    try:
        response = requests.post(
            f"{NORDIGEN_BASE_URL}/token/new/",
            headers={"Content-Type": "application/json", "accept": "application/json"},
            data=json.dumps({"secret_id": secret_id, "secret_key": secret_key}),
            timeout=30,
        )
        if response.status_code == 200:
            return response.json().get("access")
    except requests.RequestException as e:
        log.error(f"Error getting Nordigen token: {e}")
    return None


def get_requisition_status(requisition_id: str, access_token: str) -> Optional[Dict]:
    """Fetch requisition details from Nordigen API."""
    try:
        response = requests.get(
            f"{NORDIGEN_BASE_URL}/requisitions/{requisition_id}/",
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
    except requests.RequestException as e:
        log.error(f"Error fetching requisition {requisition_id}: {e}")
    return None


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
            return response.json().get("account", {}).get("iban")
    except requests.RequestException as e:
        log.error(f"Error fetching IBAN for account {account_id}: {e}")
    return None


def update_config_with_sed(config_path: str, old_account_id: str, new_account_id: str) -> bool:
    """Update account ID in config file using sed."""
    try:
        # Use sed to replace the old account ID with the new one
        if sys.platform == "darwin":
            # macOS sed requires empty string for -i
            cmd = ["sed", "-i", "", f"s/{old_account_id}/{new_account_id}/g", config_path]
        else:
            # Linux sed
            cmd = ["sed", "-i", f"s/{old_account_id}/{new_account_id}/g", config_path]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            log.info(f"Updated config: {old_account_id} -> {new_account_id}")
            return True
        else:
            log.error(f"sed failed: {result.stderr}")
            return False

    except Exception as e:
        log.error(f"Error updating config with sed: {e}")
        return False


def _match_accounts_by_iban(
    old_accounts: List[Dict[str, Any]],
    new_account_ids: List[str],
    access_token: str,
) -> Dict[str, str]:
    """
    Match old accounts to new account IDs using IBAN.

    Args:
        old_accounts: List of dicts with account_name, old_account_id, iban
        new_account_ids: List of new account IDs from requisition
        access_token: Nordigen access token

    Returns:
        Dict mapping old_account_id -> new_account_id
    """
    matches = {}

    # Build IBAN -> new_account_id map
    new_iban_map = {}
    for new_id in new_account_ids:
        iban = get_account_iban(new_id, access_token)
        if iban:
            new_iban_map[iban] = new_id
            log.info(f"New account {new_id} has IBAN {iban[:4]}...{iban[-4:]}")

    # Match old accounts by IBAN
    for old_acc in old_accounts:
        old_id = old_acc["old_account_id"]
        old_iban = old_acc.get("iban")

        if old_id in new_account_ids:
            # ID unchanged
            matches[old_id] = old_id
        elif old_iban and old_iban in new_iban_map:
            # Matched by IBAN
            matches[old_id] = new_iban_map[old_iban]
            log.info(f"Matched {old_acc['account_name']} by IBAN: {old_id} -> {new_iban_map[old_iban]}")
        elif len(old_accounts) == 1 and len(new_account_ids) == 1:
            # Single account, no IBAN needed
            matches[old_id] = new_account_ids[0]
            log.info(f"Single account match: {old_id} -> {new_account_ids[0]}")

    return matches


def _get_account_names(item: Dict[str, Any]) -> str:
    """Get display string for account names in a pending item."""
    if "accounts" in item:
        return ", ".join(a["account_name"] for a in item["accounts"])
    return item.get("account_name", "unknown")


def process_pending_reauths(
    pending_file: str,
    config_path: str,
    notifier: Optional[NtfyNotifier],
) -> None:
    """Process all pending re-authorizations."""
    data = load_pending_reauths(pending_file)
    cleanup_old_history(data)

    pending = data.get("pending", [])
    if not pending:
        log.info("No pending re-auths to process")
        save_pending_reauths(pending_file, data)
        return

    log.info(f"Processing {len(pending)} pending re-auth(s)")
    now = datetime.now(timezone.utc)
    still_pending = []

    for item in pending:
        requisition_id = item.get("requisition_id")
        secret_id = item.get("secret_id")
        secret_key = item.get("secret_key")
        expires_at_str = item.get("expires_at")

        # Support both old (single account) and new (multi-account) format
        if "accounts" in item:
            old_accounts = item["accounts"]
        else:
            # Legacy format
            old_accounts = [{
                "account_name": item.get("account_name"),
                "old_account_id": item.get("old_account_id"),
                "iban": None,
            }]

        account_names_str = _get_account_names(item)

        if not all([requisition_id, secret_id, secret_key, expires_at_str, old_accounts]):
            log.warning(f"Skipping incomplete pending reauth entry: {item}")
            continue

        # Check expiry
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        if now > expires_at:
            log.warning(f"Re-auth for {account_names_str} expired (started > 24h ago)")
            if notifier:
                notifier.send(
                    title=f"Re-auth expired: {account_names_str}",
                    message="Re-auth was not completed within 24 hours. Please retry.",
                    priority="high",
                    tags=["warning"],
                )
            continue

        # Get token
        access_token = get_nordigen_token(secret_id, secret_key)
        if not access_token:
            log.error(f"Could not get token for {account_names_str}, will retry later")
            still_pending.append(item)
            continue

        # Get requisition status
        requisition = get_requisition_status(requisition_id, access_token)
        if not requisition:
            log.error(f"Could not fetch requisition for {account_names_str}, will retry later")
            still_pending.append(item)
            continue

        status = requisition.get("status")
        new_account_ids = requisition.get("accounts", [])
        log.info(f"Requisition {requisition_id} status: {status}, accounts: {new_account_ids}")

        if status == "LN":  # Linked
            if not new_account_ids:
                log.warning(f"Requisition completed but no accounts returned for {account_names_str}")
                if notifier:
                    notifier.send(
                        title=f"Re-auth issue: {account_names_str}",
                        message="Auth completed but no accounts returned. Check manually.",
                        priority="high",
                        tags=["warning"],
                    )
                continue

            # Match old -> new by IBAN
            matches = _match_accounts_by_iban(old_accounts, new_account_ids, access_token)

            updated = []
            unchanged = []
            unmatched = []

            for old_acc in old_accounts:
                old_id = old_acc["old_account_id"]
                acc_name = old_acc["account_name"]
                new_id = matches.get(old_id)

                if not new_id:
                    unmatched.append(acc_name)
                elif old_id == new_id:
                    unchanged.append(acc_name)
                else:
                    if update_config_with_sed(config_path, old_id, new_id):
                        add_to_history(data, acc_name, old_id, new_id)
                        updated.append(acc_name)
                    else:
                        unmatched.append(acc_name)

            # Send notifications
            if updated and notifier:
                notifier.send(
                    title=f"Re-auth complete: {', '.join(updated)}",
                    message="Config updated with new account IDs.",
                    priority="default",
                    tags=["white_check_mark"],
                )
            if unchanged and notifier:
                notifier.send(
                    title=f"Re-auth complete: {', '.join(unchanged)}",
                    message="Account IDs unchanged. Sync should work now.",
                    priority="default",
                    tags=["white_check_mark"],
                )
            if unmatched and notifier:
                notifier.send(
                    title=f"Re-auth issue: {', '.join(unmatched)}",
                    message="Could not match accounts. Check manually.",
                    priority="high",
                    tags=["warning"],
                )

        elif status == "EX":  # Expired
            log.warning(f"Requisition expired for {account_names_str}")
            if notifier:
                notifier.send(
                    title=f"Re-auth failed: {account_names_str}",
                    message="Requisition expired. Please retry re-auth.",
                    priority="high",
                    tags=["x"],
                )

        elif status in ("CR", "GC", "UA"):  # In progress
            log.info(f"Re-auth still in progress for {account_names_str} (status: {status})")
            still_pending.append(item)

        else:
            log.warning(f"Unknown requisition status '{status}' for {account_names_str}")
            still_pending.append(item)

    data["pending"] = still_pending
    save_pending_reauths(pending_file, data)
    log.info(f"Remaining pending re-auths: {len(still_pending)}")


def main():
    parser = argparse.ArgumentParser(description="Re-auth poller for Nordigen accounts")
    parser.add_argument(
        "--config-file",
        dest="config_file",
        required=True,
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--pending-file",
        dest="pending_file",
        default=DEFAULT_PENDING_FILE,
        help=f"Path to pending re-auths JSON file (default: {DEFAULT_PENDING_FILE})",
    )
    args = parser.parse_args()

    setup_logging()

    # Get ntfy configuration from environment
    ntfy_topic = os.environ.get("NTFY_TOPIC")
    notifier = None
    if ntfy_topic:
        ntfy_server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
        notifier = NtfyNotifier(topic=ntfy_topic, server=ntfy_server)
    else:
        log.warning("NTFY_TOPIC not set, notifications disabled")

    process_pending_reauths(
        pending_file=args.pending_file,
        config_path=args.config_file,
        notifier=notifier,
    )


if __name__ == "__main__":
    main()
