# Transaction Type Guide

This document defines how to categorize transactions by Type in the Google Sheets Expenses Repository. Consistent categorization ensures accurate reporting, budgeting, and trend analysis.

## Overview

| Type | Direction | Purpose |
|------|-----------|---------|
| **Debt** | Money out (-) | Expenses, costs, money leaving your accounts |
| **Income** | Money in (+) | Active earnings from external sources |
| **Investment** | Both directions | Capital allocated to/from investment vehicles |
| **Transfer** | Both directions | Money moving between your own accounts |

---

## Funded Expenses

When an expense is covered by prior savings (not this month's income), create a **Funding record** in the `FundedExpensesCategory` sheet.

> **Funding records exist specifically for money that was saved in prior periods, not new money arriving this period.**

### When to Use
- Withdrawing from a holding account (VacationHolding, EmergencyFund) to pay for something
- Liquidating an investment (fixed deposit, ETF) to cover an expense

### Schema

| YearMonth | Type | Category | Value | Source |
|-----------|------|----------|-------|--------|
| 202604 | Debt | House Maintenance | -482.28 | HouseRenovationHolding |

### Example: Condominium paid from fixed deposit

**In Expenses (2 transactions):**
1. `Debt / House Maintenance / -482.28` — the actual expense
2. `Investment / HouseRenovationHolding / +482.28` — withdrawal from deposit

**In FundedExpensesCategory (1 record):**
- Links the expense to its funding source
- Tells reports: "this expense was pre-funded, not from new income"

---

## Debt (Expenses)

Money leaving your accounts for goods, services, obligations, or taxes.

### When to Use
- Purchasing goods or services
- Paying bills and utilities
- Taxes withheld or paid
- Fees and fines
- Loan payments (interest portion)
- Any cost that reduces your net worth

### Categories

| Category | Examples |
|----------|----------|
| Groceries | Supermarket, food shopping |
| Eating Out | Restaurants, cafes, takeaway |
| Transport | Fuel, tolls, public transport, Uber |
| Car | Maintenance, repairs, insurance, IUC |
| House Energy | Electricity, gas |
| House Utilities | Water, waste |
| House Maintenance | Repairs, supplies |
| House Mortgage | Monthly payment |
| House Tv Net | Internet, TV subscription |
| Mobile Phone | Phone plan |
| TV / Music Stream | Netflix, Spotify, etc. |
| Healthcare | Pharmacy, doctors, medical |
| Cat Healthcare | Vet, pet medical |
| Cat Groceries | Pet food, supplies |
| Physical Activity | Gym, sports |
| Entertainment | Cinema, events, games |
| Clothes | Clothing purchases |
| Gifts | Presents for others |
| Selfcare | Personal care |
| Learning | Courses, books |
| Technologic Asset | Electronics, gadgets |
| Home Office | Office supplies, equipment |
| Others | Uncategorized expenses |
| **Taxes / IRS** | Income tax, withheld taxes (e.g., IMPOSTO IRS IRC) |
| Tolls | Highway tolls |
| Fine | Traffic fines, penalties |
| JointAccount | Shared household expenses |
| CarLoan | Car loan payments |

---

## Income (Active Earnings)

Money entering your accounts from **external sources** as compensation for labor, sales, or benefits.

### When to Use
- Salary and wages
- Freelance/contract payments
- Bonuses
- Reimbursements from third parties
- Government benefits
- Gifts received (money)
- Sale of personal items (non-investment)

### When NOT to Use
- Interest from deposits → use **Investment**
- Dividends → use **Investment**
- Capital gains → use **Investment**
- Money from your own accounts → use **Transfer**

### Categories

| Category | Examples |
|----------|----------|
| Salary | Monthly wage, net pay |
| Healthcare | Reimbursements from health insurance |
| Groceries | Cashback, refunds |
| Others | Miscellaneous income |

---

## Investment (Capital Flows)

Money moving **to or from** investment vehicles. This includes both:
- **Outflows**: Money you allocate to investments
- **Inflows**: Returns, interest, dividends, or withdrawals from investments

### When to Use
- Buying ETFs, stocks, funds
- Fixed-term deposits (Depósito a Prazo)
- PPR contributions
- Investment account top-ups
- **Interest earned from deposits (JUROS)**
- **Dividends received**
- **Selling investments (full amount)**
- Withdrawing from investment accounts

### The Key Principle

> **Investment type tracks money flowing to/from investment vehicles, regardless of whether it's principal or returns.**

This means:
- Deposit interest (JUROS DEPOSITO PRAZO) = `Investment` (+)
- Dividend payment = `Investment` (+)
- Selling €400 of stock = `Investment` (+€400)

The detailed tracking of gains, cost basis, and performance is handled by **Portfolio Performance**, not Google Sheets.

### Categories

| Category | Examples |
|----------|----------|
| Inv::IBKR | Interactive Brokers |
| Inv::XTB | XTB broker |
| Inv::PPRGoldenETF | PPR funds |
| Inv:PPRCasaInvestimento | PPR funds |
| Inv:PPRInvestTendenciasGlobais | PPR funds |
| Inv:DPInvest12M | Fixed deposit |
| Inv:DPActivoBank6M | Fixed deposit |
| Inv:EmergencyFund | Emergency fund |
| VacationHolding | Vacation savings |
| HouseRenovationHolding | House renovation fund |
| Main->InvestingAccount | Transfer to investment account |

---

## Transfer (Internal Movements)

Money moving between **your own accounts**. Does not affect net worth.

### When to Use
- Moving money between checking accounts
- Topping up Revolut from Main
- Moving to/from joint account (internal)
- Rebalancing between accounts

### When NOT to Use
- Sending to investment vehicles → use **Investment**
- Paying someone else → use **Debt**

### Categories

| Category | Examples |
|----------|----------|
| Main->Revolut | Top-up Revolut |
| Revolut->Main | Withdraw from Revolut |
| Main->CheckingAccount | Transfer to secondary account |
| CheckingAccount->Main | Transfer from secondary account |
| EmergencyFund->Main | Withdraw from emergency fund |
| Main->EmergencyFund | Add to emergency fund |

---

## Decision Flowchart

```
Is money leaving or entering your accounts?
│
├─► LEAVING (negative)
│   │
│   ├─► Going to an investment vehicle?
│   │   └─► YES: Investment (-)
│   │   └─► NO: Is it to your own account?
│   │       └─► YES: Transfer
│   │       └─► NO: Debt
│   │
├─► ENTERING (positive)
│   │
│   ├─► Coming from an investment vehicle?
│   │   (interest, dividends, sale proceeds)
│   │   └─► YES: Investment (+)
│   │   └─► NO: Is it from your own account?
│   │       └─► YES: Transfer
│   │       └─► NO: Income
```

---

## Examples

| Transaction | Type | Category | Reasoning |
|-------------|------|----------|-----------|
| Monthly salary | Income | Salary | Active earnings from employer |
| Supermarket purchase | Debt | Groceries | Expense for goods |
| Netflix subscription | Debt | TV / Music Stream | Service expense |
| JUROS DEPOSITO PRAZO | Investment | Inv:DPActivoBank6M | Return from investment |
| IMPOSTO IRS IRC DEPOSITO PRAZO | Debt | Taxes | Tax withheld (expense) |
| Buy VWCE shares | Investment | Inv::IBKR | Capital to investment |
| Sell VWCE shares | Investment | Inv::IBKR | Capital from investment |
| Top-up Revolut | Transfer | Main->Revolut | Internal movement |
| Health insurance reimbursement | Income | Healthcare | Money from third party |
| PPR monthly contribution | Investment | Inv::PPRGoldenETF | Capital to investment |
| Dividend from ETF | Investment | Inv::IBKR | Return from investment |

---

## Notes

### Why Investment Interest ≠ Income

Income should represent **active earnings** - money you receive in exchange for labor or from external parties. Investment returns (interest, dividends, capital gains) are **passive returns on capital** - they're generated by money you've already allocated.

Keeping them separate means:
- "Income" answers: "How much am I earning from work?"
- "Investment" answers: "What's my net flow to/from investments?"
- Portfolio Performance answers: "How are my investments performing?"

### Tax on Investment Returns

Taxes withheld on investment returns (e.g., IMPOSTO IRS IRC DEPOSITO PRAZO) should be categorized as:
- **Type**: Debt
- **Category**: Taxes or IRS

This is a real expense that reduces your net worth, even though it's related to investment activity.

### When in Doubt

1. Follow the money direction
2. Ask: "Is this capital going to/from an investment vehicle?"
3. Ask: "Is this active earnings or passive returns?"
4. Check this guide's examples
5. Be consistent - same transaction type should always be categorized the same way
