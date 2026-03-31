# Simple local web wizard for Nordigen/GoCardless onboarding
# Run: python tools/nordigen_onboarding_web/app.py --config-file config/your.yaml --port 8787

import argparse
import os
import sys
import json
import logging
import tempfile
from datetime import datetime
from urllib.parse import urlencode

import requests
import yaml
from flask import Flask, request, jsonify, send_from_directory, redirect

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.repository.google_sheet_repository import GoogleSheetRepository
from src.infrastructure.bank_account_transactions_fetchers.xlsx_transactions_fetcher import XlsxTransactionsFetcher

# Constants
BASE_URL = "https://bankaccountdata.gocardless.com/api/v2"
REDIRECT_PATH = "/callback"

app = Flask(__name__, static_folder="static", static_url_path="/static")


class WizardState:
    def __init__(self):
        self.secret_id = None
        self.secret_key = None
        self.access_token = None
        self.config_file = None
        self.redirect_base = None
        self.country = "pt"
        # Keep last created agreements and requisitions
        self.agreements = []
        self.requisitions = []
        self.institutions_cache = []


state = WizardState()


def load_config():
    if not state.config_file:
        raise ValueError("Wizard not initialized with config_file")
    with open(state.config_file, "r") as f:
        return yaml.safe_load(f) or {}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/state", methods=["GET"])
def api_state():
    """Expose initial server-side state for prefilling inputs in the UI."""
    return jsonify({
        "config_file": state.config_file,
        "country": state.country,
    })


@app.route("/api/init", methods=["POST"])
def api_init():
    data = request.json or {}
    state.config_file = data.get("config_file")
    state.country = data.get("country", "pt")
    if not state.config_file:
        return jsonify({"error": "config_file required"}), 400
    return jsonify({"ok": True})


@app.route("/api/config/nordigen_accounts", methods=["GET"])
def api_config_nordigen_accounts():
    if not state.config_file:
        return jsonify({"error": "Wizard not initialized with config_file"}), 400

    config = load_config()
    accounts = config.get("accounts", {}) or {}
    nordigen_accounts = []

    for name, account in accounts.items():
        if account.get("type") != "nordigen-account":
            continue
        nordigen_accounts.append(
            {
                "name": name,
                "account": account.get("account"),
            }
        )

    return jsonify(nordigen_accounts)


@app.route("/api/credentials", methods=["POST"])
def api_credentials():
    data = request.json or {}
    state.secret_id = data.get("secret_id")
    state.secret_key = data.get("secret_key")
    if not state.secret_id or not state.secret_key:
        return jsonify({"error": "Missing credentials"}), 400
    return jsonify({"ok": True})


@app.route("/api/token", methods=["POST"])
def api_token():
    if not state.secret_id or not state.secret_key:
        return jsonify({"error": "Set credentials first"}), 400
    payload = {
        "secret_id": state.secret_id,
        "secret_key": state.secret_key,
    }
    r = requests.post(f"{BASE_URL}/token/new/", headers={"Content-Type": "application/json", "accept": "application/json"}, data=json.dumps(payload))
    if r.status_code != 200:
        return jsonify({"error": r.text}), 400
    response_parsed = r.json()
    access = response_parsed.get("access")
    if not access:
        return jsonify({"error": "No access token returned"}), 400
    state.access_token = access
    return jsonify({"ok": True})


@app.route("/api/institutions", methods=["GET"])
def api_institutions():
    if not state.access_token:
        return jsonify({"error": "Get token first"}), 400
    country = request.args.get("country", state.country)
    r = requests.get(
        f"{BASE_URL}/institutions/?country={country}",
        headers={"accept": "application/json", "Authorization": f"Bearer {state.access_token}"},
    )
    if r.status_code != 200:
        return jsonify({"error": r.text}), 400
    state.institutions_cache = r.json()
    return jsonify(state.institutions_cache)


@app.route("/api/agreements", methods=["POST"])
def api_agreements():
    if not state.access_token:
        return jsonify({"error": "Get token first"}), 400
    data = request.json or {}
    institutions = data.get("institutions", [])
    max_historical_days = data.get("max_historical_days", 90)
    access_valid_for_days = data.get("access_valid_for_days", 90)
    access_scope = data.get("access_scope", ["balances", "details", "transactions"])

    created = []
    for inst in institutions:
        r = requests.post(
            f"{BASE_URL}/agreements/enduser/",
            headers={
                "accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {state.access_token}",
            },
            data=json.dumps(
                {
                    "institution_id": inst,
                    "max_historical_days": str(max_historical_days),
                    "access_valid_for_days": str(access_valid_for_days),
                    "access_scope": access_scope,
                }
            ),
        )
        if r.status_code != 201 and r.status_code != 200:
            return jsonify({"error": r.text}), 400
        created.append(r.json())
    state.agreements = created
    return jsonify(created)


@app.route("/api/requisitions", methods=["POST"])
def api_requisitions():
    if not state.access_token:
        return jsonify({"error": "Get token first"}), 400
    data = request.json or {}
    institutions = data.get("institutions", [])
    redirect_base = data.get("redirect_base")
    if not redirect_base:
        return jsonify({"error": "redirect_base required (e.g., http://localhost:8787)"}), 400
    state.redirect_base = redirect_base.rstrip("/")

    agreements_map = {a["institution_id"]: a["id"] for a in state.agreements}

    created = []
    for inst in institutions:
        agreement_id = agreements_map.get(inst)
        if not agreement_id:
            return jsonify({"error": f"No agreement found for institution {inst}"}), 400
        reference = f"ref-{int(datetime.now().timestamp())}-{inst[:6]}"
        payload = {
            "redirect": f"{state.redirect_base}{REDIRECT_PATH}",
            "institution_id": inst,
            "reference": reference,
            "agreement": agreement_id,
            "user_language": "EN",
        }
        r = requests.post(
            f"{BASE_URL}/requisitions/",
            headers={
                "accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {state.access_token}",
            },
            data=json.dumps(payload),
        )
        if r.status_code not in (200, 201):
            return jsonify({"error": r.text}), 400
        created.append(r.json())
    state.requisitions = created
    return jsonify(created)


@app.route("/callback", methods=["GET"])
def callback():
    # Nordigen will redirect here with query params, e.g., ?ref=... or status
    # We simply redirect to UI to continue the flow
    return redirect("/static/index.html#consent_done")


@app.route("/api/requisitions/<req_id>", methods=["GET"])
def api_requisition_detail(req_id):
    if not state.access_token:
        return jsonify({"error": "Get token first"}), 400
    r = requests.get(
        f"{BASE_URL}/requisitions/{req_id}/",
        headers={"accept": "application/json", "Authorization": f"Bearer {state.access_token}"},
    )
    if r.status_code != 200:
        return jsonify({"error": r.text}), 400
    return jsonify(r.json())


@app.route("/api/requisitions/<req_id>/accounts", methods=["GET"])
def api_requisition_accounts(req_id):
    if not state.access_token:
        return jsonify({"error": "Get token first"}), 400
    r = requests.get(
        f"{BASE_URL}/requisitions/{req_id}/",
        headers={"accept": "application/json", "Authorization": f"Bearer {state.access_token}"},
    )
    if r.status_code != 200:
        return jsonify({"error": r.text}), 400
    data = r.json()
    return jsonify({"accounts": data.get("accounts", [])})


@app.route("/api/config/preview", methods=["POST"])
def api_config_preview():
    body = request.json or {}
    selected = body.get("selected_accounts", [])  # list of dicts: {account_id, name}
    refresh_accounts = body.get("refresh_accounts", [])  # list of dicts: {config_name, account_id}
    enable_historic = body.get("enable_historic", "off")  # off|global|same_account

    if not state.config_file:
        return jsonify({"error": "Wizard not initialized with config_file"}), 400

    config = load_config()
    accounts = config.get("accounts", {}) or {}
    account_names = [entry.get("name") or f"Nordigen Account {entry.get('account_id')[:8]}" for entry in selected]

    for entry in selected:
        acc_id = entry.get("account_id")
        name = entry.get("name") or f"Nordigen Account {acc_id[:8]}"
        taggers = {"regex": {}}
        if enable_historic != "off":
            # historic_from basic enable; scope extension can be handled later in tagger implementation
            if enable_historic == "same_account":
                taggers["historic_from"] = [name]
            else:
                taggers["historic_from"] = account_names
        accounts[name] = {
            "type": "nordigen-account",
            "secret_id": "${NORDIGEN_SECRET_ID}",
            "secret_key": "${NORDIGEN_SECRET_KEY}",
            "account": acc_id,
            "remove_transaction_description_prefix": False,
            "category_taggers": taggers,
        }

    for entry in refresh_accounts:
        config_name = entry.get("config_name")
        account_id = entry.get("account_id")
        if not config_name or not account_id:
            continue
        if config_name not in accounts:
            return jsonify({"error": f"Config account not found: {config_name}"}), 400
        if (accounts[config_name] or {}).get("type") != "nordigen-account":
            return jsonify({"error": f"Config account is not nordigen-account: {config_name}"}), 400
        accounts[config_name]["account"] = account_id

    config["accounts"] = accounts

    return jsonify({"preview": yaml.safe_dump(config, sort_keys=False)})


@app.route("/api/config/write", methods=["POST"])
def api_config_write():
    body = request.json or {}
    preview = body.get("preview")
    if not preview:
        return jsonify({"error": "preview content required"}), 400
    if not state.config_file:
        return jsonify({"error": "Wizard not initialized with config_file"}), 400
    with open(state.config_file, "w") as f:
        f.write(preview)
    return jsonify({"ok": True, "path": state.config_file})


@app.route("/api/google_sheets", methods=["POST"])
def setup_google_sheets():
    body = request.json or {}
    spreadsheet_id = body.get("spreadsheet_id")
    credentials_path = body.get("credentials_path", "./credentials.json")
    token_cache_path = body.get("token_cache_path", "./token.pickle")

    if not spreadsheet_id:
        return jsonify({"error": "Spreadsheet ID is required"}), 400

    if not state.config_file:
        return jsonify({"error": "Wizard not initialized with config_file"}), 400

    config = load_config()
    repositories = config.get("repositories", {})
    repositories["googlesheet"] = {
        "scopes": ["https://www.googleapis.com/auth/spreadsheets"],
        "spreadsheet_id": spreadsheet_id,
        "credentials_path": credentials_path,
        "expenses_sheet_name": "Expenses",
        "expenses_staging_name": "Expenses Staging",
        "expenses_start_cell": "A1",
        "metadata_sheet_name": "Data",
        "accounts_balance_sheet_name": "Accounts_Balance",
        "accounts_balance_start_cell": "A1",
        "token_cache_path": token_cache_path
    }

    config["repositories"] = repositories

    with open(state.config_file, "w") as f:
        yaml.safe_dump(config, f)

    return jsonify({"ok": True, "path": state.config_file})


@app.route("/api/import_accounts", methods=["POST"])
def import_accounts():
    body = request.json or {}
    account_ids = body.get("account_ids", [])

    if not state.config_file:
        return jsonify({"error": "Wizard not initialized with config_file"}), 400

    config = load_config()
    accounts = config.get("accounts", {}) or {}

    for acc_id in account_ids:
        name = f"Existing Account {acc_id[:8]}"
        accounts[name] = {
            "type": "nordigen-account",
            "secret_id": "${NORDIGEN_SECRET_ID}",
            "secret_key": "${NORDIGEN_SECRET_KEY}",
            "account": acc_id,
            "remove_transaction_description_prefix": False,
            "category_taggers": {"regex": {}},
        }

    config["accounts"] = accounts

    with open(state.config_file, "w") as f:
        yaml.safe_dump(config, f)

    return jsonify({"ok": True, "accounts_added": account_ids})


# =============================================================================
# Manual Accounts Upload Routes
# =============================================================================

def get_google_sheet_repository():
    """Build GoogleSheetRepository from config."""
    config = load_config()
    repo_config = config.get("repositories", {}).get("googlesheet")
    if not repo_config:
        raise ValueError("No googlesheet repository configured")
    return GoogleSheetRepository(**repo_config)


@app.route("/manual")
def manual_accounts_page():
    """Serve the manual accounts upload page."""
    return send_from_directory(app.static_folder, "manual.html")


@app.route("/api/manual/accounts", methods=["GET"])
def api_manual_accounts():
    """List all xlsx-manual type accounts from config."""
    if not state.config_file:
        return jsonify({"error": "Wizard not initialized with config_file"}), 400

    config = load_config()
    accounts = config.get("accounts", {}) or {}
    manual_accounts = []

    for name, account in accounts.items():
        if account.get("type") != "xlsx-manual":
            continue
        manual_accounts.append({
            "name": name,
            "columns": account.get("columns", {}),
            "date_format": account.get("date_format", "%d-%m-%Y"),
        })

    return jsonify(manual_accounts)


@app.route("/api/manual/accounts/<account_name>/last_sync", methods=["GET"])
def api_manual_account_last_sync(account_name):
    """Get last sync date and transactions for that date from Google Sheets."""
    if not state.config_file:
        return jsonify({"error": "Wizard not initialized with config_file"}), 400

    try:
        repo = get_google_sheet_repository()

        # Get last transaction date from the Data sheet (column A=Sources, B=Last Auth Date)
        last_date = repo.get_last_transaction_date_for_account(account_name)

        if last_date is None:
            return jsonify({
                "account_name": account_name,
                "last_sync_date": None,
                "transactions": [],
                "message": "No transactions found for this account"
            })

        # Get transactions from that date
        all_transactions = repo.get_transactions()
        last_date_str = last_date.strftime("%Y-%m-%d")

        log.info(f"Searching for account_name={account_name}, last_date_str={last_date_str}, total_transactions={len(all_transactions)}")

        # Schema from Expenses sheet: [DateCapture, DateAuth, Description, Account, Type, Category, ?, Amount]
        # Indexes:                        0           1          2          3       4       5      6    7
        transactions_on_date = []
        for t in all_transactions:
            if len(t) > 3 and t[3] == account_name:
                log.info(f"Account match: capture={t[0]}, auth={t[1]}, last_date_str={last_date_str}, match={(t[1] == last_date_str or t[0] == last_date_str)}")
                if t[1] == last_date_str or t[0] == last_date_str:
                    transactions_on_date.append({
                        "capture_date": t[0],
                        "auth_date": t[1],
                        "description": t[2],
                        "account": t[3] if len(t) > 3 else "",
                        "type": t[4] if len(t) > 4 else "",
                        "category": t[5] if len(t) > 5 else "",
                        "amount": t[7] if len(t) > 7 else "",
                    })

        return jsonify({
            "account_name": account_name,
            "last_sync_date": last_date.strftime("%Y-%m-%d"),
            "transactions": transactions_on_date,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/manual/accounts/<account_name>/upload", methods=["POST"])
def api_manual_account_upload(account_name):
    """Upload and process XLSX file for a manual account."""
    if not state.config_file:
        return jsonify({"error": "Wizard not initialized with config_file"}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    config = load_config()
    accounts = config.get("accounts", {}) or {}
    account_config = accounts.get(account_name)

    if not account_config:
        return jsonify({"error": f"Account '{account_name}' not found in config"}), 404

    if account_config.get("type") != "xlsx-manual":
        return jsonify({"error": f"Account '{account_name}' is not an xlsx-manual type"}), 400

    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        # Parse XLSX using existing fetcher
        fetcher = XlsxTransactionsFetcher(
            header_skip_rows=account_config.get("header_skip_rows", 8),
            date_format=account_config.get("date_format", "%d-%m-%Y"),
            decimal_separator=account_config.get("decimal_separator", ","),
            thousands_separator=account_config.get("thousands_separator", " "),
            columns=account_config["columns"],
            sheet_name=account_config.get("sheet_name"),
            footer_skip_rows=account_config.get("footer_skip_rows", 0),
        )

        # Get last sync date to filter new transactions
        repo = get_google_sheet_repository()
        last_date = repo.get_last_transaction_date_for_account(account_name)

        # Fetch transactions from the file (filter by date if we have a last sync)
        raw_transactions = fetcher.getTransactions(
            date_init=last_date,
            date_end=None,
            file_path=tmp_path,
        )

        # Clean up temp file
        os.unlink(tmp_path)

        if not raw_transactions:
            return jsonify({
                "success": True,
                "message": "No new transactions found in file",
                "transaction_count": 0,
            })

        # Convert to the format expected by GoogleSheetRepository
        # Schema: [capture_date, auth_date, description, category, account, balance, currency, amount]
        transactions_to_push = []
        for row in raw_transactions:
            capture = row["captureDate"].strftime("%Y/%m/%d") if row["captureDate"] else ""
            auth = row["authDate"].strftime("%Y/%m/%d") if row["authDate"] else capture
            transactions_to_push.append([
                capture,
                auth,
                row["description"],
                "",  # category - to be filled later
                account_name,
                row.get("balance", ""),
                "EUR",  # currency - default
                row["amount"],
            ])

        # Push to Google Sheets
        repo.batch_insert(transactions_to_push, check_duplicates=True)

        return jsonify({
            "success": True,
            "message": f"Successfully processed {len(transactions_to_push)} transactions",
            "transaction_count": len(transactions_to_push),
        })

    except Exception as e:
        # Clean up temp file if it exists
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return jsonify({"error": str(e)}), 500


def main():
    parser = argparse.ArgumentParser(description="Nordigen/GoCardless Web Onboarding Wizard")
    parser.add_argument("--config-file", required=True, help="Path to YAML config to update")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--country", default="pt")
    args = parser.parse_args()

    state.config_file = args.config_file
    state.country = args.country

    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
