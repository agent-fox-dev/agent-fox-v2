"""Property-based tests for Claude settings initialization (Spec 17).

Requirements: 17-REQ-1.3, 17-REQ-2.1, 17-REQ-2.2, 17-REQ-2.3
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.workspace.init_project import CANONICAL_PERMISSIONS, _ensure_claude_settings

# Strategy: list of permission strings (mix of canonical + random)
_permission_entry = st.text(
    alphabet=st.sampled_from(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:*()._- "
    ),
    min_size=1,
    max_size=40,
)

_permission_list = st.lists(
    st.one_of(
        st.sampled_from(CANONICAL_PERMISSIONS),
        _permission_entry,
    ),
    max_size=50,
)


@given(existing_perms=_permission_list)
@settings(max_examples=50)
def test_canonical_coverage(existing_perms, tmp_path_factory):
    """TS-17-P1: After running, all canonical entries are present."""
    tmp_path = tmp_path_factory.mktemp("settings")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.local.json"

    data = {"permissions": {"allow": list(existing_perms)}}
    settings_path.write_text(json.dumps(data))

    _ensure_claude_settings(tmp_path)

    result = json.loads(settings_path.read_text())
    result_perms = result["permissions"]["allow"]

    for perm in CANONICAL_PERMISSIONS:
        assert perm in result_perms, f"Missing canonical: {perm}"


@given(existing_perms=_permission_list)
@settings(max_examples=50)
def test_user_entry_preservation(existing_perms, tmp_path_factory):
    """TS-17-P2: No pre-existing entries are removed."""
    tmp_path = tmp_path_factory.mktemp("settings")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.local.json"

    data = {"permissions": {"allow": list(existing_perms)}}
    settings_path.write_text(json.dumps(data))

    _ensure_claude_settings(tmp_path)

    result = json.loads(settings_path.read_text())
    result_perms = result["permissions"]["allow"]

    for perm in existing_perms:
        assert perm in result_perms, f"Lost user entry: {perm}"


@given(existing_perms=_permission_list)
@settings(max_examples=50)
def test_idempotency(existing_perms, tmp_path_factory):
    """TS-17-P3: Running twice produces same result as running once."""
    tmp_path = tmp_path_factory.mktemp("settings")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.local.json"

    data = {"permissions": {"allow": list(existing_perms)}}
    settings_path.write_text(json.dumps(data))

    _ensure_claude_settings(tmp_path)
    after_first = settings_path.read_text()

    _ensure_claude_settings(tmp_path)
    after_second = settings_path.read_text()

    assert after_first == after_second


@given(existing_perms=_permission_list)
@settings(max_examples=50)
def test_order_preservation(existing_perms, tmp_path_factory):
    """TS-17-P4: Existing entries maintain their relative order."""
    tmp_path = tmp_path_factory.mktemp("settings")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.local.json"

    data = {"permissions": {"allow": list(existing_perms)}}
    settings_path.write_text(json.dumps(data))

    _ensure_claude_settings(tmp_path)

    result = json.loads(settings_path.read_text())
    result_perms = result["permissions"]["allow"]

    # The original entries should appear in the same relative order
    original_in_result = [p for p in result_perms if p in existing_perms]
    # Remove duplicates while preserving order for comparison
    seen: set[str] = set()
    deduped_original: list[str] = []
    for p in existing_perms:
        if p not in seen:
            seen.add(p)
            deduped_original.append(p)

    seen_result: set[str] = set()
    deduped_result: list[str] = []
    for p in original_in_result:
        if p not in seen_result:
            seen_result.add(p)
            deduped_result.append(p)

    assert deduped_result == deduped_original
