"""Tests for the budget proposal generator."""

import pytest

from src.application.budget import generate_budget_proposal


class TestGenerateBudgetProposal:
    """Tests for generate_budget_proposal function."""

    def test_empty_expenses_returns_empty_proposal(self):
        """When no expenses, should return empty proposal."""
        rows, stats = generate_budget_proposal(
            expenses_summary=[],
            existing_joiners=[],
            target_month="202605",
        )
        assert rows == []
        assert stats["new_categories"] == 0

    def test_category_in_single_month_is_skipped(self):
        """Category appearing in only 1 month should be skipped (threshold is 2)."""
        expenses = [
            {"year_month": "202604", "type": "Debt", "category": "OneTime", "total": 100.0},
        ]
        rows, stats = generate_budget_proposal(
            expenses_summary=expenses,
            existing_joiners=[],
            target_month="202605",
        )
        assert rows == []
        assert stats["skipped_infrequent"] == 1
        assert stats["new_categories"] == 0

    def test_category_in_two_months_is_included(self):
        """Category appearing in 2+ months should be included."""
        expenses = [
            {"year_month": "202603", "type": "Debt", "category": "Groceries", "total": 100.0},
            {"year_month": "202604", "type": "Debt", "category": "Groceries", "total": 150.0},
        ]
        rows, stats = generate_budget_proposal(
            expenses_summary=expenses,
            existing_joiners=[],
            target_month="202605",
        )
        assert len(rows) == 1
        assert rows[0][0] == "202605DebtGroceries"  # BudgetJoiner
        assert rows[0][1] == "202605"  # YearMonth
        assert rows[0][2] == "Debt"  # Type
        assert rows[0][3] == "Groceries"  # Category
        assert rows[0][4] == 150.0  # Most recent month's value
        assert stats["new_categories"] == 1

    def test_uses_most_recent_month_value(self):
        """Should use the most recent month's value, not average."""
        expenses = [
            {"year_month": "202602", "type": "Debt", "category": "Fuel", "total": 80.0},
            {"year_month": "202603", "type": "Debt", "category": "Fuel", "total": 100.0},
            {"year_month": "202604", "type": "Debt", "category": "Fuel", "total": 120.0},
        ]
        rows, stats = generate_budget_proposal(
            expenses_summary=expenses,
            existing_joiners=[],
            target_month="202605",
        )
        assert len(rows) == 1
        assert rows[0][4] == 120.0  # Most recent (202604)

    def test_existing_budget_is_skipped(self):
        """Category with existing budget should be skipped."""
        expenses = [
            {"year_month": "202603", "type": "Debt", "category": "Rent", "total": 650.0},
            {"year_month": "202604", "type": "Debt", "category": "Rent", "total": 650.0},
        ]
        existing_joiners = ["202605DebtRent"]
        rows, stats = generate_budget_proposal(
            expenses_summary=expenses,
            existing_joiners=existing_joiners,
            target_month="202605",
        )
        assert rows == []
        assert stats["skipped_existing"] == 1
        assert stats["new_categories"] == 0

    def test_multiple_categories_mixed(self):
        """Test with mix of included, skipped, and existing categories."""
        expenses = [
            # Groceries: 2 months, no existing → include
            {"year_month": "202603", "type": "Debt", "category": "Groceries", "total": 100.0},
            {"year_month": "202604", "type": "Debt", "category": "Groceries", "total": 120.0},
            # Rent: 2 months, but already exists → skip
            {"year_month": "202603", "type": "Debt", "category": "Rent", "total": 650.0},
            {"year_month": "202604", "type": "Debt", "category": "Rent", "total": 650.0},
            # OneTime: 1 month only → skip (infrequent)
            {"year_month": "202604", "type": "Debt", "category": "OneTime", "total": 50.0},
            # Investment: 3 months → include
            {"year_month": "202602", "type": "Investment", "category": "ETF", "total": 200.0},
            {"year_month": "202603", "type": "Investment", "category": "ETF", "total": 200.0},
            {"year_month": "202604", "type": "Investment", "category": "ETF", "total": 250.0},
        ]
        existing_joiners = ["202605DebtRent"]
        rows, stats = generate_budget_proposal(
            expenses_summary=expenses,
            existing_joiners=existing_joiners,
            target_month="202605",
        )
        assert len(rows) == 2
        assert stats["new_categories"] == 2
        assert stats["skipped_existing"] == 1
        assert stats["skipped_infrequent"] == 1

        # Verify categories
        joiners = [r[0] for r in rows]
        assert "202605DebtGroceries" in joiners
        assert "202605InvestmentETF" in joiners

    def test_different_types_same_category_treated_separately(self):
        """Same category name in different types should be separate entries."""
        expenses = [
            {"year_month": "202603", "type": "Debt", "category": "Transfer", "total": 100.0},
            {"year_month": "202604", "type": "Debt", "category": "Transfer", "total": 100.0},
            {"year_month": "202603", "type": "Transfer", "category": "Transfer", "total": 500.0},
            {"year_month": "202604", "type": "Transfer", "category": "Transfer", "total": 500.0},
        ]
        rows, stats = generate_budget_proposal(
            expenses_summary=expenses,
            existing_joiners=[],
            target_month="202605",
        )
        assert len(rows) == 2
        joiners = [r[0] for r in rows]
        assert "202605DebtTransfer" in joiners
        assert "202605TransferTransfer" in joiners

    def test_custom_min_months_threshold(self):
        """Should respect custom min_months_threshold."""
        expenses = [
            {"year_month": "202604", "type": "Debt", "category": "Rare", "total": 50.0},
        ]
        # With threshold=1, should be included
        rows, stats = generate_budget_proposal(
            expenses_summary=expenses,
            existing_joiners=[],
            target_month="202605",
            min_months_threshold=1,
        )
        assert len(rows) == 1
        assert stats["new_categories"] == 1
