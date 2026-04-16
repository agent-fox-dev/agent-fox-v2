"""Unit tests for AI fix pipeline wiring dispatch logic.

Test Spec: TS-109-1 through TS-109-13, TS-109-E1 through TS-109-E7
Requirements: 109-REQ-1.*, 109-REQ-2.*, 109-REQ-3.*, 109-REQ-4.*, 109-REQ-5.*
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.fixers.types import FixResult
from agent_fox.spec.validators import SEVERITY_HINT, Finding

# -- Patch targets ---------------------------------------------------------------

_MOCK_REWRITE = "agent_fox.spec.ai_validation.rewrite_criteria"
_MOCK_GENERATE = "agent_fox.spec.ai_validation.generate_test_spec_entries"
_MOCK_FIX_AI = "agent_fox.spec.fixers.ai.fix_ai_criteria"
_MOCK_FIX_TS = "agent_fox.spec.fixers.ai.fix_ai_test_spec_entries"
_MOCK_APPLY_AI = "agent_fox.spec.lint._apply_ai_fixes"
_MOCK_APPLY_FIXES = "agent_fox.spec.fixers.runner.apply_fixes"
_MOCK_VALIDATE = "agent_fox.spec.lint.validate_specs"
_MOCK_MERGE_AI = "agent_fox.spec.lint._merge_ai_findings"


# -- Helpers ---------------------------------------------------------------------


def _make_finding(
    spec_name: str = "01_test",
    rule: str = "vague-criterion",
    criterion_id: str = "01-REQ-1.1",
    message: str | None = None,
) -> Finding:
    """Create a Finding with the given attributes."""
    if message is None:
        message = f"[{criterion_id}] Vague language detected. Suggestion: Be more specific."
    return Finding(
        spec_name=spec_name,
        file="requirements.md",
        rule=rule,
        severity=SEVERITY_HINT,
        message=message,
        line=None,
    )


def _make_spec_info(specs_dir: Path, name: str = "01_test") -> SpecInfo:
    """Create a SpecInfo pointing to a directory under specs_dir."""
    spec_path = specs_dir / name
    spec_path.mkdir(parents=True, exist_ok=True)
    return SpecInfo(
        name=name,
        prefix=int(name.split("_")[0]),
        path=spec_path,
        has_tasks=True,
        has_prd=True,
    )


def _write_requirements(spec_path: Path, extra_criteria: str = "") -> None:
    """Write a minimal requirements.md to spec_path."""
    content = (
        "# Requirements\n\n"
        "### Requirement 1: Feature\n\n"
        "#### Acceptance Criteria\n\n"
        "1. [01-REQ-1.1] THE system SHALL be fast.\n"
    )
    if extra_criteria:
        content += extra_criteria
    (spec_path / "requirements.md").write_text(content)


def _write_test_spec(spec_path: Path) -> None:
    """Write a minimal test_spec.md to spec_path."""
    (spec_path / "test_spec.md").write_text(
        "# Test Spec\n\n"
        "## Coverage Matrix\n\n"
        "| Requirement | Test |\n"
        "|-------------|------|\n"
    )


def _make_fix_result(
    spec_name: str = "01_test",
    rule: str = "vague-criterion",
) -> FixResult:
    """Create a minimal FixResult."""
    return FixResult(
        rule=rule,
        spec_name=spec_name,
        file=f".specs/{spec_name}/requirements.md",
        description="Rewrote criterion 01-REQ-1.1: improved text",
    )


def _minimal_tasks_md() -> str:
    return "# Tasks\n\n- [ ] 1. Task\n  - [ ] 1.1 Sub\n"


# ==============================================================================
# TS-109-1: AI fix results included in LintResult
# ==============================================================================


class TestAiFixResultsInLintResult:
    """TS-109-1: Verify _apply_ai_fixes() returns FixResult objects.

    Requirement: 109-REQ-1.1
    """

    def test_ai_fix_results_in_lint_result(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir)
        _write_requirements(spec_info.path)
        finding = _make_finding()
        fix_result = _make_fix_result()

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_FIX_AI) as mock_fix_ai,
        ):
            mock_rewrite.return_value = {"01-REQ-1.1": "improved text"}
            mock_fix_ai.return_value = [fix_result]

            results = _apply_ai_fixes([finding], [spec_info], specs_dir)

        assert len(results) >= 1
        assert results[0].rule == "vague-criterion"


# ==============================================================================
# TS-109-2: No AI fixes without --ai flag
# ==============================================================================


class TestNoAiFixWithoutAiFlag:
    """TS-109-2: Verify run_lint_specs(fix=True, ai=False) does not invoke AI pipeline.

    Requirement: 109-REQ-1.2
    """

    def test_no_ai_fix_without_ai_flag(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import run_lint_specs  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir)
        _write_requirements(spec_info.path)
        (spec_info.path / "tasks.md").write_text(_minimal_tasks_md())

        with (
            patch(_MOCK_APPLY_AI) as mock_apply_ai,
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_GENERATE, new_callable=AsyncMock) as mock_generate,
        ):
            mock_rewrite.return_value = {}
            mock_generate.return_value = {}
            mock_apply_ai.return_value = []

            run_lint_specs(specs_dir, fix=True, ai=False)

        assert mock_apply_ai.call_count == 0
        assert mock_rewrite.call_count == 0
        assert mock_generate.call_count == 0


# ==============================================================================
# TS-109-3: No AI fixes without --fix flag
# ==============================================================================


class TestNoAiFixWithoutFixFlag:
    """TS-109-3: Verify run_lint_specs(ai=True, fix=False) does not invoke AI fix pipeline.

    Requirement: 109-REQ-1.3
    """

    def test_no_ai_fix_without_fix_flag(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import run_lint_specs  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir)
        _write_requirements(spec_info.path)
        (spec_info.path / "tasks.md").write_text(_minimal_tasks_md())

        with (
            patch(_MOCK_APPLY_AI) as mock_apply_ai,
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_FIX_AI) as mock_fix_ai,
            patch("agent_fox.spec.ai_validation.ai_call", new_callable=AsyncMock) as mock_ai,
        ):
            import json  # noqa: PLC0415

            mock_ai.return_value = (json.dumps({"issues": []}), MagicMock())
            mock_rewrite.return_value = {}
            mock_fix_ai.return_value = []
            mock_apply_ai.return_value = []

            run_lint_specs(specs_dir, ai=True, fix=False)

        assert mock_apply_ai.call_count == 0
        assert mock_rewrite.call_count == 0
        assert mock_fix_ai.call_count == 0


# ==============================================================================
# TS-109-4: Criteria rewrite dispatch for vague-criterion
# ==============================================================================


class TestVagueCriterionDispatch:
    """TS-109-4: Verify vague-criterion findings dispatched to rewrite_criteria().

    Requirement: 109-REQ-2.1
    """

    @pytest.mark.asyncio
    async def test_vague_criterion_dispatch(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_s1")
        _write_requirements(spec_info.path)
        finding = _make_finding(spec_name="01_s1", rule="vague-criterion", criterion_id="01-REQ-1.1")
        fix_result = _make_fix_result(spec_name="01_s1")

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_FIX_AI) as mock_fix_ai,
        ):
            mock_rewrite.return_value = {"01-REQ-1.1": "improved text"}
            mock_fix_ai.return_value = [fix_result]

            await _apply_ai_fixes_async([finding], [spec_info], specs_dir, "standard-id")

        assert mock_rewrite.call_count == 1
        assert mock_fix_ai.call_count == 1
        # Verify findings_map passed correctly
        call_args = mock_fix_ai.call_args
        findings_map = call_args.kwargs.get("findings_map") or (
            call_args.args[3] if len(call_args.args) > 3 else None
        )
        assert findings_map is not None
        assert findings_map.get("01-REQ-1.1") == "vague-criterion"


# ==============================================================================
# TS-109-5: findings_map built from finding messages
# ==============================================================================


class TestFindingsMapConstruction:
    """TS-109-5: Verify findings_map maps criterion IDs to rule names.

    Requirement: 109-REQ-2.2
    """

    @pytest.mark.asyncio
    async def test_findings_map_construction(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_s1")
        _write_requirements(spec_info.path, extra_criteria="2. [01-REQ-2.3] THE system SHALL use Redis.\n")

        findings = [
            _make_finding(spec_name="01_s1", rule="vague-criterion", criterion_id="01-REQ-1.1"),
            _make_finding(spec_name="01_s1", rule="implementation-leak", criterion_id="01-REQ-2.3"),
        ]
        fix_result = _make_fix_result(spec_name="01_s1")

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_FIX_AI) as mock_fix_ai,
        ):
            mock_rewrite.return_value = {
                "01-REQ-1.1": "improved vague text",
                "01-REQ-2.3": "improved leak text",
            }
            mock_fix_ai.return_value = [fix_result, fix_result]

            await _apply_ai_fixes_async(findings, [spec_info], specs_dir, "standard-id")

        assert mock_fix_ai.call_count >= 1
        call_args = mock_fix_ai.call_args
        findings_map = call_args.kwargs.get("findings_map") or (
            call_args.args[3] if len(call_args.args) > 3 else None
        )
        assert findings_map is not None
        assert findings_map.get("01-REQ-1.1") == "vague-criterion"
        assert findings_map.get("01-REQ-2.3") == "implementation-leak"


# ==============================================================================
# TS-109-6: Batch splitting for criteria rewrites
# ==============================================================================


class TestRewriteBatchSplitting:
    """TS-109-6: Verify findings > _MAX_REWRITE_BATCH split into multiple calls.

    Requirement: 109-REQ-2.3
    """

    @pytest.mark.asyncio
    async def test_rewrite_batch_splitting(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _MAX_REWRITE_BATCH, _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_s1")
        n = 25
        lines = ["# Requirements\n\n### Requirement 1: Feature\n\n#### Acceptance Criteria\n\n"]
        for i in range(1, n + 1):
            lines.append(f"{i}. [01-REQ-1.{i}] THE system SHALL do thing {i}.\n")
        (spec_info.path / "requirements.md").write_text("".join(lines))

        findings = [
            _make_finding(spec_name="01_s1", rule="vague-criterion", criterion_id=f"01-REQ-1.{i}")
            for i in range(1, n + 1)
        ]

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_FIX_AI) as mock_fix_ai,
        ):
            mock_rewrite.return_value = {"01-REQ-1.1": "improved text"}
            mock_fix_ai.return_value = []

            await _apply_ai_fixes_async(findings, [spec_info], specs_dir, "standard-id")

        # ceil(25 / _MAX_REWRITE_BATCH)
        expected_calls = -(-n // _MAX_REWRITE_BATCH)
        assert mock_rewrite.call_count == expected_calls
        # First batch has _MAX_REWRITE_BATCH findings
        first_batch_findings = (
            mock_rewrite.call_args_list[0].kwargs.get("findings")
            or mock_rewrite.call_args_list[0].args[2]
        )
        assert len(first_batch_findings) == _MAX_REWRITE_BATCH
        # Second batch has the remainder
        second_batch_findings = (
            mock_rewrite.call_args_list[1].kwargs.get("findings")
            or mock_rewrite.call_args_list[1].args[2]
        )
        assert len(second_batch_findings) == n - _MAX_REWRITE_BATCH


# ==============================================================================
# TS-109-7: Test spec generation dispatch for untraced-requirement
# ==============================================================================


class TestUntracedRequirementDispatch:
    """TS-109-7: Verify untraced-requirement findings dispatched to generate_test_spec_entries().

    Requirement: 109-REQ-3.1
    """

    @pytest.mark.asyncio
    async def test_untraced_requirement_dispatch(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_s1")
        _write_requirements(spec_info.path)
        _write_test_spec(spec_info.path)

        finding = _make_finding(
            spec_name="01_s1",
            rule="untraced-requirement",
            message="Requirement 01-REQ-1.1 is not referenced in test_spec.md",
        )
        fix_result = FixResult(
            rule="untraced-requirement",
            spec_name="01_s1",
            file=str(spec_info.path / "test_spec.md"),
            description="Generated test spec entry for 01-REQ-1.1",
        )

        with (
            patch(_MOCK_GENERATE, new_callable=AsyncMock) as mock_generate,
            patch(_MOCK_FIX_TS) as mock_fix_ts,
        ):
            mock_generate.return_value = {"01-REQ-1.1": "### TS-01-99: Auto-generated test\n..."}
            mock_fix_ts.return_value = [fix_result]

            await _apply_ai_fixes_async([finding], [spec_info], specs_dir, "standard-id")

        assert mock_generate.call_count == 1
        assert mock_fix_ts.call_count == 1
        gen_args = mock_generate.call_args
        untraced_ids = gen_args.kwargs.get("untraced_req_ids") or gen_args.args[3]
        assert "01-REQ-1.1" in untraced_ids


# ==============================================================================
# TS-109-8: Batch splitting for test spec generation
# ==============================================================================


class TestUntracedBatchSplitting:
    """TS-109-8: Verify untraced IDs > _MAX_UNTRACED_BATCH split into multiple calls.

    Requirement: 109-REQ-3.2
    """

    @pytest.mark.asyncio
    async def test_untraced_batch_splitting(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _MAX_UNTRACED_BATCH, _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_s1")
        _write_requirements(spec_info.path)
        _write_test_spec(spec_info.path)
        n = 25

        findings = [
            _make_finding(
                spec_name="01_s1",
                rule="untraced-requirement",
                message=f"Requirement 01-REQ-1.{i} is not referenced in test_spec.md",
            )
            for i in range(1, n + 1)
        ]

        with (
            patch(_MOCK_GENERATE, new_callable=AsyncMock) as mock_generate,
            patch(_MOCK_FIX_TS) as mock_fix_ts,
        ):
            mock_generate.return_value = {"01-REQ-1.1": "entry text"}
            mock_fix_ts.return_value = []

            await _apply_ai_fixes_async(findings, [spec_info], specs_dir, "standard-id")

        expected_calls = -(-n // _MAX_UNTRACED_BATCH)
        assert mock_generate.call_count == expected_calls


# ==============================================================================
# TS-109-9: STANDARD model tier used for AI calls
# ==============================================================================


class TestStandardModelUsed:
    """TS-109-9: Verify STANDARD-tier model ID used for both AI generators.

    Requirement: 109-REQ-3.3
    """

    def test_standard_model_used(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_s1")
        _write_requirements(spec_info.path)
        _write_test_spec(spec_info.path)

        findings = [
            _make_finding(spec_name="01_s1", rule="vague-criterion"),
            _make_finding(
                spec_name="01_s1",
                rule="untraced-requirement",
                message="Requirement 01-REQ-1.1 is not referenced in test_spec.md",
            ),
        ]

        with (
            patch("agent_fox.spec.lint.resolve_model") as mock_resolve,
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_GENERATE, new_callable=AsyncMock) as mock_generate,
            patch(_MOCK_FIX_AI) as mock_fix_ai,
            patch(_MOCK_FIX_TS) as mock_fix_ts,
        ):
            mock_model = MagicMock()
            mock_model.model_id = "standard-id"
            mock_resolve.return_value = mock_model
            mock_rewrite.return_value = {"01-REQ-1.1": "improved"}
            mock_generate.return_value = {"01-REQ-1.1": "entry text"}
            mock_fix_ai.return_value = [_make_fix_result()]
            mock_fix_ts.return_value = []

            _apply_ai_fixes(findings, [spec_info], specs_dir)

        rewrite_model = mock_rewrite.call_args.kwargs.get("model") or mock_rewrite.call_args.args[-1]
        assert rewrite_model == "standard-id"
        generate_model = mock_generate.call_args.kwargs.get("model") or mock_generate.call_args.args[-1]
        assert generate_model == "standard-id"


# ==============================================================================
# TS-109-10: Criteria rewrites execute before test spec generation
# ==============================================================================


class TestRewriteBeforeGeneration:
    """TS-109-10: Verify fix_ai_criteria() called before generate_test_spec_entries().

    Requirement: 109-REQ-4.1
    """

    @pytest.mark.asyncio
    async def test_rewrite_before_generation(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_s1")
        _write_requirements(spec_info.path)
        _write_test_spec(spec_info.path)

        findings = [
            _make_finding(spec_name="01_s1", rule="vague-criterion"),
            _make_finding(
                spec_name="01_s1",
                rule="untraced-requirement",
                message="Requirement 01-REQ-1.1 is not referenced in test_spec.md",
            ),
        ]

        call_order: list[str] = []

        def fix_ai_side_effect(*args: object, **kwargs: object) -> list[FixResult]:
            call_order.append("fix_ai")
            return [_make_fix_result()]

        async def generate_side_effect(*args: object, **kwargs: object) -> dict[str, str]:
            call_order.append("generate")
            return {"01-REQ-1.1": "entry"}

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock, return_value={"01-REQ-1.1": "improved"}),
            patch(_MOCK_FIX_AI, side_effect=fix_ai_side_effect),
            patch(_MOCK_GENERATE, new_callable=AsyncMock, side_effect=generate_side_effect),
            patch(_MOCK_FIX_TS, return_value=[]),
        ):
            await _apply_ai_fixes_async(findings, [spec_info], specs_dir, "standard-id")

        assert "fix_ai" in call_order
        assert "generate" in call_order
        assert call_order.index("fix_ai") < call_order.index("generate")


# ==============================================================================
# TS-109-11: AI fixes execute before mechanical fixes
# ==============================================================================


class TestAiFixesBeforeMechanical:
    """TS-109-11: Verify _apply_ai_fixes() called before apply_fixes() in run_lint_specs().

    Requirement: 109-REQ-4.2
    """

    def test_ai_fixes_before_mechanical(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import run_lint_specs  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir)
        _write_requirements(spec_info.path)
        (spec_info.path / "tasks.md").write_text(_minimal_tasks_md())

        call_order: list[str] = []

        def ai_fixes_side_effect(*args: object, **kwargs: object) -> list[FixResult]:
            call_order.append("_apply_ai_fixes")
            return []

        def apply_fixes_side_effect(*args: object, **kwargs: object) -> list[FixResult]:
            call_order.append("apply_fixes")
            return []

        with (
            patch(_MOCK_APPLY_AI, side_effect=ai_fixes_side_effect),
            patch("agent_fox.spec.fixers.runner.apply_fixes", side_effect=apply_fixes_side_effect),
            patch(_MOCK_VALIDATE, return_value=[]),
            patch(_MOCK_MERGE_AI, return_value=[]),
        ):
            run_lint_specs(specs_dir, ai=True, fix=True)

        assert "_apply_ai_fixes" in call_order
        assert "apply_fixes" in call_order
        assert call_order.index("_apply_ai_fixes") < call_order.index("apply_fixes")


# ==============================================================================
# TS-109-12: Re-validation after AI fixes
# ==============================================================================


class TestRevalidationAfterAiFixes:
    """TS-109-12: Verify re-validation called when AI fixes produce results.

    Requirement: 109-REQ-5.1
    """

    def test_revalidation_after_ai_fixes(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import run_lint_specs  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir)
        _write_requirements(spec_info.path)
        (spec_info.path / "tasks.md").write_text(_minimal_tasks_md())

        fix_result = _make_fix_result()

        with (
            patch(_MOCK_APPLY_AI, return_value=[fix_result]),
            patch(_MOCK_VALIDATE, return_value=[]) as mock_validate,
            patch(_MOCK_MERGE_AI, return_value=[]) as mock_merge_ai,
            patch("agent_fox.spec.fixers.runner.apply_fixes", return_value=[]),
        ):
            run_lint_specs(specs_dir, ai=True, fix=True)

        assert mock_validate.call_count >= 2
        assert mock_merge_ai.call_count >= 2


# ==============================================================================
# TS-109-13: No re-invocation of AI fixes during re-validation
# ==============================================================================


class TestNoReInvocationDuringRevalidation:
    """TS-109-13: Verify _apply_ai_fixes() called exactly once.

    Requirement: 109-REQ-5.2
    """

    def test_no_re_invocation_during_revalidation(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import run_lint_specs  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir)
        _write_requirements(spec_info.path)
        (spec_info.path / "tasks.md").write_text(_minimal_tasks_md())

        fix_result = _make_fix_result()

        with (
            patch(_MOCK_APPLY_AI, return_value=[fix_result]) as mock_apply_ai,
            patch(_MOCK_VALIDATE, return_value=[]),
            patch(_MOCK_MERGE_AI, return_value=[]),
            patch("agent_fox.spec.fixers.runner.apply_fixes", return_value=[]),
        ):
            run_lint_specs(specs_dir, ai=True, fix=True)

        assert mock_apply_ai.call_count == 1


# ==============================================================================
# TS-109-E1: No AI-fixable findings skips pipeline
# ==============================================================================


class TestNoFixableFindingsSkipsPipeline:
    """TS-109-E1: When no AI_FIXABLE_RULES findings, pipeline returns empty list.

    Requirement: 109-REQ-1.E1
    """

    def test_no_fixable_findings_skips_pipeline(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir)

        # Only mechanical rule findings (not in AI_FIXABLE_RULES)
        findings = [
            Finding(
                spec_name="01_test",
                file="prd.md",
                rule="missing-verification",
                severity=SEVERITY_HINT,
                message="Missing verification",
                line=None,
            )
        ]

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_GENERATE, new_callable=AsyncMock) as mock_generate,
        ):
            mock_rewrite.return_value = {}
            mock_generate.return_value = {}
            results = _apply_ai_fixes(findings, [spec_info], specs_dir)

        assert results == []
        assert mock_rewrite.call_count == 0
        assert mock_generate.call_count == 0


# ==============================================================================
# TS-109-E2: Rewrite failure for one spec continues others
# ==============================================================================


class TestRewriteFailureContinuesOtherSpecs:
    """TS-109-E2: If rewrite_criteria() raises for s1, s2 is still processed.

    Requirement: 109-REQ-2.E1
    """

    @pytest.mark.asyncio
    async def test_rewrite_failure_continues_other_specs(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec1 = _make_spec_info(specs_dir, "01_s1")
        spec2 = _make_spec_info(specs_dir, "02_s2")
        _write_requirements(spec1.path)
        _write_requirements(spec2.path)

        findings = [
            _make_finding(spec_name="01_s1", rule="vague-criterion"),
            _make_finding(spec_name="02_s2", rule="vague-criterion"),
        ]
        fix_result = _make_fix_result(spec_name="02_s2")

        async def rewrite_side_effect(
            spec_name: str,
            requirements_text: str,
            findings: list,
            model: str,
        ) -> dict[str, str]:
            if "s1" in spec_name:
                raise RuntimeError("AI call failed for s1")
            return {"01-REQ-1.1": "improved text"}

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock, side_effect=rewrite_side_effect),
            patch(_MOCK_FIX_AI, return_value=[fix_result]),
        ):
            results = await _apply_ai_fixes_async(findings, [spec1, spec2], specs_dir, "standard-id")

        assert any(r.spec_name == "02_s2" for r in results)


# ==============================================================================
# TS-109-E3: Empty rewrite dict skips fix_ai_criteria
# ==============================================================================


class TestEmptyRewriteSkipsFixer:
    """TS-109-E3: When rewrite_criteria() returns {}, fix_ai_criteria() not called.

    Requirement: 109-REQ-2.E2
    """

    @pytest.mark.asyncio
    async def test_empty_rewrite_skips_fixer(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_s1")
        _write_requirements(spec_info.path)

        finding = _make_finding(spec_name="01_s1", rule="vague-criterion")

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock, return_value={}) as mock_rewrite,
            patch(_MOCK_FIX_AI) as mock_fix_ai,
        ):
            results = await _apply_ai_fixes_async([finding], [spec_info], specs_dir, "standard-id")

        assert mock_rewrite.call_count == 1
        assert mock_fix_ai.call_count == 0
        assert results == []


# ==============================================================================
# TS-109-E4: Generation failure for one spec continues others
# ==============================================================================


class TestGenerationFailureContinuesOtherSpecs:
    """TS-109-E4: If generate_test_spec_entries() raises for s1, s2 is still processed.

    Requirement: 109-REQ-3.E1
    """

    @pytest.mark.asyncio
    async def test_generation_failure_continues_other_specs(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec1 = _make_spec_info(specs_dir, "01_s1")
        spec2 = _make_spec_info(specs_dir, "02_s2")
        _write_requirements(spec1.path)
        _write_requirements(spec2.path)
        _write_test_spec(spec1.path)
        _write_test_spec(spec2.path)

        findings = [
            _make_finding(
                spec_name="01_s1",
                rule="untraced-requirement",
                message="Requirement 01-REQ-1.1 is not referenced in test_spec.md",
            ),
            _make_finding(
                spec_name="02_s2",
                rule="untraced-requirement",
                message="Requirement 01-REQ-1.1 is not referenced in test_spec.md",
            ),
        ]
        fix_result = FixResult(
            rule="untraced-requirement",
            spec_name="02_s2",
            file=str(spec2.path / "test_spec.md"),
            description="Generated test spec entry for 01-REQ-1.1",
        )

        async def generate_side_effect(
            spec_name: str,
            requirements_text: str,
            test_spec_text: str,
            untraced_req_ids: list,
            model: str,
        ) -> dict[str, str]:
            if "s1" in spec_name:
                raise RuntimeError("AI generation failed for s1")
            return {"01-REQ-1.1": "entry text"}

        with (
            patch(_MOCK_GENERATE, new_callable=AsyncMock, side_effect=generate_side_effect),
            patch(_MOCK_FIX_TS, return_value=[fix_result]),
        ):
            results = await _apply_ai_fixes_async(findings, [spec1, spec2], specs_dir, "standard-id")

        assert any(r.spec_name == "02_s2" for r in results)


# ==============================================================================
# TS-109-E5: Empty entries dict skips fix_ai_test_spec_entries
# ==============================================================================


class TestEmptyEntriesSkipsFixer:
    """TS-109-E5: When generate_test_spec_entries() returns {}, fix_ai_test_spec_entries() not called.

    Requirement: 109-REQ-3.E2
    """

    @pytest.mark.asyncio
    async def test_empty_entries_skips_fixer(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_s1")
        _write_requirements(spec_info.path)
        _write_test_spec(spec_info.path)

        finding = _make_finding(
            spec_name="01_s1",
            rule="untraced-requirement",
            message="Requirement 01-REQ-1.1 is not referenced in test_spec.md",
        )

        with (
            patch(_MOCK_GENERATE, new_callable=AsyncMock, return_value={}) as mock_generate,
            patch(_MOCK_FIX_TS) as mock_fix_ts,
        ):
            results = await _apply_ai_fixes_async([finding], [spec_info], specs_dir, "standard-id")

        assert mock_generate.call_count == 1
        assert mock_fix_ts.call_count == 0
        assert results == []


# ==============================================================================
# TS-109-E6: Missing test_spec.md skips generation
# ==============================================================================


class TestMissingTestSpecSkipsGeneration:
    """TS-109-E6: When test_spec.md is missing, test spec generation is skipped.

    Requirement: 109-REQ-3.E3
    """

    @pytest.mark.asyncio
    async def test_missing_test_spec_skips_generation(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_s1")
        _write_requirements(spec_info.path)
        # Intentionally NOT writing test_spec.md

        finding = _make_finding(
            spec_name="01_s1",
            rule="untraced-requirement",
            message="Requirement 01-REQ-1.1 is not referenced in test_spec.md",
        )

        with (
            patch(_MOCK_GENERATE, new_callable=AsyncMock) as mock_generate,
            patch(_MOCK_FIX_TS),
        ):
            results = await _apply_ai_fixes_async([finding], [spec_info], specs_dir, "standard-id")

        assert mock_generate.call_count == 0
        assert results == []


# ==============================================================================
# TS-109-E7: Re-validation reports still-flagged criterion
# ==============================================================================


class TestStillFlaggedCriterionReported:
    """TS-109-E7: If re-validation still flags a rewritten criterion, it's reported.

    Requirement: 109-REQ-5.E1
    """

    def test_still_flagged_criterion_reported(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import run_lint_specs  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir)
        _write_requirements(spec_info.path)
        (spec_info.path / "tasks.md").write_text(_minimal_tasks_md())

        fix_result = _make_fix_result()
        remaining_finding = _make_finding(rule="vague-criterion")

        with (
            patch(_MOCK_APPLY_AI, return_value=[fix_result]) as mock_apply_ai,
            patch(_MOCK_VALIDATE, return_value=[]),
            patch(_MOCK_MERGE_AI, return_value=[remaining_finding]),
            patch("agent_fox.spec.fixers.runner.apply_fixes", return_value=[]),
        ):
            result = run_lint_specs(specs_dir, ai=True, fix=True)

        assert any(f.rule == "vague-criterion" for f in result.findings)
        assert mock_apply_ai.call_count == 1
