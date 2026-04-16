"""Property tests for AI fix pipeline wiring dispatch logic.

Test Spec: TS-109-P1 through TS-109-P6
Properties: 1-6 from design.md
Requirements: 109-REQ-1.2, 109-REQ-2.1, 109-REQ-3.1, 109-REQ-4.1,
              109-REQ-2.3, 109-REQ-3.2, 109-REQ-2.E1, 109-REQ-3.E1,
              109-REQ-5.1, 109-REQ-5.2
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.fixers.types import AI_FIXABLE_RULES, FIXABLE_RULES, FixResult
from agent_fox.spec.validators import SEVERITY_HINT, Finding

# -- Patch targets ---------------------------------------------------------------

_MOCK_REWRITE = "agent_fox.spec.ai_validation.rewrite_criteria"
_MOCK_GENERATE = "agent_fox.spec.ai_validation.generate_test_spec_entries"
_MOCK_FIX_AI = "agent_fox.spec.fixers.ai.fix_ai_criteria"
_MOCK_FIX_TS = "agent_fox.spec.fixers.ai.fix_ai_test_spec_entries"
_MOCK_APPLY_AI = "agent_fox.spec.lint._apply_ai_fixes"
_MOCK_VALIDATE = "agent_fox.spec.lint.validate_specs"
_MOCK_MERGE_AI = "agent_fox.spec.lint._merge_ai_findings"


# -- Strategies ------------------------------------------------------------------

all_rules_strategy = st.sampled_from(sorted(AI_FIXABLE_RULES | FIXABLE_RULES))
ai_rule_strategy = st.sampled_from(sorted(AI_FIXABLE_RULES))
criteria_rule_strategy = st.sampled_from(["vague-criterion", "implementation-leak"])


def _make_finding_for_rule(rule: str, spec_name: str = "01_test", idx: int = 1) -> Finding:
    """Create a Finding appropriate for the given rule."""
    if rule in {"vague-criterion", "implementation-leak"}:
        message = f"[01-REQ-1.{idx}] Issue detected."
    elif rule == "untraced-requirement":
        message = f"Requirement 01-REQ-1.{idx} is not referenced in test_spec.md"
    else:
        message = f"Rule {rule} issue detected."
    return Finding(
        spec_name=spec_name,
        file="requirements.md",
        rule=rule,
        severity=SEVERITY_HINT,
        message=message,
        line=None,
    )


def _make_spec_info(specs_dir: Path, name: str) -> SpecInfo:
    """Create a SpecInfo pointing to a directory under specs_dir."""
    spec_path = specs_dir / name
    spec_path.mkdir(parents=True, exist_ok=True)
    prefix = int(name.split("_")[0])
    (spec_path / "requirements.md").write_text(
        "# Requirements\n\n"
        "### Requirement 1: Feature\n\n"
        "#### Acceptance Criteria\n\n"
        "1. [01-REQ-1.1] THE system SHALL do something.\n"
    )
    (spec_path / "test_spec.md").write_text(
        "# Test Spec\n\n## Coverage Matrix\n\n| Requirement | Test |\n|-------------|------|\n"
    )
    return SpecInfo(
        name=name,
        prefix=prefix,
        path=spec_path,
        has_tasks=True,
        has_prd=True,
    )


def _make_fix_result(spec_name: str = "01_test", rule: str = "vague-criterion") -> FixResult:
    return FixResult(
        rule=rule,
        spec_name=spec_name,
        file=f".specs/{spec_name}/requirements.md",
        description="Rewrote criterion 01-REQ-1.1: improved text",
    )


# ==============================================================================
# TS-109-P1: AI fix isolation without --ai
# ==============================================================================


class TestAiFixIsolation:
    """TS-109-P1: For any findings, when ai=False, zero AI generator calls made.

    Property 1 from design.md.
    Validates: 109-REQ-1.2
    """

    @given(
        rules=st.lists(
            all_rules_strategy,
            min_size=0,
            max_size=20,
        )
    )
    @settings(max_examples=30)
    def test_ai_fix_isolation(self, rules: list[str], tmp_path_factory: pytest.TempPathFactory) -> None:
        from agent_fox.spec.lint import run_lint_specs  # noqa: PLC0415

        tmp_path = tmp_path_factory.mktemp("prop")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        spec_info = _make_spec_info(specs_dir, "01_test")
        (spec_info.path / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Task\n  - [ ] 1.1 Sub\n")

        findings = [_make_finding_for_rule(rule, idx=i) for i, rule in enumerate(rules, 1)]

        with (
            patch(_MOCK_APPLY_AI) as mock_apply_ai,
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_GENERATE, new_callable=AsyncMock) as mock_generate,
            patch(_MOCK_VALIDATE, return_value=findings),
        ):
            mock_rewrite.return_value = {}
            mock_generate.return_value = {}
            mock_apply_ai.return_value = []

            run_lint_specs(specs_dir, ai=False, fix=True)

        assert mock_apply_ai.call_count == 0
        assert mock_rewrite.call_count == 0
        assert mock_generate.call_count == 0


# ==============================================================================
# TS-109-P2: Dispatch correctness by rule
# ==============================================================================


class TestDispatchCorrectness:
    """TS-109-P2: For any AI-fixable finding, dispatch routes to correct generator.

    Property 2 from design.md.
    Validates: 109-REQ-2.1, 109-REQ-3.1
    """

    @given(rule=ai_rule_strategy)
    @settings(max_examples=20)
    def test_dispatch_correctness(self, rule: str, tmp_path_factory: pytest.TempPathFactory) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        tmp_path = tmp_path_factory.mktemp("prop")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_test")

        finding = _make_finding_for_rule(rule, spec_name="01_test")

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_FIX_AI, return_value=[]),
            patch(_MOCK_GENERATE, new_callable=AsyncMock) as mock_generate,
            patch(_MOCK_FIX_TS, return_value=[]),
        ):
            mock_rewrite.return_value = {}
            mock_generate.return_value = {}

            asyncio.run(_apply_ai_fixes_async([finding], [spec_info], specs_dir, "model-id"))

        if rule in {"vague-criterion", "implementation-leak"}:
            assert mock_rewrite.call_count == 1
            assert mock_generate.call_count == 0
        else:
            # untraced-requirement
            assert mock_rewrite.call_count == 0
            assert mock_generate.call_count == 1


# ==============================================================================
# TS-109-P3: Ordering invariant
# ==============================================================================


class TestOrderingInvariant:
    """TS-109-P3: For any spec with both rewrite and generation findings,
    rewrite completes before generation starts.

    Property 3 from design.md.
    Validates: 109-REQ-4.1
    """

    @given(
        n_rewrite=st.integers(min_value=1, max_value=5),
        n_untraced=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=20)
    def test_ordering_invariant(
        self,
        n_rewrite: int,
        n_untraced: int,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        tmp_path = tmp_path_factory.mktemp("prop")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_test")

        findings: list[Finding] = []
        for i in range(1, n_rewrite + 1):
            findings.append(_make_finding_for_rule("vague-criterion", spec_name="01_test", idx=i))
        for i in range(1, n_untraced + 1):
            findings.append(_make_finding_for_rule("untraced-requirement", spec_name="01_test", idx=i + 100))

        call_log: list[str] = []

        def fix_ai_side(*args: object, **kwargs: object) -> list[FixResult]:
            call_log.append("fix_ai")
            return []

        async def generate_side(*args: object, **kwargs: object) -> dict[str, str]:
            call_log.append("generate")
            return {}

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock, return_value={"01-REQ-1.1": "improved"}),
            patch(_MOCK_FIX_AI, side_effect=fix_ai_side),
            patch(_MOCK_GENERATE, new_callable=AsyncMock, side_effect=generate_side),
            patch(_MOCK_FIX_TS, return_value=[]),
        ):
            asyncio.run(_apply_ai_fixes_async(findings, [spec_info], specs_dir, "model-id"))

        assert "fix_ai" in call_log
        assert "generate" in call_log
        # All fix_ai calls precede all generate calls
        last_fix_ai_idx = max(i for i, c in enumerate(call_log) if c == "fix_ai")
        first_generate_idx = min(i for i, c in enumerate(call_log) if c == "generate")
        assert last_fix_ai_idx < first_generate_idx


# ==============================================================================
# TS-109-P4: Batch size bound
# ==============================================================================


class TestBatchSizeBound:
    """TS-109-P4: For any N findings, AI calls <= ceil(N / batch_limit).

    Property 4 from design.md.
    Validates: 109-REQ-2.3, 109-REQ-3.2
    """

    @given(n=st.integers(min_value=1, max_value=50))
    @settings(max_examples=30)
    def test_batch_size_bound_rewrite(self, n: int, tmp_path_factory: pytest.TempPathFactory) -> None:
        from agent_fox.spec.lint import _MAX_REWRITE_BATCH, _apply_ai_fixes_async  # noqa: PLC0415

        tmp_path = tmp_path_factory.mktemp("prop")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_test")

        findings = [
            _make_finding_for_rule("vague-criterion", spec_name="01_test", idx=i)
            for i in range(1, n + 1)
        ]

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock) as mock_rewrite,
            patch(_MOCK_FIX_AI, return_value=[]),
        ):
            mock_rewrite.return_value = {}

            asyncio.run(_apply_ai_fixes_async(findings, [spec_info], specs_dir, "model-id"))

        expected_max_calls = -(-n // _MAX_REWRITE_BATCH)  # ceil(n / batch)
        assert mock_rewrite.call_count == expected_max_calls

    @given(n=st.integers(min_value=1, max_value=50))
    @settings(max_examples=30)
    def test_batch_size_bound_generation(self, n: int, tmp_path_factory: pytest.TempPathFactory) -> None:
        from agent_fox.spec.lint import _MAX_UNTRACED_BATCH, _apply_ai_fixes_async  # noqa: PLC0415

        tmp_path = tmp_path_factory.mktemp("prop")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_test")

        findings = [
            _make_finding_for_rule("untraced-requirement", spec_name="01_test", idx=i)
            for i in range(1, n + 1)
        ]

        with (
            patch(_MOCK_GENERATE, new_callable=AsyncMock) as mock_generate,
            patch(_MOCK_FIX_TS, return_value=[]),
        ):
            mock_generate.return_value = {}

            asyncio.run(_apply_ai_fixes_async(findings, [spec_info], specs_dir, "model-id"))

        expected_max_calls = -(-n // _MAX_UNTRACED_BATCH)  # ceil(n / batch)
        assert mock_generate.call_count == expected_max_calls


# ==============================================================================
# TS-109-P5: Per-spec error isolation
# ==============================================================================


class TestPerSpecErrorIsolation:
    """TS-109-P5: For any set of specs with one failing, other specs' fixes returned.

    Property 5 from design.md.
    Validates: 109-REQ-2.E1, 109-REQ-3.E1

    Note: Non-failing specs must return non-empty rewrites for FixResults to appear.
    """

    @given(
        n_specs=st.integers(min_value=2, max_value=5),
        fail_idx=st.integers(min_value=0, max_value=1),
    )
    @settings(max_examples=15)
    def test_per_spec_error_isolation(
        self,
        n_specs: int,
        fail_idx: int,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        from agent_fox.spec.lint import _apply_ai_fixes_async  # noqa: PLC0415

        # Clamp fail_idx to valid range
        fail_idx = fail_idx % n_specs

        tmp_path = tmp_path_factory.mktemp("prop")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        specs = [_make_spec_info(specs_dir, f"{i + 1:02d}_spec{i}") for i in range(n_specs)]
        spec_names = [s.name for s in specs]
        failing_spec = spec_names[fail_idx]

        findings = [
            _make_finding_for_rule("vague-criterion", spec_name=name)
            for name in spec_names
        ]

        fix_results_by_spec: dict[str, list[FixResult]] = {
            name: [_make_fix_result(spec_name=name, rule="vague-criterion")]
            for name in spec_names
            if name != failing_spec
        }

        async def rewrite_side(
            spec_name: str,
            requirements_text: str,
            findings: list,
            model: str,
        ) -> dict[str, str]:
            if spec_name == failing_spec:
                raise RuntimeError(f"AI call failed for {spec_name}")
            return {"01-REQ-1.1": "improved text"}

        def fix_ai_side(
            spec_name: str,
            req_path: Path,
            rewrites: dict,
            findings_map: dict,
        ) -> list[FixResult]:
            return fix_results_by_spec.get(spec_name, [])

        with (
            patch(_MOCK_REWRITE, new_callable=AsyncMock, side_effect=rewrite_side),
            patch(_MOCK_FIX_AI, side_effect=fix_ai_side),
        ):
            results = asyncio.run(
                _apply_ai_fixes_async(findings, specs, specs_dir, "model-id")
            )

        returned_spec_names = {r.spec_name for r in results}
        for name in spec_names:
            if name != failing_spec:
                assert name in returned_spec_names


# ==============================================================================
# TS-109-P6: Single-pass fix guarantee
# ==============================================================================


class TestSinglePassGuarantee:
    """TS-109-P6: For any run with AI fixes, AI fix pipeline invoked at most once.

    Property 6 from design.md.
    Validates: 109-REQ-5.1, 109-REQ-5.2
    """

    @given(n_results=st.integers(min_value=0, max_value=10))
    @settings(max_examples=20)
    def test_single_pass_guarantee(
        self,
        n_results: int,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        from agent_fox.spec.lint import run_lint_specs  # noqa: PLC0415

        tmp_path = tmp_path_factory.mktemp("prop")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        spec_info = _make_spec_info(specs_dir, "01_test")
        (spec_info.path / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Task\n  - [ ] 1.1 Sub\n")

        ai_fix_results = [_make_fix_result()] * n_results

        with (
            patch(_MOCK_APPLY_AI, return_value=ai_fix_results) as mock_apply_ai,
            patch(_MOCK_VALIDATE, return_value=[]),
            patch(_MOCK_MERGE_AI, return_value=[]),
            patch("agent_fox.spec.fixers.runner.apply_fixes", return_value=[]),
        ):
            run_lint_specs(specs_dir, ai=True, fix=True)

        assert mock_apply_ai.call_count == 1
