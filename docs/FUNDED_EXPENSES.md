# Funded Expenses: Tracking Expenses Covered by Prior Savings

## Problem

### The Scenario

A common personal finance pattern is to allocate money to reserve funds (e.g., HomeEmergencyFund, VacationFund) over time, then draw from those funds when a relevant expense occurs.

Example:
1. **Month A**: Salary arrives → transfer €500 to HomeEmergencyFund
2. **Month B**: Fridge breaks → transfer €750 from HomeEmergencyFund to Main, buy fridge for €750

### The Reporting Problem

In Month B's reports, the €750 fridge expense shows up in "Debt to Budget", but the transfer back from HomeEmergencyFund only shows in the Transfers section. The **Monthly Delta** calculation (Income - Expenses) doesn't account for the fact that this expense was funded by prior savings, not this month's income.

**Result**: The report makes it look like you spent €750 of this month's income, when in reality you spent €0 of new money on the fridge - it was pre-funded.

### What We Want to Know

1. **Total expenses**: Still show the real sum (€750 fridge happened)
2. **Funded by prior savings**: How much of those expenses came from reserve funds
3. **Funded by new money**: How much came from this month's income
4. **True savings rate**: Income minus "Funded by New Money" = actual savings from new income

---

## Solution

### Approach: Separate Funding Records

Introduce a new record type called **Funding** that explicitly links a budget cell to non-new-money sources.

#### Why This Approach?

Several alternatives were considered:

| Approach | Pros | Cons |
|----------|------|------|
| **Link individual transactions** (expense ↔ transfer) | Precise | Complex, timing-dependent, clutters transaction schema |
| **New transaction type "FundedExpense"** | Single record | Loses transfer visibility, changes core model |
| **Treat reserve withdrawals as Income** | Simple | Pollutes Income semantics, hard to distinguish from real income |
| **Add `FundsBudget` field to Transfers** | Reuses existing records | Pollutes Transfers, couples two concepts |
| **Separate Funding record** | Clean separation, flexible timing, explicit intent | One more record type to manage |

**Chosen: Separate Funding record** because:
1. **Decouples timing** - Create expense, transfer, and funding in any order
2. **Keeps other records pure** - Transfers stay "money moved", Expenses stay "money spent"
3. **Explicit intent** - A Funding record clearly declares "this budget cell is covered by prior savings"
4. **Simple reporting** - Join Funding to Budget cells, no complex filtering

---

### Funding Record Schema

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| YearMonth | string | `202508` | Which month this funds |
| Type | string | `Debt` | Transaction type being funded (Debt/Expense) |
| Category | string | `Home Appliances` | Category being funded |
| Value | number | `750` | Amount funded (caps at actual expense) |
| Source | string | `HomeEmergencyFund` | Where the money came from (informational) |

**FundingJoiner** (computed): `YYYYMMTypeCategory` - same format as BudgetJoiner for easy joins.

---

### Workflow Example

#### Scenario: Fridge breaks in August 2025, costs €750

**Step 1: The expense happens**
```
Type: Debt
Category: Home Appliances
Value: €750
YearMonth: 202508
```

**Step 2: Transfer money from reserve fund**
```
Type: Transfer
From: HomeEmergencyFund
To: Main
Value: €750
```

**Step 3: Create Funding record**
```
YearMonth: 202508
Type: Debt
Category: Home Appliances
Value: €750
Source: HomeEmergencyFund
```

Steps can happen in any order. The Funding record is the link that tells reports this expense wasn't from new money.

---

### Handling Edge Cases

#### Under-funded (Expense > Funding)
- Transfer €500, spend €750
- Funding record: €500
- Report: €500 funded by transfer, €250 funded by new money

#### Over-funded (Funding > Expense)
- Transfer €800, spend €750
- Funding record: €750 (cap at actual expense)
- Remaining €50: manually transfer back to reserve fund
- Report: €750 funded by transfer, €0 funded by new money

#### Multiple funding sources for same category
- Transfer €300 from HomeEmergencyFund, €200 from GeneralSavings
- Create two Funding records, both targeting `202508DebtHome Appliances`
- Report sums them: €500 total funded by transfers

---

### Report Calculations

```
For each budget cell (YYYYMMTypeCategory):

  Total Expense     = SUM(Expenses WHERE BudgetJoiner = cell)
  Total Funding     = SUM(Funding WHERE FundingJoiner = cell)

  Funded by Transfer  = MIN(Total Funding, Total Expense)
  Funded by New Money = Total Expense - Funded by Transfer
```

#### Enhanced Monthly Summary

```
Income (new money):           €6,857.30

Expenses (total):             €2,742.56
  - Funded by Transfers:        €750.00
  - Funded by New Money:      €1,992.56

Monthly Delta (accounting):   €4,114.74  ← Income - Total Expenses
Monthly Delta (new money):    €4,864.74  ← Income - Funded by New Money
```

The **"Monthly Delta (new money)"** answers: "How much of this month's income did I actually keep?"

---

### Implementation in Google Sheets

1. **New sheet/tab**: `Funding` with columns matching the schema above
2. **Add FundingJoiner column**: Formula `=CONCAT(CONCAT(CONCAT(A2, B2), C2))` or similar
3. **Update reports**: Join Funding to Budget cells, calculate split metrics

---

## Integration with Automation

This feature is independent of the automation plan (`docs/AUTOMATION_PLAN.md`). The automation pulls transactions from bank APIs and pushes to staging - it doesn't create Funding records.

Funding records are **manual** - you create them when you consciously decide to fund an expense from a reserve fund. This is intentional: the decision to draw from savings is a human choice, not something to automate.

---

*Document created: March 2025*
*Status: Design complete, ready for implementation*
