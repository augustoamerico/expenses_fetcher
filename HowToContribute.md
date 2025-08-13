# How to Contribute (for LLMs and Agents)

This repo powers a sheet-centric personal finance workflow: fetch transactions from multiple sources, suggest categories and types, stage in Google Sheets for human review/splitting, and then promote to a long-term "Expenses" sheet. Contributions should preserve this workflow and add value with minimal disruption.

Core principles
- Sheet-first review: Keep "Expenses Staging → manual validate/split → button → Expenses" intact. The code suggests; the sheet confirms.
- Minimal, focused diffs: Prefer augmenting existing components over introducing new layers. Avoid broad refactors.
- Config-first: Extend YAML config and, where useful, the Google Sheet Data sheet to drive behavior. Keep defaults backward compatible.
- Deterministic and explicit: Prefer explicit mappings/rules over hidden heuristics. Use stable types/labels from config.
- Robust and consistent: Handle dates, booleans, and string comparisons correctly. Avoid fragile code paths.

Repository architecture (overview)
- Top level
  - main.py: CLI shell; builds ExpensesFetcher from YAML; interactive commands (pull, sort, list, push, remove, pull_from_sink, exit).
  - do_pull_sort_push.py: convenience script (example flow) that exercises pull→sort→push.
  - nordigen_refresh_tokens.py: helper related to Nordigen/GoCardless authentication (token refresh experiments).
  - run_tests.sh: helper to run tests locally.
- src/application
  - expenses_fetcher/expenses_fetcher.py: orchestrates accounts and repositories; stages transactions and balances; sorts; pushes (with basic dedupe delegated to repos).
  - account_manager/
    - i_account_manager.py: interface; get_transactions applies taggers and transfer rules; manages category/type assignment.
    - active_bank_account_manager.py: wraps Selenium crawler for ActivoBank; converts rows to domain transactions.
    - myedenred_account_manager.py: wraps MyEdenred fetcher; converts rows to domain transactions.
    - nordigen_account_manager.py: wraps Nordigen fetcher; converts rows to domain transactions; fetches balances.
    - exceptions.py: account-related exceptions.
  - password_getter/
    - password_getter.py: interface used to obtain secrets on demand.
  - transactions/
    - expense_fetcher_transaction.py: flattens domain transactions to the 8-column row schema used by repositories.
- src/domain
  - transactions/
    - i_transaction.py: transaction interface and common behavior (dates, amounts, category/type flags and accessors).
    - activebank_transaction.py, myedenred_transaction.py, nordigen_transaction.py: concrete transaction types for each source.
    - from_list_transaction.py: utility to create a transaction from a flat row.
  - category_taggers/
    - i_tagger.py: tagger interface (get_category, get_type).
    - regex_tagger.py: regex-based category tagger.
    - historic_tagger.py: learns most frequent Category and Type per Description from the Expenses sheet via repository.get_data.
  - balance/
    - balance.py: Balance dataclass and list serialization for pushing to repositories.
- src/infrastructure/bank_account_transactions_fetchers
  - i_transactions_fetcher.py: interface for source fetchers.
  - active_bank_fetcher_crawler.py: Selenium automation to log in and download XLSX; parses rows via openpyxl.
  - myedenred_fetcher.py: HTTP API client for MyEdenred; returns movement lists.
  - nordigen_fetcher.py: GoCardless (Nordigen) API client for transactions and balances.
  - exceptions.py: fetcher-specific exceptions.
- src/repository
  - i_repository.py: repository (sink) interface.
  - google_sheet_repository.py: Google Sheets sink; OAuth, read/write ranges; dedupe; last-transaction dates; categories; balances append.
  - buxfer_repository.py: Buxfer sink (deprecated; disabled by default via feature flag). See Feature flags for usage.
- src/service
  - configuration/configuration_parser.py: parses YAML into repositories, accounts, and taggers; reads env vars; wires password getters; handles tagger configs.
  - password_getter_tty.py: TTY password getter implementation used by main.py.
- tests/
  - tests/: add unit tests for taggers, account managers, and repositories. Note: the existing infrastructure test scaffold appears outdated; prefer focused unit tests and small integration tests with mocks.

Contribution workflow (LLM-friendly)
1) Understand the user goal and sheet schema
   - Review README.md and this guide.
   - Confirm how the Google Sheet is structured (especially Expenses, Expenses Staging, Data).
2) Propose a short plan before coding
   - List scope, config changes (optional keys), code changes by file, acceptance criteria, and risks.
   - Align on incremental delivery (one feature at a time).
3) Implement small, targeted changes
   - Touch only the necessary files.
   - Preserve backward compatibility and existing defaults/labels where possible.
4) Validate and document
   - Provide manual test steps and acceptance checks.
   - Update README.md if the feature introduces new config/usage.

Coding standards and conventions
- Python 3.8+ recommended.
- Formatting/linting/type checks: black, pylint, mypy. Run:
  - pip install -r requirements-dev.txt
  - black .
  - pylint src tests
  - mypy src
- Logging over print; use Python logging module.
- Date/time format defaults: "%Y-%m-%d".
- Booleans: parse explicitly ("true/false/1/0/yes/no"), avoid bool("False").
- String comparisons: use == / !=, not `is` / `is not`.
- Return conventions: when a method means "no suggestion" (e.g., taggers), return empty string "" rather than None.

Feature flags and deprecations
- Prefer gating deprecated functionality behind environment-based feature flags so behavior is explicit and reversible.
- Current flags:
  - FEATURES_ENABLE_BUXFER (default: false)
    - When false/absent: configurations using repository type "buxfer" fail fast with a clear error.
    - When true: BuxferRepository is enabled (restored verbatim) and can be used as before.
- Implementation pattern:
  - Gate usage in src/service/configuration/configuration_parser.parse_repository()
  - Lazily import the deprecated module only when the flag is enabled.

Key abstractions to extend (updated)
- ITransactionsFetcher (src/infrastructure/.../i_transactions_fetcher.py)
  - Implement getTransactions(self, date_init=None, date_end=None) -> List[Dict[str, object]].
  - Keep it source-specific and stateless; let Account Managers convert to domain transactions.
- IAccountManager (src/application/account_manager/i_account_manager.py)
  - Implement _get_transactions and getCategoryTaggers.
  - get_transactions() is the orchestrator: apply exclude rules (if configured), then taggers to set category and type; set transfer if category equals any configured account name and no type was already set.
- ITagger (src/domain/category_taggers/i_tagger.py)
  - get_category(description) -> str.
  - get_type(description) -> str (optional; return "" if not provided).
  - HistoricTagger learns both category and type from the Expenses sheet (by Description).
- ExpenseFetcherTransaction (src/application/transactions/expense_fetcher_transaction.py)
  - Flattens a domain transaction into the 8-column row.
  - Type resolution priority: use transaction.get_type() if present; else derive by Transfer > Investment > Debt > Income using transaction flags.
- IRepository (src/repository/i_repository.py)
  - Implement batch_insert, get_transactions, get_last_transaction_date_for_account, append_balances, get_data.
  - Repositories handle dedup specific to their backend (e.g., Google Sheets staging dedupe).
- configuration_parser (src/service/configuration/configuration_parser.py)
  - Extend parse_account/parse_repository/parse_taggers to wire new sources/sinks/taggers. Prefer optional config keys with defaults.

Semantics and data model (updated)
- Flattened transaction row schema used by repositories:
  - [capture_date, auth_date, description, account_name, type, category, unsigned_value, value]
  - Dates formatted as "%Y-%m-%d" by default.
  - Type strings should match config["transactions"] labels (debt, income, transfer, investment).
- Category and Type assignment flow:
  - AccountManager.get_transactions(): apply exclusions (optional), then taggers. Taggers may set category and type (HistoricTagger learns both). If no type was set by taggers and category equals an account name, mark as Transfer.
  - Fallback: if still unset, use transaction flags (investment/debt/income) to produce a Type in ExpenseFetcherTransaction.
- Balances schema:
  - Balance.to_list() → [balance_date, updated_date_time, account, balance] as strings; appended by repositories.
- Metadata in Google Sheets (recommended):
  - Data sheet holds accounts, categories, category types, last transaction dates by source, balance offsets, available YearMonth.

Patterns for common contributions (updated)
- Add a new tagger
  - Implement ITagger; return "" for fields you don’t set.
  - Optionally add an ExclusionTagger or support account-level exclude_regex (skip subsequent taggers for matching descriptions).
  - Wire via configuration_parser.parse_taggers with minimal config shape.
- Add a new source (bank/API/CSV/XLSX)
  - Create a fetcher under src/infrastructure/bank_account_transactions_fetchers/* that returns a list of raw dicts.
  - Add an AccountManager to convert raw dicts to domain transactions and expose taggers.
  - Extend configuration_parser.parse_account to support type: <your-source> and pass config (date formats, decimal separators, column mappings).
- Add a new sink (repository)
  - Implement IRepository; look at GoogleSheetRepository for range read/write, dedupe, metadata helpers.
  - Keep output row schema and labels consistent with config.
  - If deprecating a sink, prefer:
    - Keep code intact (backwards compatibility)
    - Gate in configuration_parser with a feature flag and fail-fast error when disabled
    - Document the flag and migration path in README/PR
- Enhance Google Sheets integration
  - Add helper reads/writes in GoogleSheetRepository for Data sheet ranges (categories, category types, last dates, offsets).
  - Add utilities to precompute helper columns (YearMonth, BudgetJoiner) if desired.
- Utilities/exports
  - Add a "PP balances recall" exporter to produce a concise checklist or CSV for manual PP updates (no direct PP writes).

Backwards compatibility and config
- New config keys must be optional with safe defaults.
- Respect labels in config["transactions"]: debt, income, transfer, investment—these should be the strings emitted to sinks.
- If reading from the Google Sheet Data sheet, make ranges/sheets configurable and fail with clear errors if missing.
- If a feature is deprecated, add a feature flag with a clear default (usually disabled), fail fast with a descriptive error, and document how to enable temporarily.

Manual testing (quick guide)
- Create a virtual env and install requirements.
- Prepare a minimal YAML config with one repository (Google Sheets) and one account.
- Run:
  - python main.py --config-file path/to/config.yaml
  - In the shell: pull apply_categories=True
  - list to inspect staged rows
  - push repository_name=googlesheet (or your sink)
- If your change affects taggers, verify Suggested Category/Type appear as expected in Staging (per your Sheet setup).
- If your change involves a feature flag (e.g., Buxfer):
  - Default (disabled): ensure the app fails fast with a clear message when config references the disabled feature.
  - Enabled:
    - macOS/Linux:
      FEATURES_ENABLE_BUXFER=true python main.py --config-file path/to/config.yaml
    - Windows (PowerShell):
      $env:FEATURES_ENABLE_BUXFER = "true"
      python main.py --config-file path/to/config.yaml

PR template (for LLMs)
- Title: Short, descriptive
- Summary: What problem/value this adds
- Changes by file: brief bullets referencing specific files
- Config updates: New keys and defaults
- Acceptance criteria: Plain-language checks the user can validate
- Manual test steps: How to quickly exercise the change
- Risk/rollback: Any risks and how to back out (e.g., revert one file)
- Feature flags: Is this gated appropriately? Default safe? Documented in README/PR?
- Migration note: If a feature is deprecated/disabled by default, include steps for users to enable or remove it from config.

Known rough edges (safe improvements)
- Default date format should be "%Y-%m-%d" throughout.
- Avoid using `is` for string comparisons in filters.
- main.py boolean and date_end parsing should be explicit and correct.
- Nordigen fetcher should import `date as datetime_date` for date filtering.

Examples of valuable, low-friction contributions
- Add MBWay exclusion regex support and wire via account config.
- Implement a BancoInvest XLSX importer using openpyxl with configurable column mapping.
- Add a "PP balances recall" command to compile deposit balances for manual PP updates.
- Add a stable transaction hash to improve deduplication in repositories.

PRs and branching (conventions and gh)
- Branching: short-lived branches from master; name by intent (feat/x, fix/x, chore/x, docs/x, refactor/x). One concern per PR.
- Keep branches current: rebase on master before opening/merging to reduce conflicts. Prefer squash merges.
- Conventional commits: feat:, fix:, chore:, docs:, refactor:, test:, perf: for clear history.
- Use GitHub CLI (gh):
  - Create PR (ready):
    gh pr create --base master --head feat/add-x --title "feat: add x" --body-file pr.md
  - Create as draft, then mark ready:
    gh pr create --draft ...
    gh pr ready
  - Add labels, reviewers, assignees:
    gh pr edit --add-label "feature" --add-label "deprecation"
    gh pr request-review @reviewer1 @reviewer2
    gh pr assign @your-handle
  - View/checkout/merge:
    gh pr view --web
    gh pr checkout <pr-number>
    gh pr merge --squash --delete-branch

Security and privacy
- Never hardcode credentials; use env vars or prompt via TTYPasswordGetter.
- Do not commit tokens, credentials, or large binaries to the repo.

Style of changes we prefer
- Small, composable diffs.
- Extend existing classes (HistoricTagger, IAccountManager, ITransaction, repositories) before adding new layers.
- Mirror the Google Sheet schema and user labels in code/output.

Thank you for contributing. Keep changes focused, sheet-aligned, and backward compatible. If unsure, propose a brief plan first, then ship in small steps.