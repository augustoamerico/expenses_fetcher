# Portfolio Performance Integration

## Context

This project (expenses_fetcher) focuses on **cashflow tracking** - transactions flowing in and out of accounts. For **portfolio management** (positions, performance, net worth), a separate tool is used: [Portfolio Performance](https://www.portfolio-performance.info/).

Both tools are valuable for their respective purposes. The goal is not to merge them, but to reduce friction where they overlap.

---

## Problem: Duplicate Balance Entry

### Current State

| Account Type | Balance tracked in | Transactions tracked in |
|--------------|-------------------|------------------------|
| Checking accounts (Nordigen API) | expenses_fetcher + PP (duplicated) | expenses_fetcher |
| Savings accounts (no API) | PP only | PP only |
| Investment accounts | PP only | PP only |

### The Friction

expenses_fetcher already pulls checking account balances via Nordigen/open banking. But to maintain a complete net worth view in Portfolio Performance, these same balances are manually entered into PP monthly.

This is pure duplication - typing numbers that already exist in Google Sheets.

---

## Solution: CSV Export for PP Import

### Approach

After expenses_fetcher pulls balances from Nordigen accounts, generate a CSV file in Portfolio Performance's import format. This CSV can then be manually imported into PP.

### Why This Approach?

- **Low effort**: Small addition to existing flow
- **User stays in control**: Manual import means you still review the data
- **No PP file manipulation**: Avoids complexity of directly editing PP's XML format
- **Matches existing workflow**: You already update PP monthly; this just removes typing

### Constraints

- **Only covers Nordigen-accessible accounts**: Savings accounts, term deposits, and other non-PSD2 accounts must still be updated manually in PP
- **Account names must match**: The account names in expenses_fetcher config must match the deposit account names in Portfolio Performance

---

## CSV Format

Portfolio Performance accepts CSV imports for deposit account transactions. A balance update can be represented as a "deposit" or "removal" transaction that brings the account to the correct balance.

**Simple balance snapshot format:**

```csv
Date;Value;Account
2025-03-01;1234.56;ActivoBankCurrente
2025-03-01;5678.90;CGDCurrente
2025-03-01;4586.18;BancoInvest_Corrente
```

*Note: Exact format may need adjustment based on PP's CSV import requirements. Test with a sample import first.*

---

## Implementation

### Where It Fits

This export could run:
1. **As part of the automation cron job** - After pulling balances, write CSV to a known location
2. **As a separate command** - `python tools/export_pp_balances.py`

### Output Location

```
expenses_fetcher/
├── exports/
│   └── pp_balances_YYYYMMDD.csv
```

Or configurable path in config.yaml.

---

## Workflow (After Implementation)

**Monthly routine:**

1. Run expenses_fetcher (or let automation run daily)
2. Open `exports/pp_balances_YYYYMMDD.csv`
3. In Portfolio Performance: File → Import → CSV
4. Manually update savings accounts and add investment transactions (as before)

**Time saved:** No more typing checking account balances - just import.

---

## Out of Scope

These remain manual in Portfolio Performance:

- **Savings account balances** - No API access via Nordigen
- **Investment transactions** - Intentionally manual ("forces me to look at performance")
- **Security prices** - PP handles this via its own price feeds

---

## Account Name Mapping

For the integration to work, account names must match. Document the mapping here once implemented:

| expenses_fetcher config name | Portfolio Performance account name |
|------------------------------|-----------------------------------|
| `ActivoBankCurrente` | `ActivoBankCurrente` |
| `CGDCurrente` | `CGDCurrente` |
| ... | ... |

*Fill in during implementation based on actual config and PP setup.*

---

*Document created: March 2025*
*Status: Design complete, not yet implemented*
