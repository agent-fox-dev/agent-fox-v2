"""Unit tests for QualityGateCategory.

Test Spec: TS-67-1 through TS-67-11, TS-67-E1 through TS-67-E7
Requirements: 67-REQ-1.1, 67-REQ-1.2, 67-REQ-1.E1, 67-REQ-2.1, 67-REQ-2.2,
              67-REQ-2.3, 67-REQ-2.4, 67-REQ-2.E1, 67-REQ-2.E2, 67-REQ-3.1,
              67-REQ-3.2, 67-REQ-3.3, 67-REQ-3.4, 67-REQ-3.E1, 67-REQ-4.1,
              67-REQ-4.2, 67-REQ-4.3, 67-REQ-4.4, 67-REQ-5.1, 67-REQ-5.2,
              67-REQ-5.3, 67-REQ-6.1, 67-REQ-6.2
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest  # noqa: F401 (used via pytest.mark and pytest.LogCaptureFixture)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(timeout: int = 600) -> MagicMock:
    """Return a mock config with a quality_gate_timeout set."""
    config = MagicMock()
    config.night_shift.quality_gate_timeout = timeout
    return config


def _make_check(name: str, category_str: str, command: list[str] | None = None) -> object:
    """Build a CheckDescriptor for testing."""
    from agent_fox.fix.checks import CheckCategory, CheckDescriptor

    return CheckDescriptor(
        name=name,
        command=command or [name],
        category=CheckCategory(category_str),
    )


def _completed(returncode: int, output: str = "") -> subprocess.CompletedProcess:
    """Build a subprocess.CompletedProcess result."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=output,
    )


def _mock_ai_response(findings_json: str) -> AsyncMock:
    """Return a mock backend whose messages.create returns the given JSON text."""
    mock_backend = AsyncMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=findings_json)]
    mock_backend.messages.create = AsyncMock(return_value=mock_msg)
    return mock_backend


def _single_finding_json(check_name: str) -> str:
    return (
        f'[{{"check_name": "{check_name}", "title": "Failure in {check_name}", '
        f'"description": "Something went wrong", '
        f'"suggested_fix": "Fix it", "affected_files": []}}]'
    )


# ---------------------------------------------------------------------------
# TS-67-1: Detect and Execute Checks
# Requirements: 67-REQ-1.1, 67-REQ-2.1, 67-REQ-2.4
# ---------------------------------------------------------------------------


class TestStaticPhase:
    """Tests for the static phase of QualityGateCategory."""

    @pytest.mark.asyncio
    async def test_detect_calls_detect_checks_and_runs_each(self) -> None:
        """TS-67-1: detect_checks called once; subprocess.run called per check."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        pytest_check = _make_check("pytest", "test", ["uv", "run", "pytest"])
        ruff_check = _make_check("ruff", "lint", ["uv", "run", "ruff", "check", "."])

        with (
            patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[pytest_check, ruff_check],
            ) as mock_detect,
            patch("subprocess.run", return_value=_completed(1, "error details")) as mock_subproc,
        ):
            cat = QualityGateCategory()
            result = await cat._run_static_tool(project_root)

        mock_detect.assert_called_once_with(project_root)
        assert mock_subproc.call_count == 2
        assert "pytest" in result
        assert "ruff" in result

    # TS-67-2: Passing checks excluded from output
    # Requirement: 67-REQ-2.3
    @pytest.mark.asyncio
    async def test_passing_checks_excluded_from_output(self) -> None:
        """TS-67-2: Checks that exit 0 are excluded from static phase output."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        pytest_check = _make_check("pytest", "test", ["pytest"])
        ruff_check = _make_check("ruff", "lint", ["ruff"])

        def side_effect(cmd: list, **kwargs: object) -> subprocess.CompletedProcess:
            if cmd and "pytest" in cmd:
                return _completed(1, "FAILED tests")
            return _completed(0, "")

        with (
            patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[pytest_check, ruff_check],
            ),
            patch("subprocess.run", side_effect=side_effect),
        ):
            cat = QualityGateCategory()
            result = await cat._run_static_tool(project_root)

        assert "pytest" in result
        assert "ruff" not in result


# ---------------------------------------------------------------------------
# TS-67-3: One Finding per Failing Check via AI
# TS-67-4: Finding Evidence Contains Raw Output
# TS-67-5: Group Key Format
# Requirements: 67-REQ-3.1, 67-REQ-3.2, 67-REQ-3.3, 67-REQ-3.4
# ---------------------------------------------------------------------------


class TestAIAnalysis:
    """Tests for the AI analysis phase of QualityGateCategory."""

    @pytest.mark.asyncio
    async def test_one_finding_per_failing_check(self) -> None:
        """TS-67-3: AI phase produces exactly one Finding per failing check."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        pytest_check = _make_check("pytest", "test")
        mypy_check = _make_check("mypy", "type")

        ai_response = (
            '[{"check_name": "pytest", "title": "Tests failing", '
            '"description": "Tests fail", "suggested_fix": "Fix tests", '
            '"affected_files": []}, '
            '{"check_name": "mypy", "title": "Type errors", '
            '"description": "Type issues", "suggested_fix": "Fix types", '
            '"affected_files": []}]'
        )
        mock_backend = _mock_ai_response(ai_response)

        with (
            patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[pytest_check, mypy_check],
            ),
            patch("subprocess.run", return_value=_completed(1, "error")),
        ):
            cat = QualityGateCategory(backend=mock_backend)
            config = _make_config()
            findings = await cat.detect(project_root, config)

        assert len(findings) == 2
        assert all(f.category == "quality_gate" for f in findings)

    @pytest.mark.asyncio
    async def test_finding_evidence_contains_raw_output(self) -> None:
        """TS-67-4: Finding evidence field contains the check's raw output."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        pytest_check = _make_check("pytest", "test")
        raw_output = "FAILED test_foo.py::test_bar - AssertionError"

        mock_backend = _mock_ai_response(_single_finding_json("pytest"))

        with (
            patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[pytest_check],
            ),
            patch("subprocess.run", return_value=_completed(1, raw_output)),
        ):
            cat = QualityGateCategory(backend=mock_backend)
            config = _make_config()
            findings = await cat.detect(project_root, config)

        assert len(findings) == 1
        assert "FAILED test_foo.py::test_bar" in findings[0].evidence

    @pytest.mark.asyncio
    async def test_group_key_format(self) -> None:
        """TS-67-5: Finding group_key is 'quality_gate:{check_name}'."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        pytest_check = _make_check("pytest", "test")

        mock_backend = _mock_ai_response(_single_finding_json("pytest"))

        with (
            patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[pytest_check],
            ),
            patch("subprocess.run", return_value=_completed(1, "error")),
        ):
            cat = QualityGateCategory(backend=mock_backend)
            config = _make_config()
            findings = await cat.detect(project_root, config)

        assert len(findings) == 1
        assert findings[0].group_key == "quality_gate:pytest"


# ---------------------------------------------------------------------------
# TS-67-6: Severity Mapping for Test Category (critical)
# TS-67-7: Severity Mapping for Type Category (major)
# TS-67-8: Severity Mapping for Lint Category (minor)
# Requirements: 67-REQ-4.1, 67-REQ-4.2, 67-REQ-4.3
# ---------------------------------------------------------------------------


class TestSeverityMapping:
    """Tests for severity mapping from check category to Finding severity."""

    async def _run_single_check(self, name: str, category_str: str) -> list:
        """Helper: run one failing check through the full detect() flow."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        check = _make_check(name, category_str)
        mock_backend = _mock_ai_response(_single_finding_json(name))

        with (
            patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[check],
            ),
            patch("subprocess.run", return_value=_completed(1, "failure output")),
        ):
            cat = QualityGateCategory(backend=mock_backend)
            config = _make_config()
            return await cat.detect(Path("/fake/project"), config)

    @pytest.mark.asyncio
    async def test_test_category_is_critical(self) -> None:
        """TS-67-6: Test-category check failure produces critical severity."""
        findings = await self._run_single_check("pytest", "test")
        assert len(findings) == 1
        assert findings[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_type_category_is_major(self) -> None:
        """TS-67-7: Type-category check failure produces major severity."""
        findings = await self._run_single_check("mypy", "type")
        assert len(findings) == 1
        assert findings[0].severity == "major"

    @pytest.mark.asyncio
    async def test_lint_category_is_minor(self) -> None:
        """TS-67-8: Lint-category check failure produces minor severity."""
        findings = await self._run_single_check("ruff", "lint")
        assert len(findings) == 1
        assert findings[0].severity == "minor"


# ---------------------------------------------------------------------------
# TS-67-9: Config Toggle Disables Category
# TS-67-10: Default Timeout Value
# Requirements: 67-REQ-5.1, 67-REQ-5.2
# ---------------------------------------------------------------------------


class TestConfiguration:
    """Tests for quality_gate configuration fields."""

    def test_category_toggle_disables_in_registry(self) -> None:
        """TS-67-9: quality_gate=False disables the category in the registry."""
        from agent_fox.nightshift.hunt import HuntCategoryRegistry

        config = MagicMock()
        config.night_shift.categories.quality_gate = False
        # Enable all other categories so the registry doesn't short-circuit
        for name in [
            "dependency_freshness",
            "todo_fixme",
            "test_coverage",
            "deprecated_api",
            "linter_debt",
            "dead_code",
            "documentation_drift",
        ]:
            setattr(config.night_shift.categories, name, True)

        registry = HuntCategoryRegistry()
        enabled = registry.enabled(config)
        enabled_names = [c.name for c in enabled]
        assert "quality_gate" not in enabled_names

    def test_default_timeout_is_600(self) -> None:
        """TS-67-10: Default quality_gate_timeout is 600 seconds."""
        from agent_fox.core.config import NightShiftConfig

        config = NightShiftConfig()
        assert config.quality_gate_timeout == 600


# ---------------------------------------------------------------------------
# TS-67-11: Category Registration
# Requirements: 67-REQ-6.1, 67-REQ-6.2
# ---------------------------------------------------------------------------


class TestRegistration:
    """Tests for category registration and package export."""

    def test_quality_gate_registered_in_registry(self) -> None:
        """TS-67-11: QualityGateCategory is registered in HuntCategoryRegistry."""
        from agent_fox.nightshift.hunt import HuntCategoryRegistry

        registry = HuntCategoryRegistry()
        names = {cat.name for cat in registry.all()}
        assert "quality_gate" in names

    def test_quality_gate_exportable_from_categories(self) -> None:
        """TS-67-11: QualityGateCategory is importable from the categories package."""
        from agent_fox.nightshift.categories import QualityGateCategory

        assert QualityGateCategory is not None


# ---------------------------------------------------------------------------
# TS-67-E1: detect_checks Raises Exception
# Requirement: 67-REQ-1.E1
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for QualityGateCategory."""

    @pytest.mark.asyncio
    async def test_detect_checks_raises_returns_empty(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-67-E1: OSError from detect_checks produces zero findings with warning."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        with patch(
            "agent_fox.nightshift.categories.quality_gate.detect_checks",
            side_effect=OSError("disk error"),
        ):
            cat = QualityGateCategory()
            config = _make_config()
            with caplog.at_level("WARNING"):
                findings = await cat.detect(project_root, config)

        assert findings == []
        # Either the error message or the category name should appear in the log
        assert any("disk error" in r.message or "quality_gate" in r.message.lower() for r in caplog.records)

    # TS-67-E2: No Checks Detected
    # Requirement: 67-REQ-1.2
    @pytest.mark.asyncio
    async def test_no_checks_detected_returns_empty(self) -> None:
        """TS-67-E2: Empty check list produces zero findings."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        with patch(
            "agent_fox.nightshift.categories.quality_gate.detect_checks",
            return_value=[],
        ):
            cat = QualityGateCategory()
            config = _make_config()
            findings = await cat.detect(project_root, config)

        assert findings == []

    # TS-67-E3: Check Subprocess Timeout
    # Requirement: 67-REQ-2.E1
    @pytest.mark.asyncio
    async def test_subprocess_timeout_recorded_in_output(self) -> None:
        """TS-67-E3: TimeoutExpired is captured as failure with timeout message."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        pytest_check = _make_check("pytest", "test")

        with (
            patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[pytest_check],
            ),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=600),
            ),
        ):
            cat = QualityGateCategory()
            result = await cat._run_static_tool(project_root)

        assert "timeout" in result.lower()

    # TS-67-E4: All Checks Pass (Silent)
    # Requirement: 67-REQ-2.E2
    @pytest.mark.asyncio
    async def test_all_checks_pass_returns_empty(self) -> None:
        """TS-67-E4: All passing checks produce zero findings."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        pytest_check = _make_check("pytest", "test")
        ruff_check = _make_check("ruff", "lint")

        with (
            patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[pytest_check, ruff_check],
            ),
            patch("subprocess.run", return_value=_completed(0, "")),
        ):
            cat = QualityGateCategory()
            config = _make_config()
            findings = await cat.detect(project_root, config)

        assert findings == []

    # TS-67-E5: AI Backend Failure Fallback
    # Requirement: 67-REQ-3.E1
    @pytest.mark.asyncio
    async def test_ai_failure_triggers_mechanical_fallback(self) -> None:
        """TS-67-E5: AI exception produces one mechanical Finding with check name."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        pytest_check = _make_check("pytest", "test")

        mock_backend = AsyncMock()
        mock_backend.messages.create = AsyncMock(side_effect=RuntimeError("AI down"))

        with (
            patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[pytest_check],
            ),
            patch("subprocess.run", return_value=_completed(1, "some failure output")),
        ):
            cat = QualityGateCategory(backend=mock_backend)
            config = _make_config()
            findings = await cat.detect(project_root, config)

        assert len(findings) == 1
        assert "pytest" in findings[0].title.lower()

    # TS-67-E6: AI Returns Unparseable JSON
    # Requirement: 67-REQ-3.E1
    @pytest.mark.asyncio
    async def test_ai_unparseable_json_triggers_fallback(self) -> None:
        """TS-67-E6: Unparseable AI response triggers mechanical fallback."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        project_root = Path("/fake/project")
        pytest_check = _make_check("pytest", "test")

        mock_backend = _mock_ai_response("not valid json at all")

        with (
            patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[pytest_check],
            ),
            patch("subprocess.run", return_value=_completed(1, "some failure output")),
        ):
            cat = QualityGateCategory(backend=mock_backend)
            config = _make_config()
            findings = await cat.detect(project_root, config)

        assert len(findings) == 1

    # TS-67-E7: Timeout Config Clamped
    # Requirement: 67-REQ-5.3
    def test_timeout_below_60_is_clamped(self) -> None:
        """TS-67-E7: quality_gate_timeout below 60 is clamped to 60."""
        from agent_fox.core.config import NightShiftConfig

        config = NightShiftConfig(quality_gate_timeout=10)
        assert config.quality_gate_timeout == 60


# ---------------------------------------------------------------------------
# TS-493-1: Test-file error annotation
# Issue: #493
# ---------------------------------------------------------------------------


class TestTestFileAnnotation:
    """Regression tests for test-file error annotation in quality gate output.

    Issue #493: mypy import-not-found errors in test files (negative tests)
    were misinterpreted as real missing modules.
    """

    def test_annotate_test_file_errors_tags_test_paths(self) -> None:
        """Errors in tests/ paths get the [TEST FILE] annotation."""
        from agent_fox.nightshift.categories.quality_gate import (
            _annotate_test_file_errors,
        )

        output = (
            "tests/unit/security/test_relocation.py:58: error: Cannot find "
            'implementation or library stub for module named "agent_fox.hooks.security"'
            "  [import-not-found]\n"
            "agent_fox/engine/session_lifecycle.py:42: error: Incompatible return "
            "value type  [return-value]\n"
        )
        result = _annotate_test_file_errors(output)

        assert "[TEST FILE — may be intentional]" in result
        # Only the test file line should be annotated
        lines = result.strip().splitlines()
        assert "[TEST FILE" in lines[0]
        assert "[TEST FILE" not in lines[1]

    def test_annotate_preserves_non_test_errors(self) -> None:
        """Errors in non-test paths are not modified."""
        from agent_fox.nightshift.categories.quality_gate import (
            _annotate_test_file_errors,
        )

        output = "agent_fox/core/client.py:10: error: Missing return  [return-value]\n"
        result = _annotate_test_file_errors(output)
        assert result == output

    def test_annotate_handles_empty_output(self) -> None:
        """Empty output is returned unchanged."""
        from agent_fox.nightshift.categories.quality_gate import (
            _annotate_test_file_errors,
        )

        assert _annotate_test_file_errors("") == ""

    def test_format_failures_annotates_type_check_output(self) -> None:
        """_format_failures annotates test-file errors for TYPE checks."""
        from agent_fox.fix.checks import CheckCategory, CheckDescriptor
        from agent_fox.nightshift.categories.quality_gate import _format_failures

        mypy_check = CheckDescriptor(name="mypy", command=["mypy"], category=CheckCategory.TYPE)
        output = "tests/unit/foo.py:10: error: Missing type  [type-arg]\nSome other line\n"
        result = _format_failures([(mypy_check, output, 1)])

        assert "[TEST FILE — may be intentional]" in result

    def test_format_failures_annotates_lint_check_output(self) -> None:
        """_format_failures annotates test-file errors for LINT checks."""
        from agent_fox.fix.checks import CheckCategory, CheckDescriptor
        from agent_fox.nightshift.categories.quality_gate import _format_failures

        ruff_check = CheckDescriptor(name="ruff", command=["ruff"], category=CheckCategory.LINT)
        output = "tests/prop/test_x.py:5: warning: unused import  [F401]\n"
        result = _format_failures([(ruff_check, output, 1)])

        assert "[TEST FILE — may be intentional]" in result

    def test_format_failures_skips_annotation_for_test_checks(self) -> None:
        """_format_failures does NOT annotate TEST-category check output."""
        from agent_fox.fix.checks import CheckCategory, CheckDescriptor
        from agent_fox.nightshift.categories.quality_gate import _format_failures

        pytest_check = CheckDescriptor(name="pytest", command=["pytest"], category=CheckCategory.TEST)
        output = "tests/unit/foo.py:10: error: assert False  [assertion]\n"
        result = _format_failures([(pytest_check, output, 1)])

        assert "[TEST FILE — may be intentional]" not in result


# ---------------------------------------------------------------------------
# TS-493-2: Prompt contains negative-test guidance
# Issue: #493
# ---------------------------------------------------------------------------


class TestPromptGuidance:
    """Verify the quality gate prompt includes negative test guidance."""

    def test_prompt_mentions_pytest_raises(self) -> None:
        """QUALITY_GATE_PROMPT must mention pytest.raises pattern."""
        from agent_fox.nightshift.categories.quality_gate import QUALITY_GATE_PROMPT

        assert "pytest.raises" in QUALITY_GATE_PROMPT

    def test_prompt_mentions_test_file_annotation(self) -> None:
        """QUALITY_GATE_PROMPT must reference the [TEST FILE] tag."""
        from agent_fox.nightshift.categories.quality_gate import QUALITY_GATE_PROMPT

        assert "TEST FILE" in QUALITY_GATE_PROMPT


# ---------------------------------------------------------------------------
# TS-493-3: Critic prompt contains structural false-positive rules
# Issue: #493
# ---------------------------------------------------------------------------


class TestCriticFalsePositiveRules:
    """Verify the critic system prompt includes structural FP patterns."""

    def test_critic_prompt_mentions_import_errors_in_tests(self) -> None:
        """Critic prompt must warn about import errors in test files."""
        from agent_fox.nightshift.critic import _CRITIC_SYSTEM_PROMPT

        assert "import-not-found" in _CRITIC_SYSTEM_PROMPT.lower() or (
            "import error" in _CRITIC_SYSTEM_PROMPT.lower()
            and "test file" in _CRITIC_SYSTEM_PROMPT.lower()
        )

    def test_critic_prompt_mentions_pytest_raises(self) -> None:
        """Critic prompt must reference the pytest.raises pattern."""
        from agent_fox.nightshift.critic import _CRITIC_SYSTEM_PROMPT

        assert "pytest.raises" in _CRITIC_SYSTEM_PROMPT

    def test_critic_prompt_mentions_generated_files(self) -> None:
        """Critic prompt must warn about generated/vendored file FPs."""
        from agent_fox.nightshift.critic import _CRITIC_SYSTEM_PROMPT

        assert "generated" in _CRITIC_SYSTEM_PROMPT.lower() or "vendored" in _CRITIC_SYSTEM_PROMPT.lower()
