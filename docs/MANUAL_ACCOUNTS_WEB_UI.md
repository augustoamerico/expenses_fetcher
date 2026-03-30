# Manual Accounts Web UI

## Problem

Some bank accounts don't support PSD2/open banking (e.g., MyEdenred, certain savings accounts). These require manual CSV export from the bank's website/app, then running a script to import transactions.

### Current Friction

1. Download CSV from bank (can be done on phone)
2. Need a computer with the repo to run the import script
3. No visibility into which manual accounts are stale

**Result:** Manual accounts rarely get updated because it requires being at a computer.

---

## Solution

A web interface hosted on Zimaboard that:
1. Shows all accounts (automated + manual) with last sync dates
2. Allows CSV upload for manual accounts from any device (phone or computer)
3. Processes the upload and pushes transactions to Google Sheets

### Why This Approach?

- **Device agnostic**: Phone browser works fine for uploading files
- **Reuses existing infrastructure**: Same Zimaboard running the automation
- **Visual feedback**: See at a glance which accounts need attention
- **Low friction**: Bank app → export CSV → upload → done

---

## Architecture

```
Phone/Computer Browser
    │
    └─→ expenses-web (Flask, port 8787, on Zimaboard)
            │
            ├─→ Dashboard: view all accounts + last sync dates
            │       └─→ Queries Google Sheets for latest transaction dates
            │
            ├─→ Nordigen re-auth wizard (existing)
            │
            └─→ Manual CSV upload
                    └─→ Process CSV → Push to Google Sheets
```

### Unified Web Service

Extend the existing `nordigen_onboarding_web` Flask app to include:
- Dashboard view
- Manual account upload endpoints

This keeps infrastructure simple (one web service, one port).

---

## User Interface

### Dashboard (Home Page)

```
┌─────────────────────────────────────────────────────┐
│  Expenses Fetcher Dashboard                         │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Automated Accounts (Nordigen)                      │
│  ┌─────────────────────────────────────────────┐    │
│  │ ✓ Revolut            Last sync: today       │    │
│  │ ✓ ActivoBank         Last sync: today       │    │
│  │ ⚠ CGD                Re-auth needed  [→]    │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  Manual Accounts                                    │
│  ┌─────────────────────────────────────────────┐    │
│  │ ⚠ MyEdenred          Last: 45 days ago      │    │
│  │                      [Upload CSV]           │    │
│  │                                             │    │
│  │ ✓ OtherBank          Last: 5 days ago       │    │
│  │                      [Upload CSV]           │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Status Indicators

| Icon | Meaning |
|------|---------|
| ✓ | Synced recently (< 7 days) |
| ⚠ | Stale (> 7 days) or needs action |

Thresholds can be configurable per account (some accounts may only need monthly updates).

### Upload Page (`/manual/<account>/upload`)

```
┌─────────────────────────────────────────────────────┐
│  Upload CSV - MyEdenred                             │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Last sync: 2025-01-15 (45 days ago)                │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │  [Choose File]  No file selected            │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  [Upload and Process]                               │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Success/Error Feedback

After upload:
```
┌─────────────────────────────────────────────────────┐
│  Upload Complete                                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ✓ Processed 23 transactions                        │
│  ✓ Pushed to Google Sheets                          │
│                                                     │
│  [← Back to Dashboard]                              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

Or on error:
```
┌─────────────────────────────────────────────────────┐
│  Upload Failed                                      │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ✗ Error parsing CSV: unexpected column format      │
│                                                     │
│  Expected columns: Date, Description, Amount        │
│  Found columns: Data, Descrição, Valor              │
│                                                     │
│  [Try Again]                                        │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Mobile Workflow

1. Open bank app on phone
2. Export transactions as CSV → saves to Downloads
3. Open `http://zimaboard-ip:8787` in phone browser
4. See dashboard - notice MyEdenred is stale
5. Tap "Upload CSV" next to MyEdenred
6. Select CSV file from Downloads
7. Tap "Upload and Process"
8. See success message with transaction count
9. Done - transactions are in Google Sheets

---

## Implementation Details

### Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Dashboard with all accounts |
| `/nordigen/onboard` | GET | Existing re-auth wizard |
| `/manual/<account>` | GET | Upload form for specific account |
| `/manual/<account>/upload` | POST | Process uploaded CSV |

### Last Sync Date

Query Google Sheets for the latest transaction date per account:

```python
def get_last_sync_date(account_name: str) -> date | None:
    """Query Google Sheets for most recent transaction date for this account."""
    # Query the Expenses or Staging sheet
    # Filter by Account column
    # Return max(Date) or None if no transactions
```

### CSV Processing

Reuse existing importer logic:

```python
@app.route('/manual/<account>/upload', methods=['POST'])
def upload_csv(account):
    file = request.files['csv_file']

    # 1. Get account config (which parser to use)
    account_config = get_manual_account_config(account)

    # 2. Parse CSV using existing importer
    transactions = parse_csv(file, account_config['parser'])

    # 3. Push to Google Sheets (reuse existing repository)
    repository.push_transactions(transactions)

    # 4. Return success with count
    return render_template('upload_success.html', count=len(transactions))
```

### Config Extension

Add manual accounts to config.yaml:

```yaml
accounts:
  # Existing Nordigen accounts...

  MyEdenred:
    type: manual-csv
    parser: edenred  # Which CSV parser to use
    stale_threshold_days: 30  # When to show warning

  OtherBank:
    type: manual-csv
    parser: generic-csv
    stale_threshold_days: 14
```

---

## Integration with Automation Plan

This feature extends the same web service used for Nordigen re-auth:

```
expenses-web (Flask, port 8787)
├── /                        → Dashboard (NEW)
├── /nordigen/onboard        → Re-auth wizard (existing)
├── /manual/<account>        → CSV upload form (NEW)
└── /manual/<account>/upload → Process CSV (NEW)
```

The automation cron job handles Nordigen accounts automatically. This UI handles:
1. Manual account uploads
2. Visual status of all accounts
3. Nordigen re-auth when needed

---

## Future Enhancements

- **Drag-and-drop upload**: Better UX on desktop
- **Transaction preview**: Show parsed transactions before pushing
- **Edit before push**: Allow fixing categorization before submit
- **Upload history**: Track when each upload happened

---

*Document created: March 2025*
*Status: Design complete, implementation after core automation*
