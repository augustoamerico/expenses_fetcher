# FinBuddy Design Document

## Overview

FinBuddy is a personal finance assistant that provides context-aware insights via mobile. It combines automated data collection with intelligent analysis to help track spending, budgets, and progress toward financial goals.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CURRENT SOLUTION                                   │
│                                                                              │
│  ┌──────────────────┐     ┌─────────────┐     ┌──────────────────┐         │
│  │  Zimaboard       │     │   Banks     │     │     Mobile       │         │
│  │  Server          │◄───►│  (Nordigen) │     │     (You)        │         │
│  │                  │     └─────────────┘     │                  │         │
│  │  • Daily Cron    │                         │  • NTFY alerts   │         │
│  │  • 30min Poller  │     ┌─────────────┐     │  • Review trx    │         │
│  │  • Flask App     │◄───►│   Google    │◄───►│  • Categorize    │         │
│  │                  │     │   Sheets    │     │  • Upload XLSX   │         │
│  │  🐳 Docker       │     └─────────────┘     └──────────────────┘         │
│  └──────────────────┘            │                                          │
│                                  │                                          │
├──────────────────────────────────┼──────────────────────────────────────────┤
│                           FINBUDDY ADDITION                                  │
│                                  │                                          │
│                                  ▼                                          │
│  ┌──────────────────────────────────────────────┐    ┌──────────────────┐  │
│  │              Google Drive                     │    │    FinBuddy     │  │
│  │                                               │    │    (Mobile)     │  │
│  │  ┌─────────────┐  ┌─────────────┐            │    │                  │  │
│  │  │ micro_      │  │ macro_      │            │───►│  Claude or      │  │
│  │  │ context.md  │  │ context.md  │            │    │  ChatGPT with   │  │
│  │  │             │  │             │            │    │  Drive access   │  │
│  │  │ Daily auto  │  │ Monthly     │            │    │                  │  │
│  │  └─────────────┘  └─────────────┘            │    │  "How's my      │  │
│  │                                               │    │   budget?"      │  │
│  │         ┌─────────────┐                      │    │                  │  │
│  │         │ my_goals.md │                      │    │  "Can I afford  │  │
│  │         │             │                      │    │   this €500?"   │  │
│  │         │ Quarterly   │                      │    │                  │  │
│  │         └─────────────┘                      │    └──────────────────┘  │
│  └──────────────────────────────────────────────┘                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Context Files

### 1. micro_context.md (Daily, Auto-generated)

**Source:** Google Sheets Expenses Repository
**Update Frequency:** Daily after cron sync
**Purpose:** Day-to-day spending awareness

**Contents:**
- Current month budget vs actual by category
- Recent transactions (last 7 days)
- Alerts (over budget, near limit)
- Monthly delta (savings)
- Income received vs expected

**When to Generate:**
- After daily cron completes successfully
- Only includes data from "Expenses" sheet (validated transactions)
- "Expenses Staging" is excluded (not yet categorized)

### 2. macro_context.md (Monthly, Manual)

**Source:** Portfolio Performance
**Update Frequency:** Monthly (after PP review)
**Purpose:** Long-term wealth tracking

**Contents:**
- Net worth summary
- Investment allocation
- Performance vs benchmarks
- Retirement/goal projections

**Note:** This is curated manually because:
- PP data requires interpretation
- Macro view shouldn't change daily
- You decide what's relevant to share

### 3. my_goals.md (Quarterly, Manual)

**Source:** You
**Update Frequency:** Quarterly or when life changes
**Purpose:** Anchor for advice and accountability

**Contents:**
- Short-term goals (this quarter/year)
- Long-term goals (5+ years)
- Behavioral intentions ("cook more", "reduce X")
- Constraints ("saving for house", "paying off car")

---

## Nudge System

### Philosophy

The nudge is the **hook**, the conversation is the **value**.

Don't notify for everything. Notify when there's something worth **thinking about** - either a concern or a win.

### Two-Layer Analysis

```
┌─────────────────────────────────────────────────────────────┐
│                    Nudge Decision Engine                     │
│                                                              │
│  Layer 1: Rule-based (fast, catches obvious stuff)          │
│  ─────────────────────────────────────────────────────────  │
│  • Category > 100% budget → ALERT                           │
│  • Category > 80% with 10+ days left → WARNING              │
│  • Large transaction > €300 → FLAG                          │
│  • Negative monthly delta → ALERT                           │
│                                                              │
│  Layer 2: LLM Trend Analysis (finds patterns)               │
│  ─────────────────────────────────────────────────────────  │
│  Input: Current month + previous 3 months + goals           │
│  Output: SKIP or NUDGE with message                         │
│                                                              │
│  Can detect:                                                 │
│  • "Eating Out up 3 months in a row"                        │
│  • "Savings rate improved from 12% to 18%"                  │
│  • "You wanted to reduce Entertainment but it's stable"     │
│  • "Nothing notable this period"                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Nudge Types

| Type | Trigger | Example Message |
|------|---------|-----------------|
| 🔴 Critical | Budget exceeded | "Car at 125% - €55 over budget" |
| ⚠️ Warning | Approaching limit | "Eating Out at 85% with 12 days left" |
| 📈 Trend (bad) | 3+ months increasing | "Groceries up 3 months: €180→€210→€245" |
| 📉 Trend (good) | 3+ months improving | "Transport down 20% vs 3-month avg" |
| 🎉 Win | Milestone reached | "Savings rate hit 20% - best in 6 months!" |
| 🤔 Review | Unusual pattern | "€180 in 'Others' - worth categorizing?" |

### Frequency Rules

- **Max 1 nudge per day** (aggregate if multiple triggers)
- **Critical alerts bypass limit** (budget exceeded, negative delta)
- **Positive nudges max 1 per week** (don't spam celebrations)
- **SKIP if nothing notable** (silence is golden)

---

## Month Closure Logic

A month is considered "closed" and ready for historical analysis when:

### Prerequisites

1. **All Nordigen accounts synced** for that month
   - Verified by: transactions exist with dates in the following month

2. **All transactions categorized**
   - Verified by: no rows in "Expenses Staging" with dates from that month

3. **Budget exists for that month**
   - Verified by: entries in Budgets sheet matching `{YYYYMM}{Type}{Category}` pattern

### What This Enables

- Monthly summary generation
- 3-month trend comparisons
- Historical nudges ("vs last month", "vs 3-month average")

### Manual CSV Accounts

- Typically less relevant for trend analysis
- Often updated less frequently
- Should not block month closure
- Flag if significantly behind: "Manual account X not synced since {date}"

---

## Budget Wizard (TODO)

### The Problem

Budgets are required for meaningful analysis, but:
- Currently set manually in Google Sheets
- No guidance on what's reasonable
- Easy to forget to set for new month
- No way to adjust mid-month

### Proposed Solution: Budget Facilitator

A wizard that helps set budgets based on:

1. **Historical data**: "You spent avg €150 on Groceries last 3 months"
2. **Goals**: "You want to reduce Eating Out by 20%"
3. **Seasonal adjustments**: "December typically 30% higher"
4. **Income changes**: "New salary = more savings capacity?"

### Wizard Flow

```
1. Detect: New month started, no budgets set
   → NTFY: "Time to set April budgets. Tap to start wizard."

2. Show historical averages:
   "Based on Jan-Mar, here are suggested budgets:"

   Category        Avg     Suggested   Your Input
   ─────────────────────────────────────────────
   Groceries       €180    €180        [    ]
   Eating Out      €135    €110 ⬇️     [    ] (goal: reduce)
   Transport       €95     €95         [    ]
   ...

3. Confirm and save to Budgets sheet

4. Mid-month adjustment:
   "Eating Out at 90% on day 15. Adjust budget or stay disciplined?"
```

### Implementation Options

- **Flask web page** (like manual upload)
- **Google Apps Script** (native to Sheets)
- **Conversational via FinBuddy** ("Set my April budgets based on March")

---

## Data Flow

### Daily Sync (Current)

```
08:00  Cron starts
       │
       ├─► Fetch from Nordigen accounts
       ├─► Push to Google Sheets (Staging)
       ├─► Send NTFY summary
       │
08:05  Cron ends
```

### Daily Sync (With FinBuddy)

```
08:00  Cron starts
       │
       ├─► Fetch from Nordigen accounts
       ├─► Push to Google Sheets (Staging)
       │
08:05  Context Generator starts
       │
       ├─► Read Expenses sheet (validated only)
       ├─► Read Budgets sheet
       ├─► Read previous 3 months data
       ├─► Generate micro_context.md
       │
       ├─► Layer 1: Rule-based checks
       │   └─► Any critical alerts? → Immediate NTFY
       │
       ├─► Layer 2: LLM trend analysis
       │   └─► Anything worth nudging? → NTFY with insight
       │
       ├─► Upload micro_context.md to Google Drive
       │
08:06  Done
```

### Month Closure (New)

```
Day 1-3 of new month:
       │
       ├─► Check: Is previous month "closed"?
       │   ├─► All accounts synced?
       │   ├─► All transactions categorized?
       │   └─► Budgets exist?
       │
       ├─► If closed:
       │   ├─► Generate monthly summary
       │   ├─► Archive to historical data
       │   └─► Enable trend comparisons
       │
       └─► If not closed:
           └─► NTFY: "March not closed yet. 5 uncategorized transactions."
```

---

## Implementation Phases

### Phase 1: Context Generation
- [ ] Create `micro_context.md` generator
- [ ] Pull data from Google Sheets API
- [ ] Upload to Google Drive
- [ ] Integrate with daily cron

### Phase 2: Rule-Based Nudges
- [ ] Budget threshold alerts
- [ ] Large transaction flags
- [ ] Monthly delta warnings
- [ ] NTFY integration

### Phase 3: LLM Trend Analysis
- [ ] 3-month historical comparison
- [ ] Goal-aware analysis
- [ ] Smart nudge generation
- [ ] "SKIP if nothing notable" logic

### Phase 4: Month Closure
- [ ] Closure detection logic
- [ ] Monthly summary generation
- [ ] Historical archival
- [ ] Closure reminder nudges

### Phase 5: Budget Wizard
- [ ] Historical average calculation
- [ ] Goal-based suggestions
- [ ] Web UI or conversational interface
- [ ] Mid-month adjustment flow

---

## Open Questions

1. **Where to run LLM analysis?**
   - Local (Ollama)?
   - Claude API (cost per call)?
   - Only on-demand when opening FinBuddy?

2. **Google Drive structure?**
   - Single folder for all context files?
   - Versioning/history of context files?

3. **FinBuddy app choice?**
   - Claude Mobile (has Drive integration)
   - ChatGPT (has Drive integration)
   - Custom Telegram bot (full control)?

4. **Budget wizard location?**
   - Extend Flask app?
   - Google Apps Script?
   - Conversational in FinBuddy?

---

## Related Documentation

- [AUTOMATION_PLAN.md](./AUTOMATION_PLAN.md) - Cron setup, re-auth flow
- [MANUAL_ACCOUNTS_WEB_UI.md](./MANUAL_ACCOUNTS_WEB_UI.md) - Flask app for uploads
- [finbuddy_architecture.excalidraw](./finbuddy_architecture.excalidraw) - Visual diagram
