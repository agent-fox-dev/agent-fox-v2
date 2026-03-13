"""Unit tests for Claude settings initialization (Spec 17).

Requirements: 17-REQ-1.1, 17-REQ-1.2, 17-REQ-1.3, 17-REQ-1.E1,
              17-REQ-2.1, 17-REQ-2.2, 17-REQ-2.3,
              17-REQ-2.E1, 17-REQ-2.E2, 17-REQ-2.E3
"""

from __future__ import annotations

import json

import pytest

from agent_fox.cli.init import CANONICAL_PERMISSIONS, _ensure_claude_settings


class TestCreateSettings:
    """TS-17-1: Create settings file when absent."""

    def test_creates_settings_file(self, tmp_path):
        _ensure_claude_settings(tmp_path)

        settings_path = tmp_path / ".claude" / "settings.local.json"
        assert settings_path.exists()

        data = json.loads(settings_path.read_text())
        assert set(data["permissions"]["allow"]) == set(CANONICAL_PERMISSIONS)

    def test_creates_claude_directory(self, tmp_path):
        """TS-17-2: Create .claude/ directory when absent."""
        _ensure_claude_settings(tmp_path)

        assert (tmp_path / ".claude").is_dir()

    def test_file_is_valid_json_with_indent(self, tmp_path):
        _ensure_claude_settings(tmp_path)

        settings_path = tmp_path / ".claude" / "settings.local.json"
        raw = settings_path.read_text()
        assert raw.endswith("\n")
        data = json.loads(raw)
        assert isinstance(data, dict)


class TestMergeSettings:
    """TS-17-3: Merge missing entries into existing file."""

    def test_adds_missing_canonical_entries(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"

        existing = {"permissions": {"allow": ["Read", "Write"]}}
        settings_path.write_text(json.dumps(existing))

        _ensure_claude_settings(tmp_path)

        data = json.loads(settings_path.read_text())
        allow = data["permissions"]["allow"]
        for perm in CANONICAL_PERMISSIONS:
            assert perm in allow

    def test_preserves_user_entries(self, tmp_path):
        """TS-17-4: Preserve user-added entries."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"

        user_entry = "Bash(custom-tool:*)"
        existing = {"permissions": {"allow": [user_entry, "Read"]}}
        settings_path.write_text(json.dumps(existing))

        _ensure_claude_settings(tmp_path)

        data = json.loads(settings_path.read_text())
        assert user_entry in data["permissions"]["allow"]

    def test_preserves_ordering(self, tmp_path):
        """TS-17-5: Preserve ordering of existing entries."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"

        ordered = ["Write", "Read", "Glob"]
        existing = {"permissions": {"allow": ordered}}
        settings_path.write_text(json.dumps(existing))

        _ensure_claude_settings(tmp_path)

        data = json.loads(settings_path.read_text())
        allow = data["permissions"]["allow"]
        # First entries should be preserved in order
        assert allow[:3] == ordered


class TestEdgeCases:
    """Edge case tests for claude settings."""

    def test_noop_when_all_present(self, tmp_path):
        """TS-17-E1: No-op when all canonical entries present."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"

        full = {"permissions": {"allow": list(CANONICAL_PERMISSIONS)}}
        content = json.dumps(full, indent=2) + "\n"
        settings_path.write_text(content)

        _ensure_claude_settings(tmp_path)

        # File should be unchanged
        assert settings_path.read_text() == content

    def test_invalid_json_warns_and_skips(self, tmp_path, caplog):
        """TS-17-E2: Invalid JSON logs warning and skips."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"
        settings_path.write_text("{broken json")

        _ensure_claude_settings(tmp_path)

        # File should not be modified
        assert settings_path.read_text() == "{broken json"
        assert "Invalid JSON" in caplog.text

    def test_missing_permissions_created(self, tmp_path):
        """TS-17-E3: Missing permissions structure is created."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"
        settings_path.write_text(json.dumps({"other_key": "value"}))

        _ensure_claude_settings(tmp_path)

        data = json.loads(settings_path.read_text())
        assert "permissions" in data
        assert "allow" in data["permissions"]
        for perm in CANONICAL_PERMISSIONS:
            assert perm in data["permissions"]["allow"]
        # Existing key preserved
        assert data["other_key"] == "value"

    def test_allow_not_list_warns_and_skips(self, tmp_path, caplog):
        """TS-17-E4: permissions.allow not a list logs warning and skips."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"
        original = json.dumps({"permissions": {"allow": "not-a-list"}})
        settings_path.write_text(original)

        _ensure_claude_settings(tmp_path)

        assert settings_path.read_text() == original
        assert "not a list" in caplog.text


@pytest.fixture()
def caplog(caplog):
    """Enable log capture at DEBUG level for agent_fox.cli.init."""
    import logging

    caplog.set_level(logging.DEBUG, logger="agent_fox.cli.init")
    return caplog
