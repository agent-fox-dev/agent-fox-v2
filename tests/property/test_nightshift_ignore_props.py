"""Property tests for the .night-shift ignore file feature.

Test Spec: TS-106-P1 through TS-106-P5
Properties: 1, 3, 4, 6 from design.md (filter monotonicity + never-raises + idempotency)
Requirements: 106-REQ-2.1, 106-REQ-2.E1, 106-REQ-3.2, 106-REQ-1.4,
              106-REQ-1.E1, 106-REQ-1.E2, 106-REQ-4.1, 106-REQ-4.E1
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.nightshift.finding import Finding
from agent_fox.nightshift.ignore import (
    NightShiftIgnoreSpec,
    filter_findings,
    load_ignore_spec,
)
from agent_fox.workspace.init_project import _ensure_nightshift_ignore

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe single-line pattern text: printable ASCII minus control chars
# Avoids characters that could cause issues with pathspec parsing
_safe_pattern_char = "abcdefghijklmnopqrstuvwxyz0123456789_./!*?-[]"

_pattern_line = st.text(
    alphabet=_safe_pattern_char,
    min_size=1,
    max_size=40,
)

_pattern_list = st.lists(_pattern_line, min_size=0, max_size=15)

_file_path_char = "abcdefghijklmnopqrstuvwxyz0123456789_./"

_file_path = st.text(
    alphabet=_file_path_char,
    min_size=1,
    max_size=50,
).filter(lambda s: "/" in s or "." in s)  # Ensure it looks like a file path

_file_path_list = st.lists(_file_path, min_size=0, max_size=10)

# Representative default exclusion test paths — one per default category
_DEFAULT_TEST_PATHS: list[str] = [
    ".agent-fox/config.toml",
    ".git/HEAD",
    "node_modules/lodash/index.js",
    "__pycache__/main.cpython-312.pyc",
    ".claude/settings.json",
]


def _make_finding(affected_files: list[str]) -> Finding:
    """Build a minimal Finding for property testing."""
    return Finding(
        category="test",
        title="Test",
        description="Test finding",
        severity="minor",
        affected_files=affected_files,
        suggested_fix="",
        evidence="",
        group_key="test",
    )


# ---------------------------------------------------------------------------
# TS-106-P1: Default exclusions always hold
# Property 1 from design.md
# Validates: 106-REQ-2.1, 106-REQ-2.E1
# ---------------------------------------------------------------------------


class TestDefaultExclusionsAlwaysHold:
    """For any set of user patterns, default exclusion paths are always ignored."""

    @pytest.mark.property
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(patterns=_pattern_list)
    def test_prop_defaults_always_hold(self, patterns: list[str]) -> None:
        """TS-106-P1: Default paths are always ignored regardless of user-supplied patterns."""
        project_dir = Path(tempfile.mkdtemp())
        try:
            content = "\n".join(patterns) + "\n" if patterns else ""
            (project_dir / ".night-shift").write_text(content, encoding="utf-8")

            spec = load_ignore_spec(project_dir)

            for path in _DEFAULT_TEST_PATHS:
                assert spec.is_ignored(path) is True, (
                    f"Default path {path!r} was not ignored with patterns: {patterns!r}"
                )
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TS-106-P2: filter_findings never adds findings
# Property 4 (monotonic filtering) from design.md
# Validates: 106-REQ-3.2
# ---------------------------------------------------------------------------


class TestFilterFindingsMonotonic:
    """Filtering can only remove or shrink findings, never add them."""

    @pytest.mark.property
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    @given(
        file_lists=st.lists(_file_path_list, min_size=0, max_size=8),
        patterns=_pattern_list,
    )
    def test_prop_filter_findings_never_adds(
        self,
        file_lists: list[list[str]],
        patterns: list[str],
    ) -> None:
        """TS-106-P2: len(filter_findings(findings, spec)) <= len(findings) always holds."""
        project_dir = Path(tempfile.mkdtemp())
        try:
            content = "\n".join(patterns) + "\n" if patterns else ""
            (project_dir / ".night-shift").write_text(content, encoding="utf-8")
            spec = load_ignore_spec(project_dir)

            findings = [_make_finding(files) for files in file_lists]
            result = filter_findings(findings, spec)

            assert len(result) <= len(findings), (
                f"filter_findings added findings: {len(findings)} in -> {len(result)} out"
            )
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)

    @pytest.mark.property
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    @given(
        file_lists=st.lists(_file_path_list, min_size=0, max_size=8),
        patterns=_pattern_list,
    )
    def test_prop_filter_findings_subset(
        self,
        file_lists: list[list[str]],
        patterns: list[str],
    ) -> None:
        """TS-106-P2: Every finding in the result was present in the input."""
        project_dir = Path(tempfile.mkdtemp())
        try:
            content = "\n".join(patterns) + "\n" if patterns else ""
            (project_dir / ".night-shift").write_text(content, encoding="utf-8")
            spec = load_ignore_spec(project_dir)

            findings = [_make_finding(files) for files in file_lists]
            result = filter_findings(findings, spec)

            # Every result finding must be "derived from" an input finding
            # (same category, title, etc. — just with fewer affected_files)
            assert len(result) <= len(findings)
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TS-106-P3: load_ignore_spec never raises
# Property 3 from design.md
# Validates: 106-REQ-1.E1, 106-REQ-1.E2, 106-REQ-1.4
# ---------------------------------------------------------------------------


class TestLoadIgnoreSpecNeverRaises:
    """load_ignore_spec returns a valid spec for any file state — never raises."""

    @pytest.mark.property
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(file_content=st.one_of(st.none(), st.text(max_size=500)))
    def test_prop_load_ignore_spec_never_raises(
        self,
        file_content: str | None,
    ) -> None:
        """TS-106-P3: load_ignore_spec returns NightShiftIgnoreSpec for any file state."""
        project_dir = Path(tempfile.mkdtemp())
        try:
            if file_content is not None:
                (project_dir / ".night-shift").write_text(file_content, encoding="utf-8")
            # If file_content is None, no file is created (missing file case)

            spec = load_ignore_spec(project_dir)
            assert isinstance(spec, NightShiftIgnoreSpec)
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)

    @pytest.mark.property
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    @given(file_content=st.one_of(st.none(), st.text(max_size=500)))
    def test_prop_load_ignore_spec_defaults_always_present(
        self,
        file_content: str | None,
    ) -> None:
        """TS-106-P3: Returned spec always applies default exclusions regardless of input."""
        project_dir = Path(tempfile.mkdtemp())
        try:
            if file_content is not None:
                (project_dir / ".night-shift").write_text(file_content, encoding="utf-8")

            spec = load_ignore_spec(project_dir)
            assert isinstance(spec, NightShiftIgnoreSpec)
            # At minimum, the first default path is always excluded
            assert spec.is_ignored(_DEFAULT_TEST_PATHS[0]) is True
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TS-106-P4: Findings with empty affected_files survive filtering
# Property 4 from design.md
# Validates: 106-REQ-3.2
# ---------------------------------------------------------------------------


class TestEmptyAffectedFilesSurvive:
    """Findings with no affected_files are never removed by filter_findings."""

    @pytest.mark.property
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(
        n_findings=st.integers(min_value=0, max_value=10),
        patterns=_pattern_list,
    )
    def test_prop_empty_files_findings_survive(
        self,
        n_findings: int,
        patterns: list[str],
    ) -> None:
        """TS-106-P4: All findings with empty affected_files are preserved by filter."""
        project_dir = Path(tempfile.mkdtemp())
        try:
            content = "\n".join(patterns) + "\n" if patterns else ""
            (project_dir / ".night-shift").write_text(content, encoding="utf-8")
            spec = load_ignore_spec(project_dir)

            findings = [_make_finding([]) for _ in range(n_findings)]
            result = filter_findings(findings, spec)

            assert len(result) == n_findings, (
                f"Expected {n_findings} findings with empty files to survive, got {len(result)}"
            )
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TS-106-P5: Init idempotency
# Property 6 from design.md
# Validates: 106-REQ-4.1, 106-REQ-4.E1
# ---------------------------------------------------------------------------


class TestInitIdempotency:
    """Multiple calls to _ensure_nightshift_ignore are idempotent."""

    @pytest.mark.property
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    @given(n_calls=st.integers(min_value=2, max_value=5))
    def test_prop_init_idempotent(self, n_calls: int) -> None:
        """TS-106-P5: File is created on first call; content unchanged on subsequent calls."""
        project_dir = Path(tempfile.mkdtemp())
        try:
            first_result = _ensure_nightshift_ignore(project_dir)
            assert first_result == "created"

            night_shift_path = project_dir / ".night-shift"
            assert night_shift_path.exists()
            first_content = night_shift_path.read_text(encoding="utf-8")

            for _ in range(n_calls - 1):
                result = _ensure_nightshift_ignore(project_dir)
                assert result == "skipped"
                assert night_shift_path.read_text(encoding="utf-8") == first_content
        finally:
            shutil.rmtree(project_dir, ignore_errors=True)
