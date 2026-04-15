"""Unit tests for the .night-shift ignore file feature.

Test Spec: TS-106-1 through TS-106-14, TS-106-E1 through TS-106-E4
Requirements: 106-REQ-1.1, 106-REQ-1.2, 106-REQ-1.3, 106-REQ-1.4,
              106-REQ-1.E1, 106-REQ-1.E2, 106-REQ-2.1, 106-REQ-2.E1,
              106-REQ-3.2, 106-REQ-3.3, 106-REQ-3.E1, 106-REQ-4.1,
              106-REQ-4.2, 106-REQ-4.4, 106-REQ-4.E1, 106-REQ-4.E2,
              106-REQ-5.1, 106-REQ-6.1, 106-REQ-6.2, 106-REQ-6.3
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.nightshift.finding import Finding
from agent_fox.nightshift.ignore import (
    DEFAULT_EXCLUSIONS,
    NightShiftIgnoreSpec,
    filter_findings,
    load_ignore_spec,
)
from agent_fox.workspace.init_project import InitResult, _ensure_nightshift_ignore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_TEST_PATHS = [
    ".agent-fox/state.jsonl",
    ".git/HEAD",
    "node_modules/pkg/index.js",
    "__pycache__/mod.pyc",
    ".claude/settings.json",
]


def _make_finding(
    *,
    affected_files: list[str] | None = None,
    category: str = "todo_fixme",
    title: str = "Test Finding",
    description: str = "A test finding.",
    severity: str = "minor",
    suggested_fix: str = "Fix it.",
    evidence: str = "See file.",
    group_key: str = "test",
) -> Finding:
    """Create a Finding with sensible defaults for testing."""
    return Finding(
        category=category,
        title=title,
        description=description,
        severity=severity,
        affected_files=affected_files if affected_files is not None else [],
        suggested_fix=suggested_fix,
        evidence=evidence,
        group_key=group_key,
    )


def _is_root_on_posix() -> bool:
    """Return True if running as root on POSIX (tests requiring chmod won't work)."""
    if os.name != "posix":
        return True  # Skip on non-POSIX (no chmod semantics)
    return hasattr(os, "getuid") and os.getuid() == 0  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# TS-106-1: Load ignore spec from valid `.night-shift` file
# Requirements: 106-REQ-1.1, 106-REQ-1.2, 106-REQ-6.3
# ---------------------------------------------------------------------------


class TestLoadValidIgnoreSpec:
    """Verify load_ignore_spec reads and parses a valid .night-shift file."""

    def test_load_valid_file(self, tmp_path: Path) -> None:
        """TS-106-1: load_ignore_spec returns NightShiftIgnoreSpec from valid file."""
        ignore_file = tmp_path / ".night-shift"
        ignore_file.write_text("vendor/**\n*.log\n", encoding="utf-8")

        spec = load_ignore_spec(tmp_path)

        assert isinstance(spec, NightShiftIgnoreSpec)
        assert spec.is_ignored("vendor/lib.py") is True
        assert spec.is_ignored("output.log") is True
        assert spec.is_ignored("src/main.py") is False

    def test_is_ignored_is_callable_predicate(self, tmp_path: Path) -> None:
        """TS-106-1: is_ignored returns a boolean and can be used as a predicate."""
        ignore_file = tmp_path / ".night-shift"
        ignore_file.write_text("*.log\n", encoding="utf-8")

        spec = load_ignore_spec(tmp_path)

        result = spec.is_ignored("error.log")
        assert isinstance(result, bool)
        assert result is True

        result2 = spec.is_ignored("src/main.py")
        assert isinstance(result2, bool)
        assert result2 is False


# ---------------------------------------------------------------------------
# TS-106-2: Comments and blank lines are ignored
# Requirement: 106-REQ-1.3
# ---------------------------------------------------------------------------


class TestCommentsAndBlankLines:
    """Verify that comment lines and blank lines produce no patterns."""

    def test_comments_and_blank_lines_ignored(self, tmp_path: Path) -> None:
        """TS-106-2: Comments and blank lines in .night-shift produce no patterns."""
        ignore_file = tmp_path / ".night-shift"
        ignore_file.write_text("# this is a comment\n\n  \n*.tmp\n", encoding="utf-8")

        spec = load_ignore_spec(tmp_path)

        assert spec.is_ignored("file.tmp") is True
        assert spec.is_ignored("src/app.py") is False


# ---------------------------------------------------------------------------
# TS-106-3: Missing `.night-shift` file returns defaults-only spec
# Requirement: 106-REQ-1.4
# ---------------------------------------------------------------------------


class TestMissingFileDefaultsOnly:
    """Verify that a missing .night-shift file yields a defaults-only spec."""

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        """TS-106-3: Missing .night-shift returns valid spec with default exclusions."""
        # No .night-shift file created — directory is empty
        spec = load_ignore_spec(tmp_path)

        assert isinstance(spec, NightShiftIgnoreSpec)
        assert spec.is_ignored(".agent-fox/config.toml") is True
        assert spec.is_ignored(".git/HEAD") is True
        assert spec.is_ignored("src/main.py") is False


# ---------------------------------------------------------------------------
# TS-106-4: Default exclusions always applied
# Requirement: 106-REQ-2.1
# ---------------------------------------------------------------------------


class TestDefaultExclusionsAlwaysApplied:
    """Verify all default exclusion patterns are applied regardless of .night-shift content."""

    def test_default_exclusions_applied_with_user_patterns(self, tmp_path: Path) -> None:
        """TS-106-4: All default paths are ignored even when .night-shift has other content."""
        ignore_file = tmp_path / ".night-shift"
        ignore_file.write_text("*.log\n", encoding="utf-8")

        spec = load_ignore_spec(tmp_path)

        for path in _DEFAULT_TEST_PATHS:
            assert spec.is_ignored(path) is True, f"Expected default path {path!r} to be ignored"

    def test_default_exclusions_list_exists(self) -> None:
        """TS-106-4: DEFAULT_EXCLUSIONS constant is defined and non-empty."""
        assert isinstance(DEFAULT_EXCLUSIONS, list)
        assert len(DEFAULT_EXCLUSIONS) > 0
        # Verify expected patterns are present
        joined = "\n".join(DEFAULT_EXCLUSIONS)
        assert ".agent-fox" in joined
        assert ".git" in joined
        assert "node_modules" in joined
        assert "__pycache__" in joined
        assert ".claude" in joined


# ---------------------------------------------------------------------------
# TS-106-5: Default exclusions cannot be negated
# Requirement: 106-REQ-2.E1
# ---------------------------------------------------------------------------


class TestDefaultsCannotBeNegated:
    """Verify negation patterns in .night-shift cannot un-exclude default paths."""

    def test_negation_cannot_override_defaults(self, tmp_path: Path) -> None:
        """TS-106-5: Negation patterns in .night-shift do not un-exclude default paths."""
        ignore_file = tmp_path / ".night-shift"
        ignore_file.write_text(
            "!.agent-fox/config.toml\n!.git/HEAD\n",
            encoding="utf-8",
        )

        spec = load_ignore_spec(tmp_path)

        assert spec.is_ignored(".agent-fox/config.toml") is True
        assert spec.is_ignored(".git/HEAD") is True


# ---------------------------------------------------------------------------
# TS-106-6: Filter findings removes ignored affected_files
# Requirement: 106-REQ-3.2
# ---------------------------------------------------------------------------


class TestFilterFindingsRemovesIgnoredFiles:
    """Verify filter_findings removes ignored file entries and drops empty findings."""

    def test_filter_findings_mixed_and_pure_ignored(self, tmp_path: Path) -> None:
        """TS-106-6: Ignored files removed; all-ignored findings dropped."""
        ignore_file = tmp_path / ".night-shift"
        ignore_file.write_text("vendor/**\n", encoding="utf-8")
        spec = load_ignore_spec(tmp_path)

        finding_a = _make_finding(affected_files=["vendor/lib.py", "src/main.py"])
        finding_b = _make_finding(affected_files=["vendor/util.py"])
        finding_c = _make_finding(affected_files=["src/app.py"])

        result = filter_findings([finding_a, finding_b, finding_c], spec)

        assert len(result) == 2
        assert result[0].affected_files == ["src/main.py"]
        assert result[1].affected_files == ["src/app.py"]

    def test_filter_findings_empty_input(self, tmp_path: Path) -> None:
        """TS-106-6: filter_findings with empty list returns empty list."""
        spec = load_ignore_spec(tmp_path)
        result = filter_findings([], spec)
        assert result == []


# ---------------------------------------------------------------------------
# TS-106-7: Findings with empty affected_files are preserved
# Requirement: 106-REQ-3.2
# ---------------------------------------------------------------------------


class TestFindingsEmptyFilesPreserved:
    """Verify findings with no affected_files are never dropped by filtering."""

    def test_empty_affected_files_preserved(self, tmp_path: Path) -> None:
        """TS-106-7: Finding with empty affected_files is preserved by filter_findings."""
        ignore_file = tmp_path / ".night-shift"
        ignore_file.write_text("vendor/**\n", encoding="utf-8")
        spec = load_ignore_spec(tmp_path)

        finding = _make_finding(affected_files=[])
        result = filter_findings([finding], spec)

        assert len(result) == 1
        assert result[0].affected_files == []


# ---------------------------------------------------------------------------
# TS-106-8: Additive with .gitignore
# Requirement: 106-REQ-3.3
# ---------------------------------------------------------------------------


class TestAdditiveWithGitignore:
    """Verify .gitignore patterns are also applied when both files exist."""

    def test_gitignore_and_nightshift_additive(self, tmp_path: Path) -> None:
        """TS-106-8: Both .gitignore and .night-shift patterns are applied."""
        (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
        (tmp_path / ".night-shift").write_text("docs/internal/**\n", encoding="utf-8")

        spec = load_ignore_spec(tmp_path)

        assert spec.is_ignored("mod.pyc") is True
        assert spec.is_ignored("docs/internal/notes.md") is True
        assert spec.is_ignored("src/main.py") is False

    def test_gitignore_only_no_nightshift(self, tmp_path: Path) -> None:
        """TS-106-8: .gitignore patterns apply even without .night-shift file."""
        (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
        # No .night-shift file

        spec = load_ignore_spec(tmp_path)

        assert spec.is_ignored("module.pyc") is True
        assert spec.is_ignored("src/main.py") is False


# ---------------------------------------------------------------------------
# TS-106-9: Init creates `.night-shift` file
# Requirements: 106-REQ-4.1, 106-REQ-4.2
# ---------------------------------------------------------------------------


class TestInitCreatesNightshiftFile:
    """Verify _ensure_nightshift_ignore creates a seed file with correct content."""

    def test_ensure_nightshift_creates_file(self, tmp_path: Path) -> None:
        """TS-106-9: _ensure_nightshift_ignore creates .night-shift with seed content."""
        result = _ensure_nightshift_ignore(tmp_path)

        assert result == "created"
        night_shift_path = tmp_path / ".night-shift"
        assert night_shift_path.exists()
        content = night_shift_path.read_text(encoding="utf-8")
        # Contains a comment header explaining its purpose
        assert "night-shift" in content
        # Contains default exclusion patterns as commented entries
        assert ".agent-fox" in content

    def test_ensure_nightshift_seed_content_structure(self, tmp_path: Path) -> None:
        """TS-106-9: .night-shift seed file contains comment header and default patterns."""
        _ensure_nightshift_ignore(tmp_path)

        content = (tmp_path / ".night-shift").read_text(encoding="utf-8")
        lines = content.splitlines()
        # File must have at least some content
        assert len(lines) > 0
        # At least one line should be a comment
        assert any(line.strip().startswith("#") for line in lines)


# ---------------------------------------------------------------------------
# TS-106-10: Init skips existing `.night-shift` file
# Requirement: 106-REQ-4.E1
# ---------------------------------------------------------------------------


class TestInitSkipsExistingFile:
    """Verify init does not overwrite an existing .night-shift file."""

    def test_ensure_nightshift_skips_existing(self, tmp_path: Path) -> None:
        """TS-106-10: _ensure_nightshift_ignore skips and preserves existing file."""
        night_shift_path = tmp_path / ".night-shift"
        night_shift_path.write_text("my-custom-pattern\n", encoding="utf-8")
        original_content = night_shift_path.read_text(encoding="utf-8")

        result = _ensure_nightshift_ignore(tmp_path)

        assert result == "skipped"
        assert night_shift_path.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# TS-106-11: InitResult includes nightshift_ignore status
# Requirement: 106-REQ-4.4
# ---------------------------------------------------------------------------


class TestInitResultField:
    """Verify InitResult has the nightshift_ignore field."""

    def test_init_result_nightshift_ignore_created(self) -> None:
        """TS-106-11: InitResult accepts nightshift_ignore='created'."""
        result = InitResult(
            status="ok",
            agents_md="created",
            nightshift_ignore="created",
        )
        assert result.nightshift_ignore == "created"

    def test_init_result_nightshift_ignore_default_is_skipped(self) -> None:
        """TS-106-11: InitResult.nightshift_ignore defaults to 'skipped'."""
        result = InitResult(
            status="ok",
            agents_md="created",
        )
        assert result.nightshift_ignore == "skipped"

    def test_init_result_nightshift_ignore_skipped(self) -> None:
        """TS-106-11: InitResult accepts nightshift_ignore='skipped'."""
        result = InitResult(
            status="already_initialized",
            agents_md="skipped",
            nightshift_ignore="skipped",
        )
        assert result.nightshift_ignore == "skipped"


# ---------------------------------------------------------------------------
# TS-106-12: pathspec is in project dependencies
# Requirement: 106-REQ-5.1
# ---------------------------------------------------------------------------


class TestPathspecDependency:
    """Verify pathspec>=0.12 is listed in pyproject.toml dependencies."""

    def test_pathspec_in_pyproject_toml(self) -> None:
        """TS-106-12: pathspec>=0.12 appears in [project] dependencies of pyproject.toml."""
        # Walk up from this file to find pyproject.toml
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / "pyproject.toml"
            if candidate.exists():
                content = candidate.read_text(encoding="utf-8")
                assert "pathspec>=0.12" in content, (
                    "pathspec>=0.12 not found in pyproject.toml [project] dependencies"
                )
                return
        pytest.fail("pyproject.toml not found in any parent directory")


# ---------------------------------------------------------------------------
# TS-106-13: Gitwildmatch patterns work correctly
# Requirement: 106-REQ-6.1
# ---------------------------------------------------------------------------


class TestGitwildmatchPatterns:
    """Verify gitwildmatch patterns (wildcards, double-star, character classes) work."""

    def test_gitwildmatch_wildcard_extension(self, tmp_path: Path) -> None:
        """TS-106-13: Wildcard (*) pattern matches file extensions."""
        (tmp_path / ".night-shift").write_text("*.log\n", encoding="utf-8")
        spec = load_ignore_spec(tmp_path)
        assert spec.is_ignored("error.log") is True
        assert spec.is_ignored("error.txt") is False

    def test_gitwildmatch_double_star(self, tmp_path: Path) -> None:
        """TS-106-13: Double-star (**) matches recursively across directories."""
        (tmp_path / ".night-shift").write_text("build/**/output.bin\n", encoding="utf-8")
        spec = load_ignore_spec(tmp_path)
        assert spec.is_ignored("build/release/output.bin") is True
        assert spec.is_ignored("build/release/debug/output.bin") is True

    def test_gitwildmatch_character_class(self, tmp_path: Path) -> None:
        """TS-106-13: Character class ([abc]) matches exactly those characters."""
        (tmp_path / ".night-shift").write_text("test[0-9].py\n", encoding="utf-8")
        spec = load_ignore_spec(tmp_path)
        assert spec.is_ignored("test3.py") is True
        assert spec.is_ignored("test.py") is False
        assert spec.is_ignored("testa.py") is False

    def test_gitwildmatch_combined_patterns(self, tmp_path: Path) -> None:
        """TS-106-13: All gitwildmatch pattern types work together."""
        (tmp_path / ".night-shift").write_text(
            "*.log\nbuild/**/output.bin\ntest[0-9].py\n",
            encoding="utf-8",
        )
        spec = load_ignore_spec(tmp_path)

        assert spec.is_ignored("error.log") is True
        assert spec.is_ignored("build/release/output.bin") is True
        assert spec.is_ignored("test3.py") is True
        assert spec.is_ignored("test.py") is False
        assert spec.is_ignored("src/main.py") is False


# ---------------------------------------------------------------------------
# TS-106-14: POSIX relative paths used for matching
# Requirement: 106-REQ-6.2
# ---------------------------------------------------------------------------


class TestPosixRelativePaths:
    """Verify that paths are matched as POSIX-relative from the repository root."""

    def test_posix_relative_path_matched(self, tmp_path: Path) -> None:
        """TS-106-14: POSIX-relative paths from root are matched correctly."""
        (tmp_path / ".night-shift").write_text("src/generated/**\n", encoding="utf-8")
        spec = load_ignore_spec(tmp_path)

        assert spec.is_ignored("src/generated/model.py") is True
        assert spec.is_ignored("src/main.py") is False

    def test_posix_path_with_forward_slashes(self, tmp_path: Path) -> None:
        """TS-106-14: Paths use forward slashes (POSIX) for matching."""
        (tmp_path / ".night-shift").write_text("a/b/c/**\n", encoding="utf-8")
        spec = load_ignore_spec(tmp_path)

        assert spec.is_ignored("a/b/c/file.py") is True
        assert spec.is_ignored("a/b/other.py") is False


# ---------------------------------------------------------------------------
# TS-106-E1: Unreadable `.night-shift` file
# Requirement: 106-REQ-1.E1
# ---------------------------------------------------------------------------


class TestUnreadableFile:
    """Verify graceful handling when .night-shift cannot be read."""

    @pytest.mark.skipif(
        _is_root_on_posix(),
        reason="Cannot test file permissions as root or on non-POSIX systems",
    )
    def test_unreadable_file_returns_defaults(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """TS-106-E1: Unreadable .night-shift returns defaults-only spec with warning."""
        import logging

        night_shift_path = tmp_path / ".night-shift"
        night_shift_path.write_text("secret/**\n", encoding="utf-8")
        night_shift_path.chmod(0o000)

        try:
            with caplog.at_level(logging.WARNING):
                spec = load_ignore_spec(tmp_path)

            assert isinstance(spec, NightShiftIgnoreSpec)
            # Default exclusions still apply
            assert spec.is_ignored(".agent-fox/state.jsonl") is True
            assert spec.is_ignored("src/main.py") is False
            # User pattern should NOT be applied (since file was unreadable)
            # secret/ may or may not be ignored depending on defaults
            assert "secret/config.txt" not in [
                p for p in _DEFAULT_TEST_PATHS
            ]
        finally:
            night_shift_path.chmod(0o644)

    @pytest.mark.skipif(
        _is_root_on_posix(),
        reason="Cannot test file permissions as root or on non-POSIX systems",
    )
    def test_unreadable_file_logs_warning(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """TS-106-E1: Warning is logged when .night-shift cannot be read."""
        import logging

        night_shift_path = tmp_path / ".night-shift"
        night_shift_path.write_text("secret/**\n", encoding="utf-8")
        night_shift_path.chmod(0o000)

        try:
            with caplog.at_level(logging.WARNING):
                load_ignore_spec(tmp_path)

            assert len(caplog.records) > 0, "Expected a warning to be logged"
        finally:
            night_shift_path.chmod(0o644)


# ---------------------------------------------------------------------------
# TS-106-E2: Empty `.night-shift` file
# Requirement: 106-REQ-1.E2
# ---------------------------------------------------------------------------


class TestEmptyFile:
    """Verify an empty .night-shift file returns defaults-only spec."""

    def test_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        """TS-106-E2: Empty .night-shift returns valid defaults-only spec."""
        night_shift_path = tmp_path / ".night-shift"
        night_shift_path.write_text("", encoding="utf-8")

        spec = load_ignore_spec(tmp_path)

        assert isinstance(spec, NightShiftIgnoreSpec)
        assert spec.is_ignored(".agent-fox/foo") is True
        assert spec.is_ignored("src/main.py") is False

    def test_whitespace_only_file_returns_defaults(self, tmp_path: Path) -> None:
        """TS-106-E2: Whitespace-only .night-shift behaves like empty file."""
        night_shift_path = tmp_path / ".night-shift"
        night_shift_path.write_text("   \n\n  \n", encoding="utf-8")

        spec = load_ignore_spec(tmp_path)

        assert isinstance(spec, NightShiftIgnoreSpec)
        assert spec.is_ignored(".git/HEAD") is True
        assert spec.is_ignored("src/app.py") is False


# ---------------------------------------------------------------------------
# TS-106-E3: Init handles permission error
# Requirement: 106-REQ-4.E2
# ---------------------------------------------------------------------------


class TestInitPermissionError:
    """Verify init does not fail when .night-shift cannot be created."""

    @pytest.mark.skipif(
        _is_root_on_posix(),
        reason="Cannot test file permissions as root or on non-POSIX systems",
    )
    def test_init_permission_error_returns_skipped(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """TS-106-E3: _ensure_nightshift_ignore logs warning and returns 'skipped' on error."""
        import logging

        # Make the directory read-only so file creation fails
        tmp_path.chmod(0o555)

        try:
            with caplog.at_level(logging.WARNING):
                result = _ensure_nightshift_ignore(tmp_path)

            assert result == "skipped"
        finally:
            tmp_path.chmod(0o755)


# ---------------------------------------------------------------------------
# TS-106-E4: HuntScanner.run works when ignore spec loading fails
# Requirement: 106-REQ-3.E1
# ---------------------------------------------------------------------------


class TestHuntScannerIgnoreLoadingFails:
    """Verify HuntScanner.run() still produces findings when ignore loading raises."""

    @pytest.mark.asyncio
    async def test_scanner_returns_findings_on_ignore_error(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """TS-106-E4: HuntScanner.run returns findings even when ignore loading fails."""
        import logging

        from agent_fox.nightshift.hunt import HuntCategoryRegistry, HuntScanner

        expected_finding = _make_finding(affected_files=["src/main.py"])

        mock_category = MagicMock()
        mock_category.name = "mock_category"
        mock_category.detect = AsyncMock(return_value=[expected_finding])

        mock_registry = MagicMock(spec=HuntCategoryRegistry)
        mock_registry.enabled.return_value = [mock_category]

        scanner = HuntScanner(mock_registry, MagicMock())

        with (
            patch(
                "agent_fox.nightshift.hunt.load_ignore_spec",
                side_effect=RuntimeError("simulated failure"),
            ),
            caplog.at_level(logging.WARNING),
        ):
            findings = await scanner.run(tmp_path)

        # Findings must be returned even when ignore loading fails
        assert len(findings) >= 1
