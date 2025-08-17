# Simple local web wizard for Nordigen/GoCardless onboarding
# Run: python tools/nordigen_onboarding_web/app.py --config-file config/your.yaml --port 8787

import argparse
import os
import json
from datetime import datetime
from urllib.parse import urlencode

import requests
import yaml
from flask import Flask, request, jsonify, send_from_directory, redirect

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


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/init", methods=["POST"])
def api_init():
    data = request.json or {}
    state.config_file = data.get("config_file")
    state.country = data.get("country", "pt")
    if not state.config_file:
        return jsonify({"error": "config_file required"}), 400
    return jsonify({"ok": True})


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
    enable_historic = body.get("enable_historic", "off")  # off|global|same_account

    if not state.config_file:
        return jsonify({"error": "Wizard not initialized with config_file"}), 400

    with open(state.config_file, "r") as f:
        config = yaml.safe_load(f) or {}

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

    with open(state.config_file, "r") as f:
        config = yaml.safe_load(f) or {}

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


def main():
    parser = argparse.ArgumentParser(description="Nordigen/GoCardless Web Onboarding Wizard")
    parser.add_argument("--config-file", required=True, help="Path to YAML config to update")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--country", default="pt")
    args = parser.parse_args()

    state.config_file = args.config_file
    state.country = args.country

    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
