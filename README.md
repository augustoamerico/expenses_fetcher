# Expenses Fetcher

A small CLI tool to pull personal finance transactions from multiple sources (banks/APIs), categorize them, and push them into repositories such as Google Sheets. It also tracks account balances and supports basic deduplication.

Highlights
- Repository-first workflow: keep categorization and dashboards in your repository (Google Sheets today; Excel planned).
- Pull transactions from:
  - ActivoBank (web automation with Selenium)
  - MyEdenred (official API)
  - Nordigen/GoCardless (open banking API)
  - Manual XLSX imports (xlsx-manual) for banks without open banking
- Categorize using:
  - Regular expressions
  - Historic matching learned from your repository (for both Category and Type)
- Type suggestions:
  - Learns and suggests Type (Debt, Income, Investment, Transfer) from your own history and configured labels
- Push data to:
  - Google Sheets (with OAuth)
  - [Optional, deprecated] Buxfer (behind FEATURES_ENABLE_BUXFER)
- Interactive shell to pull, list, sort, and push
- Balance tracking and appending to repositories (xlsx-manual appends latest balance)

---

Repository-first (Sheets/Excel) philosophy
- Your repository (Google Sheets now; Excel Online planned) is the first-class UI for review, categorization, and visualization.
  - Workflow: Expenses Staging → manual validate/split (data validation, dropdowns) → button/script → Expenses.
  - Dashboards and pivots live in the repository (e.g., Month Report by Category, Year/Category pivots).
- The Python app is a pipeline that fetches, suggests, stages, and syncs — it does not override your manual edits.
- The repository abstraction lets you keep the same UX across sinks (Google Sheets today, Excel Online tomorrow) with consistent sheet/table schemas.

---

Prerequisites
- Python 3.8+ recommended
- For ActivoBank:
  - Google Chrome installed
  - ChromeDriver installed and available in PATH (matching your Chrome version)
- For Google Sheets:
  - Google Cloud project with “Google Sheets API” enabled
  - OAuth client credentials JSON file
- For XLSX imports:
  - openpyxl
- Network access to:
  - MyEdenred API
  - Nordigen/GoCardless API

---

Quick start

1) Create and activate a virtual environment
- macOS/Linux:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```
- Windows (PowerShell):
  ```bash
  py -m venv venv
  venv\Scripts\Activate.ps1
  ```

2) Install dependencies
```bash
pip install -r requirements.txt
```

3) Prepare Google Sheets credentials (if using Google Sheets)
- Create a Google Cloud project and enable “Google Sheets API”
- Create OAuth client credentials for “Desktop App”
- Download the credentials JSON to a path you’ll reference in the config (credentials_path)

4) Create your config file
- Start from your own YAML file (e.g., config/my_config.yaml) using the template below

5) Run the CLI
```bash
python main.py --config-file config/my_config.yaml
```

---

Configuration

Place your YAML config anywhere (e.g., config/your_config.yaml) and pass it to the CLI with --config-file. The structure connects accounts (sources) to repositories (sinks), and wires category taggers.

Minimal example (adjust to your needs):

- Google Sheets as repository
- ActivoBank, MyEdenred, Nordigen as accounts
- BancoInvest (xlsx-manual) as a manual file-based account

Example config

```yaml
expense_fetcher_options:
  tmp_dir_path: "/tmp/expenses_fetcher"  # required for ActivoBank downloads

repositories:
  googlesheet:
    scopes:
      - https://www.googleapis.com/auth/spreadsheets
    spreadsheet_id: "YOUR_SHEET_ID"
    expenses_sheet_name: "Expenses"
    expenses_staging_name: "Expenses Staging"
    expenses_start_cell: "A2"
    metadata_sheet_name: "Data"  # point this to your metadata sheet (often called "Data")
    accounts_balance_sheet_name: "Accounts Balance"
    accounts_balance_start_cell: "A2"
    token_cache_path: "token.pickle"
    credentials_path: "credentials.json"
  # Optional, deprecated sink (disabled by default; enable with FEATURES_ENABLE_BUXFER=true)
  # buxfer:
  #   username: "your_email@example.com"
  #   password_env: "BUXFER_PASSWORD"
  #   define_type:
  #     transfer:
  #       - to:
  #           account_name: "Savings"
  #           description: "Transfer to Savings"
  #           category: "Transfers"
  #         from:
  #           account_name: "Checking"
  #           description: "Transfer to Savings"
  #           category: "Transfers"

accounts:
  Active Main Card:
    type: activebank-debit
    card_number: "1234"
    # Use either *_env or inline values
    username_env: "ACTIVE_USER"
    password_env: "ACTIVE_PASS"
    remove_transaction_description_prefix: false
    category_taggers:
      regex:
        Groceries: ["(?i)continente|pingo\\sdoce|lidl"]
        Transport: ["(?i)uber|bolt|metro|bus"]
      historic_from: {}

  Meal Card:
    type: myedenred
    card_number: "987654321"
    username_env: "EDENRED_USER"
    password_env: "EDENRED_PASS"
    category_taggers:
      regex:
        Restaurants: ["(?i)restaurant|cafe|menu"]
      historic_from: {}

  OpenBanking Account:
    type: nordigen-account
    secret_id: "YOUR_NORDIGEN_SECRET_ID"
    secret_key: "YOUR_NORDIGEN_SECRET_KEY"
    account: "YOUR_ACCOUNT_UUID"
    remove_transaction_description_prefix: false
    category_taggers:
      regex:
        Salary: ["(?i)salary|payroll"]
        Rent: ["(?i)rent|landlord"]
      historic_from: {}

  BancoInvest Movements:
    type: xlsx-manual
    prompt_for_file_path: true
    header_skip_rows: 8
    footer_skip_rows: 1
    date_format: "%d-%m-%Y"
    decimal_separator: ","
    thousands_separator: " "
    columns:
      capture_date: "Data Operação"
      auth_date: "Data Valor"
      description: "Descrição"
      debit: "Débito"
      credit: "Crédito"
      balance: "Saldo"
    category_taggers:
      regex:
        Interest: ["(?i)juros|interest"]
      historic_from: {}
    exclude_regex:
      - "(?i)mb\\s*way"

transactions:
  debt: "Debt"
  income: "Income"
  transfer: "Transfer"
  investment: "Investment"   # optional; used when Type is learned/suggested
  date_format: "%Y-%m-%d"
```

Notes:
- historic_from: learns Category and Type by Description from your repository.
- xlsx-manual: prompts for a file path unless file_path is configured; applies header/footer skips; normalizes locale decimals/thousands; unifies debit/credit -> signed amount; appends the most recent balance.

---

How it works

- main.py reads your YAML config and builds an ExpensesFetcher via src/service/configuration/configuration_parser.py:
  - Accounts are created for each source:
    - ActivoBank: src/application/account_manager/active_bank_account_manager.py
    - MyEdenred: src/application/account_manager/myedenred_account_manager.py
    - Nordigen: src/application/account_manager/nordigen_account_manager.py
    - Manual XLSX: src/application/account_manager/xlsx_manual_account_manager.py
  - Repositories are created for each sink:
    - Google Sheets: src/repository/google_sheet_repository.py
    - [Optional] Buxfer (deprecated; behind feature flag): src/repository/buxfer_repository.py
  - Taggers are wired into each account:
    - RegexTagger for rule-based categories
    - HistoricTagger to suggest both Category and Type from your past "Expenses" history

- The shell (ExpenseFetcherShell) exposes commands to fetch, stage, review, sort, and push transactions

Data model
- Domain transaction types per source: src/domain/transactions/*.py
- Flattened rows used for repositories: src/application/transactions/expense_fetcher_transaction.py
  - [capture_date, auth_date, description, account_name, type, category, unsigned_value, value]
- Balance model: src/domain/balance/balance.py

Type resolution
- If a tagger (e.g., HistoricTagger) suggests a Type, it is used.
- Otherwise, derive with priority: Transfer > Investment > Debt > Income.
- Transfer convention: if Category equals any configured account name, mark as Transfer unless a tagger already set Type.

Additional behavior
- Last Auth Date by Source: If you omit date_start, the app reads your “Data” sheet A2:B (account, last date) and uses that as the lower bound for each account, including xlsx-manual.
- Balances: The app calls get_balance before fetching transactions. For xlsx-manual, the importer reads the file (respecting header/footer skips) and appends the most recent balance (by auth date; fallback to capture date) to "Accounts Balance".

---

Interactive shell

Start
```bash
python main.py --config-file path/to/your_config.yaml
```

Commands
- pull
  - Parameters (comma-separated key=value):
    - account_name=Account Name (optional; default: all)
    - date_start=YYYY-MM-DD (optional)
    - date_end=YYYY-MM-DD (optional)
    - apply_categories=True|False (default True)
  - Example:
    ```bash
    pull account_name="Meal Card",date_start=2024-01-01,date_end=2024-01-31,apply_categories=True
    ```

- sort
  - Parameters:
    - reverse=True|False (default False)
  - Example:
    ```bash
    sort reverse=False
    ```

- list
  - Prints currently staged transactions as a table

- push
  - Parameters:
    - repository_name=googlesheet (optional; default: all configured)
  - Examples:
    ```bash
    push
    push repository_name=googlesheet
    ```

- pull_from_sink
  - Parameters:
    - repository=googlesheet
  - Loads transactions from a repository into staging (useful for inspection)
  - Example:
    ```bash
    pull_from_sink repository=googlesheet
    ```

- remove
  - Parameters:
    - account_name=Account Name (optional; default: clear all)
  - Example:
    ```bash
    remove account_name="Meal Card"
    ```

- exit
  - Closes connections and exits

Dates
- If you omit date_start/date_end, the tool attempts to infer a starting date from a repository’s latest transaction date for each account, and uses today as the end date.

---

Google Sheets repository

- First-class UI: This is the primary place where you review, categorize (via dropdowns), optionally split rows, and run a button/script to promote data from "Expenses Staging" to "Expenses". Build your pivots and dashboards here.
- OAuth: First run will open a local browser window to authorize. A token cache (token_cache_path) is stored for reuse.
- Expected structure (you can name the sheet tabs as you prefer):
  - expenses_sheet_name + expenses_start_cell (where data goes)
  - expenses_staging_name (staging sheet for new rows)
  - metadata_sheet_name (often "Data"):
    - Column A: Account names
    - Column B: Last transaction date per account (YYYY-MM-DD)
    - Column D: Categories list (D2:D)
  - accounts_balance_sheet_name + accounts_balance_start_cell for balances
- Deduplication: New inserts to the staging sheet are deduped against existing data by string serialization.

---

Future sinks: Excel Online
- The repository abstraction is designed to support an ExcelRepository that mirrors the Google Sheets experience (staging sheet, final sheet, metadata). This enables the same repository-first workflow for Excel users.

---

Categorization and type learning

- RegexTagger: Match description strings using regex to assign categories
- HistoricTagger: Learns from your Expenses history (by Description) to suggest both Category and Type
- Transfer detection:
  - If Category matches any configured account name, the transaction is marked as Transfer unless a tagger already set a Type

---

Security tips

- Prefer environment variables for credentials (username_env, password_env, BUXFER_PASSWORD, etc.)
- For Google Sheets, keep your credentials.json outside of version control
- The app can prompt for secrets via TTY when not supplied

---

Troubleshooting

- Selenium/Chrome errors (ActivoBank):
  - Ensure ChromeDriver is installed and matches your Chrome version
  - Ensure ChromeDriver is in PATH
- Google Sheets 403/permission errors:
  - Verify credentials_path points to the correct OAuth client file
  - Ensure the Sheets API is enabled and scope includes spreadsheets write access
- Nordigen errors:
  - Verify secret_id/secret_key and account UUID
  - Check network access to bankaccountdata.gocardless.com
- Footer/banners: Set footer_skip_rows to ignore trailing non-transaction rows.
- Date errors (time data '...' does not match format): Ensure date_format matches the export (e.g., "%d-%m-%Y"). Non-transaction rows should be ignored via footer_skip_rows.
- Separators: Set decimal_separator and thousands_separator to match your XLSX (e.g., "," and " ").
- [Optional, when Buxfer is enabled] Buxfer login failures:
  - Confirm credentials and API availability
  - If 2FA is enabled, ensure you can authenticate via the API

---

Development

- Install dev dependencies
  ```bash
  pip install -r requirements-dev.txt
  ```
- Run tests
  ```bash
  pytest
  ```
- Lint and format
  ```bash
  black .
  pylint src tests
  ```
- Type checks
  ```bash
  mypy src
  ```

---

Project layout

- main.py: entry point and interactive shell
- src/application: orchestration (expenses fetcher), account managers, transaction flattening
- src/application/account_manager/xlsx_manual_account_manager.py: manual XLSX account manager (prompts path; converts rows; publishes latest balance)
- src/domain: domain models (transactions, balances), category taggers
- src/infrastructure/bank_account_transactions_fetchers: source-specific fetchers (web/API)
- src/infrastructure/bank_account_transactions_fetchers/xlsx_transactions_fetcher.py: XLSX fetcher (header/footer skips; locale parsing)
- src/repository: repository (sink) implementations for Google Sheets
- src/service/configuration: YAML config parsing and wiring
- tests/: unit tests

---

License

- Add your license information here (e.g., MIT)
