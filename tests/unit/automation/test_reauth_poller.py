"""Tests for the reauth_poller module."""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from automation.reauth_poller import (
    add_to_history,
    cleanup_old_history,
    load_pending_reauths,
    process_pending_reauths,
    save_pending_reauths,
    update_config_with_sed,
    HISTORY_RETENTION_DAYS,
)


class TestLoadSavePendingReauths:
    def test_load_nonexistent_file_returns_empty(self):
        result = load_pending_reauths("/nonexistent/path.json")
        assert result == {"pending": [], "history": []}

    def test_load_and_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "pending.json")
            data = {
                "pending": [{"requisition_id": "req-123", "account_name": "Test"}],
                "history": [],
            }
            save_pending_reauths(filepath, data)
            loaded = load_pending_reauths(filepath)
            assert loaded == data

    def test_load_malformed_json_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "bad.json")
            with open(filepath, "w") as f:
                f.write("not valid json {{{")
            result = load_pending_reauths(filepath)
            assert result == {"pending": [], "history": []}


class TestCleanupOldHistory:
    def test_removes_entries_older_than_retention(self):
        now = datetime.now(timezone.utc)
        old_date = (now - timedelta(days=HISTORY_RETENTION_DAYS + 1)).isoformat().replace("+00:00", "Z")
        recent_date = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")

        data = {
            "pending": [],
            "history": [
                {"account_name": "Old", "replaced_at": old_date},
                {"account_name": "Recent", "replaced_at": recent_date},
            ],
        }
        cleanup_old_history(data)
        assert len(data["history"]) == 1
        assert data["history"][0]["account_name"] == "Recent"

    def test_keeps_all_recent_entries(self):
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")

        data = {
            "pending": [],
            "history": [
                {"account_name": "A", "replaced_at": recent},
                {"account_name": "B", "replaced_at": recent},
            ],
        }
        cleanup_old_history(data)
        assert len(data["history"]) == 2


class TestAddToHistory:
    def test_adds_entry_with_timestamp(self):
        data = {"pending": [], "history": []}
        add_to_history(data, "MyAccount", "old-id-123", "new-id-456")

        assert len(data["history"]) == 1
        entry = data["history"][0]
        assert entry["account_name"] == "MyAccount"
        assert entry["old_account_id"] == "old-id-123"
        assert entry["new_account_id"] == "new-id-456"
        assert "replaced_at" in entry


class TestUpdateConfigWithSed:
    def test_replaces_account_id_in_yaml(self):
        config_content = """accounts:
  TestAccount:
    type: nordigen-account
    secret_id: ...
    secret_key: ...
    account: 783fhc69-v359-4ab3-b48e-c1391m40ye46
    cache_policy: use_if_fresh
    cache_ttl_hours: 3
    cache_dir: .cache/nordigen
"""
        expected_content = """accounts:
  TestAccount:
    type: nordigen-account
    secret_id: ...
    secret_key: ...
    account: 265ghc69-v359-4ab3-b48e-c1391m40ye46
    cache_policy: use_if_fresh
    cache_ttl_hours: 3
    cache_dir: .cache/nordigen
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.yaml")
            with open(config_path, "w") as f:
                f.write(config_content)

            result = update_config_with_sed(
                config_path,
                "783fhc69-v359-4ab3-b48e-c1391m40ye46",
                "265ghc69-v359-4ab3-b48e-c1391m40ye46",
            )

            assert result is True
            with open(config_path, "r") as f:
                actual_content = f.read()
            assert actual_content == expected_content

    def test_preserves_yaml_comments(self):
        config_content = """# Main config file
accounts:
  TestAccount:
    type: nordigen-account
    # Nordigen credentials
    secret_id: abc123
    secret_key: xyz789
    account: old-account-id  # This is the account ID
    cache_policy: use_if_fresh
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.yaml")
            with open(config_path, "w") as f:
                f.write(config_content)

            result = update_config_with_sed(config_path, "old-account-id", "new-account-id")

            assert result is True
            with open(config_path, "r") as f:
                actual_content = f.read()
            # Comments should be preserved
            assert "# Main config file" in actual_content
            assert "# Nordigen credentials" in actual_content
            assert "# This is the account ID" in actual_content
            assert "new-account-id" in actual_content
            assert "old-account-id" not in actual_content

    def test_returns_false_for_nonexistent_file(self):
        result = update_config_with_sed(
            "/nonexistent/path/config.yaml",
            "old-id",
            "new-id",
        )
        assert result is False


class TestProcessPendingReauths:
    @pytest.fixture
    def temp_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_file = os.path.join(tmpdir, "pending.json")
            config_file = os.path.join(tmpdir, "config.yaml")
            with open(config_file, "w") as f:
                f.write("account_id: old-account-id-123\n")
            yield {"pending": pending_file, "config": config_file, "tmpdir": tmpdir}

    def _make_pending_entry(self, account_name="TestAccount", old_id="old-account-id-123", hours_ago=1):
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=24 - hours_ago)
        return {
            "requisition_id": "req-123",
            "account_name": account_name,
            "old_account_id": old_id,
            "secret_id": "secret-id",
            "secret_key": "secret-key",
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
        }

    @patch("automation.reauth_poller.get_nordigen_token")
    @patch("automation.reauth_poller.get_requisition_status")
    def test_requisition_linked_same_account_id(self, mock_get_req, mock_get_token, temp_files):
        """When requisition is linked and account ID is unchanged."""
        mock_get_token.return_value = "access-token"
        mock_get_req.return_value = {"status": "LN", "accounts": ["old-account-id-123"]}

        entry = self._make_pending_entry()
        save_pending_reauths(temp_files["pending"], {"pending": [entry], "history": []})

        notifier = MagicMock()
        process_pending_reauths(temp_files["pending"], temp_files["config"], notifier)

        # Should be removed from pending
        data = load_pending_reauths(temp_files["pending"])
        assert len(data["pending"]) == 0

        # Notification sent
        notifier.send.assert_called_once()
        assert "unchanged" in notifier.send.call_args[1]["message"].lower()

    @patch("automation.reauth_poller.get_nordigen_token")
    @patch("automation.reauth_poller.get_requisition_status")
    @patch("automation.reauth_poller.update_config_with_sed")
    def test_requisition_linked_new_account_id(self, mock_sed, mock_get_req, mock_get_token, temp_files):
        """When requisition is linked and account ID changed."""
        mock_get_token.return_value = "access-token"
        mock_get_req.return_value = {"status": "LN", "accounts": ["new-account-id-456"]}
        mock_sed.return_value = True

        entry = self._make_pending_entry()
        save_pending_reauths(temp_files["pending"], {"pending": [entry], "history": []})

        notifier = MagicMock()
        process_pending_reauths(temp_files["pending"], temp_files["config"], notifier)

        # Config updated
        mock_sed.assert_called_once_with(temp_files["config"], "old-account-id-123", "new-account-id-456")

        # History recorded
        data = load_pending_reauths(temp_files["pending"])
        assert len(data["pending"]) == 0
        assert len(data["history"]) == 1
        assert data["history"][0]["new_account_id"] == "new-account-id-456"

    @patch("automation.reauth_poller.get_nordigen_token")
    @patch("automation.reauth_poller.get_requisition_status")
    def test_requisition_still_pending(self, mock_get_req, mock_get_token, temp_files):
        """When requisition status is CR (created), keep in pending."""
        mock_get_token.return_value = "access-token"
        mock_get_req.return_value = {"status": "CR", "accounts": []}

        entry = self._make_pending_entry()
        save_pending_reauths(temp_files["pending"], {"pending": [entry], "history": []})

        process_pending_reauths(temp_files["pending"], temp_files["config"], None)

        data = load_pending_reauths(temp_files["pending"])
        assert len(data["pending"]) == 1

    @patch("automation.reauth_poller.get_nordigen_token")
    @patch("automation.reauth_poller.get_requisition_status")
    def test_requisition_expired(self, mock_get_req, mock_get_token, temp_files):
        """When requisition status is EX (expired), remove from pending."""
        mock_get_token.return_value = "access-token"
        mock_get_req.return_value = {"status": "EX", "accounts": []}

        entry = self._make_pending_entry()
        save_pending_reauths(temp_files["pending"], {"pending": [entry], "history": []})

        notifier = MagicMock()
        process_pending_reauths(temp_files["pending"], temp_files["config"], notifier)

        data = load_pending_reauths(temp_files["pending"])
        assert len(data["pending"]) == 0
        notifier.send.assert_called_once()
        assert "expired" in notifier.send.call_args[1]["message"].lower()

    def test_pending_entry_expired_24h(self, temp_files):
        """Entry older than 24h should be removed without API call."""
        now = datetime.now(timezone.utc)
        expired = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")

        entry = self._make_pending_entry()
        entry["expires_at"] = expired
        save_pending_reauths(temp_files["pending"], {"pending": [entry], "history": []})

        notifier = MagicMock()
        process_pending_reauths(temp_files["pending"], temp_files["config"], notifier)

        data = load_pending_reauths(temp_files["pending"])
        assert len(data["pending"]) == 0
        notifier.send.assert_called_once()
        assert "24 hours" in notifier.send.call_args[1]["message"]

    @patch("automation.reauth_poller.get_nordigen_token")
    def test_api_token_failure_keeps_pending(self, mock_get_token, temp_files):
        """When token fetch fails, keep entry for retry."""
        mock_get_token.return_value = None

        entry = self._make_pending_entry()
        save_pending_reauths(temp_files["pending"], {"pending": [entry], "history": []})

        process_pending_reauths(temp_files["pending"], temp_files["config"], None)

        data = load_pending_reauths(temp_files["pending"])
        assert len(data["pending"]) == 1


class TestMultiAccountIbanMatching:
    """Tests for multi-account IBAN matching in reauth_poller."""

    @pytest.fixture
    def temp_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_file = os.path.join(tmpdir, "pending.json")
            config_file = os.path.join(tmpdir, "config.yaml")
            config_content = """accounts:
  Revolut-EUR:
    account: old-eur-id
  Revolut-USD:
    account: old-usd-id
"""
            with open(config_file, "w") as f:
                f.write(config_content)
            yield {"pending": pending_file, "config": config_file, "tmpdir": tmpdir}

    def _make_multi_account_entry(self):
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=23)
        return {
            "requisition_id": "req-multi-123",
            "accounts": [
                {"account_name": "Revolut-EUR", "old_account_id": "old-eur-id", "iban": "LT111111111111111111"},
                {"account_name": "Revolut-USD", "old_account_id": "old-usd-id", "iban": "LT222222222222222222"},
            ],
            "secret_id": "secret-id",
            "secret_key": "secret-key",
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
        }

    @patch("automation.reauth_poller.get_nordigen_token")
    @patch("automation.reauth_poller.get_requisition_status")
    @patch("automation.reauth_poller.get_account_iban")
    @patch("automation.reauth_poller.update_config_with_sed")
    def test_multi_account_iban_matching(self, mock_sed, mock_iban, mock_get_req, mock_get_token, temp_files):
        """Two accounts matched by IBAN, both IDs changed."""
        mock_get_token.return_value = "access-token"
        mock_get_req.return_value = {"status": "LN", "accounts": ["new-eur-id", "new-usd-id"]}
        # Map new IDs to IBANs
        mock_iban.side_effect = lambda acc_id, token: {
            "new-eur-id": "LT111111111111111111",
            "new-usd-id": "LT222222222222222222",
        }.get(acc_id)
        mock_sed.return_value = True

        entry = self._make_multi_account_entry()
        save_pending_reauths(temp_files["pending"], {"pending": [entry], "history": []})

        notifier = MagicMock()
        process_pending_reauths(temp_files["pending"], temp_files["config"], notifier)

        # Both accounts updated
        assert mock_sed.call_count == 2
        mock_sed.assert_any_call(temp_files["config"], "old-eur-id", "new-eur-id")
        mock_sed.assert_any_call(temp_files["config"], "old-usd-id", "new-usd-id")

        # History has both
        data = load_pending_reauths(temp_files["pending"])
        assert len(data["history"]) == 2

    @patch("automation.reauth_poller.get_nordigen_token")
    @patch("automation.reauth_poller.get_requisition_status")
    @patch("automation.reauth_poller.get_account_iban")
    def test_multi_account_ids_unchanged(self, mock_iban, mock_get_req, mock_get_token, temp_files):
        """Two accounts, IDs unchanged."""
        mock_get_token.return_value = "access-token"
        mock_get_req.return_value = {"status": "LN", "accounts": ["old-eur-id", "old-usd-id"]}
        mock_iban.return_value = None  # Not needed when IDs match

        entry = self._make_multi_account_entry()
        save_pending_reauths(temp_files["pending"], {"pending": [entry], "history": []})

        notifier = MagicMock()
        process_pending_reauths(temp_files["pending"], temp_files["config"], notifier)

        # No history (no changes)
        data = load_pending_reauths(temp_files["pending"])
        assert len(data["history"]) == 0
        # Notification about unchanged
        assert notifier.send.called

    @patch("automation.reauth_poller.get_nordigen_token")
    @patch("automation.reauth_poller.get_requisition_status")
    @patch("automation.reauth_poller.get_account_iban")
    def test_multi_account_partial_match(self, mock_iban, mock_get_req, mock_get_token, temp_files):
        """One account matched, one unmatched (IBAN not found)."""
        mock_get_token.return_value = "access-token"
        mock_get_req.return_value = {"status": "LN", "accounts": ["new-eur-id", "new-unknown-id"]}
        mock_iban.side_effect = lambda acc_id, token: {
            "new-eur-id": "LT111111111111111111",
            "new-unknown-id": "LT999999999999999999",  # No match
        }.get(acc_id)

        entry = self._make_multi_account_entry()
        save_pending_reauths(temp_files["pending"], {"pending": [entry], "history": []})

        notifier = MagicMock()
        with patch("automation.reauth_poller.update_config_with_sed", return_value=True):
            process_pending_reauths(temp_files["pending"], temp_files["config"], notifier)

        # Should have notifications for both success and failure
        calls = notifier.send.call_args_list
        messages = [c[1]["message"] for c in calls]
        assert any("updated" in m.lower() or "unchanged" in m.lower() for m in messages)
        assert any("could not match" in m.lower() for m in messages)
