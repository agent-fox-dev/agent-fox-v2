"""Property tests for QualityGateCategory.

Test Spec: TS-67-P1 through TS-67-P6
Properties: 1-6 from design.md
Requirements: 67-REQ-1.2, 67-REQ-2.3, 67-REQ-2.E2, 67-REQ-3.2,
              67-REQ-3.E1, 67-REQ-4.1, 67-REQ-4.2, 67-REQ-4.3, 67-REQ-4.4,
              67-REQ-5.3
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import assume, given, settings
from hypothesis import strategies as st

_PROJECT_ROOT = Path("/fake/project")

_CATEGORY_STRINGS = ["test", "lint", "type", "build"]

_SEVERITY_MAP = {
    "test": "critical",
    "build": "critical",
    "type": "major",
    "lint": "minor",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(timeout: int = 600) -> MagicMock:
    config = MagicMock()
    config.night_shift.quality_gate_timeout = timeout
    return config


def _completed(returncode: int, output: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=output)


def _make_check(name: str, category_str: str) -> object:
    from agent_fox.fix.checks import CheckCategory, CheckDescriptor

    return CheckDescriptor(
        name=name,
        command=[name],
        category=CheckCategory(category_str),
    )


def _mock_backend_with_response(response_text: str) -> AsyncMock:
    mock_backend = AsyncMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=response_text)]
    mock_backend.messages.create = AsyncMock(return_value=mock_msg)
    return mock_backend


def _build_ai_response(checks: list, booleans: list[bool]) -> str:
    """Build a JSON AI response for the failing checks."""
    failing = [ch for ch, fail in zip(checks, booleans) if fail]
    items = [
        f'{{"check_name": "{ch.name}", "title": "Failure", '
        f'"description": "Desc", "suggested_fix": "Fix", "affected_files": []}}'
        for ch in failing
    ]
    return f"[{', '.join(items)}]"


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Use simple alphanumeric names to avoid command injection or weird path issues
_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=1,
    max_size=12,
)

_category_strategy = st.sampled_from(_CATEGORY_STRINGS)


@st.composite
def _check_descriptor_strategy(draw: st.DrawFn) -> object:
    name = draw(_name_strategy)
    cat = draw(_category_strategy)
    return _make_check(name, cat)


# ---------------------------------------------------------------------------
# TS-67-P1: Silent on Green
# Requirements: 67-REQ-2.E2, 67-REQ-2.3
# ---------------------------------------------------------------------------


class TestSilentOnGreen:
    @given(checks=st.lists(_check_descriptor_strategy(), min_size=1, max_size=10))
    @settings(max_examples=20)
    def test_all_passing_produces_zero_findings(self, checks: list) -> None:
        """TS-67-P1: If all checks pass, zero findings are produced."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        config = _make_config()

        async def run() -> list:
            with (
                patch(
                    "agent_fox.nightshift.categories.quality_gate.detect_checks",
                    return_value=checks,
                ),
                patch("subprocess.run", return_value=_completed(0)),
            ):
                cat = QualityGateCategory()
                return await cat.detect(_PROJECT_ROOT, config)

        findings = asyncio.run(run())
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# TS-67-P2: One Finding per Failure
# Requirements: 67-REQ-3.2
# ---------------------------------------------------------------------------


class TestOneFindingPerFailure:
    @given(
        checks=st.lists(_check_descriptor_strategy(), min_size=1, max_size=8),
        fail_flags=st.data(),
    )
    @settings(max_examples=20)
    def test_finding_count_equals_failing_check_count(self, checks: list, fail_flags: st.DataObject) -> None:
        """TS-67-P2: Number of findings equals number of failing checks."""
        booleans = fail_flags.draw(st.lists(st.booleans(), min_size=len(checks), max_size=len(checks)))
        k = sum(booleans)
        assume(k > 0)

        config = _make_config()

        # subprocess.run side_effect: return results in order of checks
        subprocess_results = [_completed(1, "fail") if fail else _completed(0) for fail in booleans]

        ai_response = _build_ai_response(checks, booleans)
        mock_backend = _mock_backend_with_response(ai_response)

        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        async def run() -> list:
            with (
                patch(
                    "agent_fox.nightshift.categories.quality_gate.detect_checks",
                    return_value=checks,
                ),
                patch("subprocess.run", side_effect=subprocess_results),
            ):
                cat = QualityGateCategory(backend=mock_backend)
                return await cat.detect(_PROJECT_ROOT, config)

        findings = asyncio.run(run())
        assert len(findings) == k


# ---------------------------------------------------------------------------
# TS-67-P3: Severity Mapping Consistency
# Requirements: 67-REQ-4.1, 67-REQ-4.2, 67-REQ-4.3, 67-REQ-4.4
# ---------------------------------------------------------------------------


class TestSeverityMappingConsistency:
    @given(cat_str=st.sampled_from(_CATEGORY_STRINGS))
    @settings(max_examples=10)
    def test_severity_always_matches_category(self, cat_str: str) -> None:
        """TS-67-P3: Severity always matches the check category mapping."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        check = _make_check("mycheck", cat_str)
        config = _make_config()

        ai_response = (
            '[{"check_name": "mycheck", "title": "T", "description": "D", "suggested_fix": "F", "affected_files": []}]'
        )
        mock_backend = _mock_backend_with_response(ai_response)

        async def run() -> list:
            with (
                patch(
                    "agent_fox.nightshift.categories.quality_gate.detect_checks",
                    return_value=[check],
                ),
                patch("subprocess.run", return_value=_completed(1, "failure")),
            ):
                cat = QualityGateCategory(backend=mock_backend)
                return await cat.detect(_PROJECT_ROOT, config)

        findings = asyncio.run(run())
        assert len(findings) == 1
        expected_severity = _SEVERITY_MAP[cat_str]
        assert findings[0].severity == expected_severity


# ---------------------------------------------------------------------------
# TS-67-P4: Graceful Degradation
# Requirements: 67-REQ-3.E1
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    @given(checks=st.lists(_check_descriptor_strategy(), min_size=1, max_size=5))
    @settings(max_examples=15)
    def test_ai_failure_never_causes_zero_findings(self, checks: list) -> None:
        """TS-67-P4: AI failure never produces zero findings when checks fail."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        config = _make_config()
        mock_backend = AsyncMock()
        mock_backend.messages.create = AsyncMock(side_effect=RuntimeError("AI down"))

        async def run() -> list:
            with (
                patch(
                    "agent_fox.nightshift.categories.quality_gate.detect_checks",
                    return_value=checks,
                ),
                patch("subprocess.run", return_value=_completed(1, "failure")),
            ):
                cat = QualityGateCategory(backend=mock_backend)
                return await cat.detect(_PROJECT_ROOT, config)

        findings = asyncio.run(run())
        assert len(findings) == len(checks)


# ---------------------------------------------------------------------------
# TS-67-P5: No Findings Without Checks
# Requirements: 67-REQ-1.2
# ---------------------------------------------------------------------------


class TestNoFindingsWithoutChecks:
    def test_empty_check_list_yields_no_findings(self) -> None:
        """TS-67-P5: Empty check list always yields empty findings."""
        from agent_fox.nightshift.categories.quality_gate import QualityGateCategory

        config = _make_config()

        async def run() -> list:
            with patch(
                "agent_fox.nightshift.categories.quality_gate.detect_checks",
                return_value=[],
            ):
                cat = QualityGateCategory()
                return await cat.detect(_PROJECT_ROOT, config)

        findings = asyncio.run(run())
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# TS-67-P6: Timeout Clamping
# Requirements: 67-REQ-5.3
# ---------------------------------------------------------------------------


class TestTimeoutClamping:
    @given(timeout=st.integers(min_value=0, max_value=10000))
    @settings(max_examples=30)
    def test_timeout_always_at_least_60(self, timeout: int) -> None:
        """TS-67-P6: Config timeout values are always >= 60 after validation."""
        from agent_fox.core.config import NightShiftConfig

        config = NightShiftConfig(quality_gate_timeout=timeout)
        assert config.quality_gate_timeout >= 60
