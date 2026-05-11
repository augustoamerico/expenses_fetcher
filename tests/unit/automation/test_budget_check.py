"""Tests for the budget check logic in cron_runner."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from automation.cron_runner import (
    check_and_handle_budget,
    get_budget_staging_months,
    is_previous_month_closed,
    load_budget_state,
    save_budget_state,
    MONTH_CLOSE_BUFFER_DAYS,
)


class TestLoadSaveBudgetState:
    """Tests for budget state file operations."""

    def test_load_nonexistent_file_returns_empty(self):
        result = load_budget_state("/nonexistent/path.json")
        assert result == {}

    def test_load_and_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "budget_state.json")
            state = {"last_gap_check": "202605"}
            save_budget_state(filepath, state)
            loaded = load_budget_state(filepath)
            assert loaded == state

    def test_load_malformed_json_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "bad.json")
            with open(filepath, "w") as f:
                f.write("not valid json")
            result = load_budget_state(filepath)
            assert result == {}


class TestIsPreviousMonthClosed:
    """Tests for is_previous_month_closed function."""

    def test_returns_true_when_all_accounts_synced_past_threshold(self):
        """All active accounts synced past month end + buffer → closed."""
        mock_repo = MagicMock()
        mock_repo.metadata_sheet_name = "Data"

        # Current month is 202605, previous is 202604
        # Month end is 2026-04-30, threshold is 2026-05-02
        # Last sync dates are 2026-05-03 → past threshold
        mock_repo.get_data.return_value = [
            ["Main", "2026-05-07", "", "2026-05-03 08:00:00"],
            ["RevolutAccount", "2026-05-05", "", "2026-05-03 08:00:00"],
        ]

        result = is_previous_month_closed(mock_repo, "202605")
        assert result is True

    def test_returns_false_when_account_not_synced_past_threshold(self):
        """Account synced before threshold → not closed."""
        mock_repo = MagicMock()
        mock_repo.metadata_sheet_name = "Data"

        # Last sync is 2026-05-01, threshold is 2026-05-02
        mock_repo.get_data.return_value = [
            ["Main", "2026-05-07", "", "2026-05-03 08:00:00"],
            ["RevolutAccount", "2026-05-05", "", "2026-05-01 08:00:00"],  # Before threshold
        ]

        result = is_previous_month_closed(mock_repo, "202605")
        assert result is False

    def test_deactivated_accounts_are_ignored(self):
        """Accounts with Deactivated at Date should be ignored."""
        mock_repo = MagicMock()
        mock_repo.metadata_sheet_name = "Data"

        mock_repo.get_data.return_value = [
            ["Main", "2026-05-07", "", "2026-05-03 08:00:00"],
            ["OldAccount", "2022-01-01", "2022-01-01", "2022-01-01"],  # Deactivated
        ]

        result = is_previous_month_closed(mock_repo, "202605")
        assert result is True

    def test_returns_false_when_no_last_sync_date(self):
        """Account with no Last Sync Date → not closed."""
        mock_repo = MagicMock()
        mock_repo.metadata_sheet_name = "Data"

        mock_repo.get_data.return_value = [
            ["Main", "2026-05-07", "", "2026-05-03 08:00:00"],
            ["NewAccount", "2026-05-05", "", ""],  # No Last Sync Date
        ]

        result = is_previous_month_closed(mock_repo, "202605")
        assert result is False

    def test_handles_january_previous_month(self):
        """Previous month of January should be December of previous year."""
        mock_repo = MagicMock()
        mock_repo.metadata_sheet_name = "Data"

        # Current month is 202601, previous is 202512
        # Month end is 2025-12-31, threshold is 2026-01-02
        mock_repo.get_data.return_value = [
            ["Main", "2026-01-05", "", "2026-01-03 08:00:00"],
        ]

        result = is_previous_month_closed(mock_repo, "202601")
        assert result is True


class TestGetBudgetStagingMonths:
    """Tests for get_budget_staging_months function."""

    def test_returns_unique_months(self):
        mock_repo = MagicMock()
        mock_repo.get_data.return_value = [
            ["202605"],
            ["202605"],
            ["202604"],
        ]

        result = get_budget_staging_months(mock_repo)
        assert result == {"202604", "202605"}

    def test_returns_empty_set_for_empty_staging(self):
        mock_repo = MagicMock()
        mock_repo.get_data.return_value = []

        result = get_budget_staging_months(mock_repo)
        assert result == set()


class TestCheckAndHandleBudget:
    """Tests for check_and_handle_budget state machine."""

    @patch("automation.cron_runner.is_previous_month_closed")
    @patch("automation.cron_runner.datetime")
    def test_nudges_when_previous_month_not_closed_after_3rd(
        self, mock_datetime, mock_is_closed
    ):
        """After 3rd of month, if previous not closed, should nudge."""
        mock_datetime.now.return_value = datetime(2026, 5, 5)  # 5th of May
        mock_is_closed.return_value = False

        mock_repo = MagicMock()
        mock_notifier = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")
            check_and_handle_budget(mock_repo, mock_notifier, state_file)

        mock_notifier.send.assert_called_once()
        call_args = mock_notifier.send.call_args
        assert "not closed" in call_args.kwargs["title"].lower()

    @patch("automation.cron_runner.is_previous_month_closed")
    @patch("automation.cron_runner.get_budget_staging_months")
    @patch("automation.cron_runner.generate_budget_proposal")
    @patch("automation.cron_runner.datetime")
    def test_generates_proposal_when_no_budget_and_no_staging(
        self, mock_datetime, mock_generate, mock_staging, mock_is_closed
    ):
        """When no budget and no staging, should generate proposal."""
        mock_datetime.now.return_value = datetime(2026, 5, 5)
        mock_is_closed.return_value = True
        mock_staging.return_value = set()  # No staging
        mock_generate.return_value = (
            [["202605DebtGroceries", "202605", "Debt", "Groceries", 100.0]],
            {"new_categories": 1, "skipped_existing": 0, "skipped_infrequent": 0},
        )

        mock_repo = MagicMock()
        mock_repo.get_existing_budget_joiners.return_value = []  # No budget
        mock_repo.get_expenses_summary_last_n_months.return_value = []

        mock_notifier = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")
            check_and_handle_budget(mock_repo, mock_notifier, state_file)

        mock_repo.clear_budget_staging.assert_called_once()
        mock_repo.push_budget_staging.assert_called_once()
        mock_notifier.send.assert_called_once()
        assert "proposal ready" in mock_notifier.send.call_args.kwargs["title"].lower()

    @patch("automation.cron_runner.is_previous_month_closed")
    @patch("automation.cron_runner.get_budget_staging_months")
    @patch("automation.cron_runner.datetime")
    def test_nudges_to_approve_when_staging_exists_but_no_budget(
        self, mock_datetime, mock_staging, mock_is_closed
    ):
        """When staging exists but no budget, should nudge to approve."""
        mock_datetime.now.return_value = datetime(2026, 5, 5)
        mock_is_closed.return_value = True
        mock_staging.return_value = {"202605"}  # Has staging

        mock_repo = MagicMock()
        mock_repo.get_existing_budget_joiners.return_value = []  # No budget

        mock_notifier = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")
            check_and_handle_budget(mock_repo, mock_notifier, state_file)

        mock_notifier.send.assert_called_once()
        assert "approve" in mock_notifier.send.call_args.kwargs["title"].lower()

    @patch("automation.cron_runner.is_previous_month_closed")
    @patch("automation.cron_runner.get_budget_staging_months")
    @patch("automation.cron_runner.generate_budget_proposal")
    @patch("automation.cron_runner.datetime")
    def test_checks_gaps_once_when_budget_exists(
        self, mock_datetime, mock_generate, mock_staging, mock_is_closed
    ):
        """When budget exists, should check for gaps once per month."""
        mock_datetime.now.return_value = datetime(2026, 5, 5)
        mock_is_closed.return_value = True
        mock_staging.return_value = set()  # No staging initially
        mock_generate.return_value = (
            [["202605DebtNewCategory", "202605", "Debt", "NewCategory", 50.0]],
            {"new_categories": 1, "skipped_existing": 5, "skipped_infrequent": 0},
        )

        mock_repo = MagicMock()
        mock_repo.get_existing_budget_joiners.return_value = ["202605DebtRent"]  # Has budget
        mock_repo.get_expenses_summary_last_n_months.return_value = []

        mock_notifier = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")

            # First run - should check gaps
            check_and_handle_budget(mock_repo, mock_notifier, state_file)

            assert mock_repo.push_budget_staging.called
            assert "gaps found" in mock_notifier.send.call_args.kwargs["title"].lower()

            # Verify state was saved
            with open(state_file) as f:
                state = json.load(f)
            assert state["last_gap_check"] == "202605"

    @patch("automation.cron_runner.is_previous_month_closed")
    @patch("automation.cron_runner.get_budget_staging_months")
    @patch("automation.cron_runner.generate_budget_proposal")
    @patch("automation.cron_runner.datetime")
    def test_does_not_check_gaps_twice_same_month(
        self, mock_datetime, mock_generate, mock_staging, mock_is_closed
    ):
        """Should not check gaps twice in same month."""
        mock_datetime.now.return_value = datetime(2026, 5, 5)
        mock_is_closed.return_value = True
        mock_staging.return_value = set()

        mock_repo = MagicMock()
        mock_repo.get_existing_budget_joiners.return_value = ["202605DebtRent"]

        mock_notifier = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")
            # Pre-populate state as if gap check already done
            save_budget_state(state_file, {"last_gap_check": "202605"})

            check_and_handle_budget(mock_repo, mock_notifier, state_file)

            # Should not call generate_budget_proposal
            mock_generate.assert_not_called()

    @patch("automation.cron_runner.is_previous_month_closed")
    @patch("automation.cron_runner.get_budget_staging_months")
    @patch("automation.cron_runner.datetime")
    def test_nudges_when_staging_pending_after_gap_check(
        self, mock_datetime, mock_staging, mock_is_closed
    ):
        """After gap check done, if staging still has content, nudge to approve/remove."""
        mock_datetime.now.return_value = datetime(2026, 5, 5)
        mock_is_closed.return_value = True
        mock_staging.return_value = {"202605"}  # Staging has content

        mock_repo = MagicMock()
        mock_repo.get_existing_budget_joiners.return_value = ["202605DebtRent"]  # Has budget

        mock_notifier = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")
            # Gap check already done
            save_budget_state(state_file, {"last_gap_check": "202605"})

            check_and_handle_budget(mock_repo, mock_notifier, state_file)

            mock_notifier.send.assert_called_once()
            assert "staging pending" in mock_notifier.send.call_args.kwargs["title"].lower()
