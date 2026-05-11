# Budget Wizard Design

## What is a Budget?

**Budget = how much money I need to allocate (or have available) for a category.**

Budget is independent of funding source. Whether the money comes from:
- Current month's income
- Prior savings (funded expenses)
- Investment withdrawals

...doesn't matter for budgeting purposes. The budget answers: "How much do I need for this category?"

**Funding is a separate problem.** It happens after the expense occurs and tracks where the money actually came from. See `docs/FUNDED_EXPENSES.md` for funding logic.

---

## Problem

Budgets are required for meaningful spending analysis, but:
- Currently set manually in Google Sheets (`Financial_Planning`)
- Tedious to create ~20-30 rows per month
- Easy to forget (user hasn't created budgets in ~5 months)

## Solution Overview

A new component in the Flask app (nordigen-onboarding) that:
1. Detects when a budget is needed
2. Generates a proposal based on recent spending
3. Pushes to a staging sheet for review
4. Allows approval to move to final budget

---

## Trigger Conditions

Budget proposal is generated when **either**:
- New month transactions detected (e.g., first sync that includes transactions for month N+1)
- Previous month closure detected (all active accounts synced past month end + buffer)

---

## Proposal Generation Logic

### Data Source
Query `Expenses` sheet for last 3 months of actual spending.

### Category Inclusion Rules

| Condition | Action |
|-----------|--------|
| Category appears in ≥2 of last 3 months | Include in proposal |
| Category appears in only 1 of last 3 months | Omit |
| Category has no spend in last 3 months | Omit |

### Value Selection
For each included category: use the **most recent month's actual value** as the suggested budget.

Why most recent (not average)?
- Reflects current reality (salary changes, new subscriptions, lifestyle changes)
- Simpler to understand and adjust
- Avoids smoothing out intentional changes

### Overlap Handling

If a budget already exists for the target month in Financial_Planning:

1. Fetch existing budget categories for target month
2. Generate proposal as usual
3. Filter out categories that already have a budget entry
4. Push only the "gap" (missing categories) to Budget_Staging

**Notification variants:**
- Full proposal: "Budget proposal for May: 24 categories"
- Partial gap: "Budget proposal for May: 5 new categories added"
- Already complete: "Budget for May already complete — no new categories to add"

### Schema
Same as `Financial_Planning`:
```
[BudgetJoiner, YearMonth, Type, Category, EstimateValue]
```

Example:
```
202605DebtGroceries, 202605, Debt, Groceries, 58.67
202605DebtEating Out, 202605, Debt, Eating Out, 119.30
202605InvestmentInv:EmergencyFund, 202605, Investment, Inv:EmergencyFund, 6000.00
```

---

## Sheets Structure

### New Sheet: `Budget_Staging`

| Column | Description |
|--------|-------------|
| A | BudgetJoiner |
| B | YearMonth |
| C | Type |
| D | Category |
| E | EstimateValue (suggested) |

No status column needed — if a row exists, it's approved. User deletes unwanted rows before clicking "Approve Budget".

### Existing Sheet: `Financial_Planning`
No changes — all Budget_Staging rows are moved here on approval.

---

## User Flow

```
1. Trigger detected (new month / month closed)
   │
   ▼
2. Flask component generates proposal
   - Queries last 3 months from Expenses
   - Applies inclusion rules
   - Takes most recent value per category
   │
   ▼
3. Pushes to Budget_Staging sheet
   - All rows with Status = "pending"
   │
   ▼
4. Sends ntfy notification
   "Budget proposal for May ready for review"
   │
   ▼
5. User reviews in Google Sheets
   - Adjust values as needed
   - Delete rows not wanted
   │
   ▼
6. User clicks "Approve Budget" (web UI)
   - Moves ALL rows from Budget_Staging to Financial_Planning
   - Clears Budget_Staging
   │
   ▼
7. Done! Budget active for the month
```

---

## Flask Component Design

### New Endpoint: `/api/budget/proposal`

**POST** `/api/budget/proposal`
```json
{
  "target_month": "202605"
}
```

Response:
```json
{
  "success": true,
  "rows_created": 24,
  "categories": ["Groceries", "Eating Out", "Fuel", ...]
}
```

### New Page: `/budget`

Simple web UI:
- Month selector (defaults to current month)
- "Generate Proposal" button → calls `/api/budget/proposal`
- Success message with link to Budget_Staging sheet

No approval button here — approval happens via Google Apps Script.

---

## Google Apps Script: Approve Budget

Lives in the Google Sheet. Moves all rows from `Budget Staging` to `Financial_Planning`.

```javascript
function approveBudget() {
  var ss = SpreadsheetApp.getActive();
  var staging = ss.getSheetByName("Budget Staging");
  var planning = ss.getSheetByName("Financial_Planning");

  var source_rows = staging.getDataRange().getValues();

  if (source_rows.length <= 1) {
    return "No rows to approve";
  }

  var rowsToMove = [];
  var header = [["BudgetJoiner", "YearMonth", "Type", "Category", "EstimateValue"]];

  source_rows.forEach(function(row, index) {
    if (index != 0) {
      // Only move rows that have content
      var budgetJoiner = row[0];
      if (budgetJoiner != "") {
        rowsToMove.push(row);
      }
    }
  });

  if (rowsToMove.length > 0) {
    // Append to Financial_Planning
    planning.getRange(planning.getLastRow() + 1, 1, rowsToMove.length, rowsToMove[0].length)
            .setValues(rowsToMove);

    // Clear staging and restore header
    staging.getDataRange().clearContent();
    staging.getRange(1, 1, 1, header[0].length).setValues(header);
  }

  return rowsToMove.length + " rows moved to Financial_Planning";
}

// Web app entry point for mobile trigger
function doGetBudget(e) {
  var token = e.parameter.token;
  if (token !== "YOUR_SECRET_TOKEN") {
    return ContentService.createTextOutput("Unauthorized");
  }
  var result = approveBudget();
  return ContentService.createTextOutput(result);
}
```

Deploy as web app → create iOS Shortcut → tap to approve from anywhere.

---

## Notification

When proposal is generated, send via ntfy:

```
Title: "Budget proposal ready"
Message: "May 2026 budget proposal created with 24 categories. Review and approve."
Priority: default
Tags: clipboard
```

---

## Implementation Checklist

- [ ] Create `Budget_Staging` sheet in Google Sheets (same schema as Financial_Planning)
- [ ] Add `generate_budget_proposal()` function to repository
- [ ] Add `/api/budget/proposal` endpoint in Flask
- [ ] Add `/budget` web page in Flask
- [ ] Add Google Apps Script `approveBudget()` function
- [ ] Deploy Apps Script as web app
- [ ] Create iOS Shortcut for "Approve Budget"
- [ ] Add ntfy notification on proposal creation
- [ ] Add auto-trigger detection in cron_runner (nudge when budget missing for current month)

---

## Future Enhancements

- **Auto-trigger**: Automatically generate proposal when new month detected in cron_runner
- **Historical comparison**: Show "vs last month" and "vs 3-month avg" in staging view
- **Goal setting**: "Reduce Eating Out by 10%" suggestions
- **Seasonal adjustments**: Flag December as typically higher spend
- **Mid-month adjustments**: Allow budget revisions with tracking

---

*Document created: 2026-05-09*
