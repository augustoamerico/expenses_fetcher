"""
Budget Proposal Generator

Generates budget proposals based on recent spending patterns.
See docs/BUDGET_WIZARD_DESIGN.md for full design.
"""

import logging
from typing import Dict, List, Tuple
from collections import defaultdict

log = logging.getLogger(__name__)


def generate_budget_proposal(
    expenses_summary: List[Dict],
    existing_joiners: List[str],
    target_month: str,
    min_months_threshold: int = 2,
    lookback_months: int = 3,
) -> Tuple[List[List], Dict]:
    """
    Generate a budget proposal for the target month.

    Args:
        expenses_summary: Output from repo.get_expenses_summary_last_n_months()
                         [{"year_month": "202604", "type": "Debt", "category": "Groceries", "total": 150.0}, ...]
        existing_joiners: List of BudgetJoiners already in Financial_Planning for target_month
        target_month: YearMonth to generate budget for (e.g., "202605")
        min_months_threshold: Category must appear in at least this many months (default: 2)
        lookback_months: Number of months in expenses_summary (default: 3)

    Returns:
        Tuple of:
        - List of rows for Budget Staging: [[BudgetJoiner, YearMonth, Type, Category, EstimateValue], ...]
        - Stats dict: {"total_categories": N, "new_categories": M, "skipped_existing": X, "skipped_infrequent": Y}
    """
    # Group expenses by (Type, Category) -> {year_month: total}
    category_by_month = defaultdict(lambda: defaultdict(float))

    for item in expenses_summary:
        key = (item["type"], item["category"])
        category_by_month[key][item["year_month"]] = item["total"]

    # Find the most recent month for each category (for value selection)
    # and count how many months it appeared in
    proposal_rows = []
    stats = {
        "total_categories": 0,
        "new_categories": 0,
        "skipped_existing": 0,
        "skipped_infrequent": 0,
    }

    for (trx_type, category), monthly_totals in category_by_month.items():
        stats["total_categories"] += 1

        # Skip if category doesn't appear in enough months
        months_present = len(monthly_totals)
        if months_present < min_months_threshold:
            log.debug(f"Skipping {trx_type}/{category}: only in {months_present} months")
            stats["skipped_infrequent"] += 1
            continue

        # Build BudgetJoiner
        budget_joiner = f"{target_month}{trx_type}{category}"

        # Skip if already exists in Financial_Planning
        if budget_joiner in existing_joiners:
            log.debug(f"Skipping {budget_joiner}: already exists")
            stats["skipped_existing"] += 1
            continue

        # Get most recent month's value
        most_recent_month = max(monthly_totals.keys())
        estimate_value = monthly_totals[most_recent_month]

        # Add to proposal
        proposal_rows.append([
            budget_joiner,
            target_month,
            trx_type,
            category,
            estimate_value,
        ])
        stats["new_categories"] += 1

    log.info(
        f"Budget proposal for {target_month}: "
        f"{stats['new_categories']} new, "
        f"{stats['skipped_existing']} already exist, "
        f"{stats['skipped_infrequent']} infrequent"
    )

    return proposal_rows, stats
