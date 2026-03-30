# Known Limitations

This document captures acknowledged limitations in the current expense tracking framework. These are not bugs, but areas where the current design makes trade-offs or simplifications.

---

## Transaction Type Terminology

**Current state:** The framework uses "Debt" as a transaction type for money leaving the portfolio.

**Issue:** "Debt" typically implies owing money (loans, credit cards). The more conventional term would be "Expense" for outflows.

**Impact:** May cause confusion when onboarding or explaining the system to others.

**Future fix:** Rename `Debt` → `Expense` across the codebase, configs, and Google Sheets.

---

## Loan Tracking

**Current state:** The framework can track loan *payments* as transactions (categorized under a budget), but does not track the loan itself as a financial instrument.

**What's missing:**
- Remaining principal balance
- Interest paid vs principal paid breakdown
- Amortization schedule tracking
- Total cost of loan over time

**Workaround:** Users manually track loan balances outside the system, or treat payments as simple expenses without decomposition.

**Future consideration:** A dedicated "Liabilities" module could track loans, credit lines, and their payoff progress.

---

## Investment Income Handling

**Current state:** Investment contributions are tracked as `type: Investment` transactions. Returns (dividends, interest, capital gains) are handled by adding a positive-value Investment transaction.

**What's missing:**
- Distinction between contributions vs returns
- Unrealized vs realized gains
- Per-asset or per-fund performance tracking
- Cost basis tracking for tax purposes

**Workaround:** Positive Investment transactions represent "value added" but don't distinguish source.

**Future consideration:** This may require a separate portfolio tracking system rather than extending the expense framework, as investment tracking has fundamentally different concerns (positions, prices, lots).

---

## Transaction Types Overview

For context, the current transaction types and their semantics:

| Type | Meaning | Example |
|------|---------|---------|
| **Income** | Money entering the portfolio | Salary, freelance payment, gift |
| **Debt** (should be Expense) | Money leaving the portfolio | Groceries, rent, subscriptions |
| **Transfer** | Internal movement, net-zero | Checking → Savings, EUR → USD |
| **Investment** | Allocation to volatile products | ETF purchase, stock buy, crypto |

---

*Document created: March 2025*
*Status: Reference document for future improvements*
