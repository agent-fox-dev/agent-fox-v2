"""Integration smoke tests for AI fix pipeline wiring.

Test Spec: TS-109-SMOKE-1, TS-109-SMOKE-2
Validates: Path 1 and Path 2 from design.md

Note: fix_ai_criteria() and fix_ai_test_spec_entries() are NOT mocked in
these tests -- they run for real to verify actual file modifications.
Only the AI generator functions (rewrite_criteria, generate_test_spec_entries)
and the AI analysis (validate_specs, _merge_ai_findings) are mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent_fox.spec.validators import SEVERITY_HINT, Finding

# -- Patch targets ---------------------------------------------------------------

_MOCK_REWRITE = "agent_fox.spec.ai_validation.rewrite_criteria"
_MOCK_GENERATE = "agent_fox.spec.ai_validation.generate_test_spec_entries"
_MOCK_VALIDATE = "agent_fox.spec.lint.validate_specs"
_MOCK_MERGE_AI = "agent_fox.spec.lint._merge_ai_findings"


# -- Setup helpers ---------------------------------------------------------------


def _setup_spec(
    specs_dir: Path,
    name: str = "99_test",
    *,
    requirements_content: str,
    test_spec_content: str,
) -> Path:
    """Create a spec directory with standard files."""
    spec_path = specs_dir / name
    spec_path.mkdir(parents=True, exist_ok=True)

    (spec_path / "requirements.md").write_text(requirements_content)
    (spec_path / "test_spec.md").write_text(test_spec_content)
    (spec_path / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Task\n  - [ ] 1.1 Sub\n")
    for f in ["prd.md", "design.md"]:
        (spec_path / f).write_text(f"# {f}\n")

    return spec_path


# ==============================================================================
# TS-109-SMOKE-1: Full criteria rewrite path
# ==============================================================================


class TestSmokeCriteriaRewrite:
    """TS-109-SMOKE-1: End-to-end verification of criteria rewrite pipeline.

    Validates: Path 1 from design.md
    fix_ai_criteria() is NOT mocked -- real file modification verified.
    """

    def test_smoke_criteria_rewrite(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import run_lint_specs  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        spec_path = _setup_spec(
            specs_dir,
            "99_test",
            requirements_content=(
                "# Requirements\n\n"
                "### Requirement 1: Feature\n\n"
                "#### Acceptance Criteria\n\n"
                "1. [99-REQ-1.1] THE system SHALL be fast.\n"
            ),
            test_spec_content="# Test Spec\n\n**Requirement:** 99-REQ-1.1\n",
        )

        vague_finding = Finding(
            spec_name="99_test",
            file="requirements.md",
            rule="vague-criterion",
            severity=SEVERITY_HINT,
            message="[99-REQ-1.1] Vague language detected. Suggestion: Add measurable target.",
            line=None,
        )

        with (
            patch(_MOCK_VALIDATE, return_value=[]),
            patch(_MOCK_MERGE_AI, return_value=[vague_finding]),
            patch(
                _MOCK_REWRITE,
                new_callable=AsyncMock,
                return_value={"99-REQ-1.1": "THE system SHALL respond within 200ms at p95."},
            ),
        ):
            result = run_lint_specs(specs_dir, ai=True, fix=True)

        content = (spec_path / "requirements.md").read_text()
        assert "respond within 200ms" in content
        assert "be fast" not in content
        assert any(r.rule == "vague-criterion" for r in result.fix_results)


# ==============================================================================
# TS-109-SMOKE-2: Full test spec generation path
# ==============================================================================


class TestSmokeTestSpecGeneration:
    """TS-109-SMOKE-2: End-to-end verification of test spec generation pipeline.

    Validates: Path 2 from design.md
    fix_ai_test_spec_entries() is NOT mocked -- real file modification verified.
    """

    def test_smoke_test_spec_generation(self, tmp_path: Path) -> None:
        from agent_fox.spec.lint import run_lint_specs  # noqa: PLC0415

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        spec_path = _setup_spec(
            specs_dir,
            "99_test",
            requirements_content=(
                "# Requirements\n\n"
                "### Requirement 1: Feature\n\n"
                "#### Acceptance Criteria\n\n"
                "1. [99-REQ-1.1] THE system SHALL do something.\n"
            ),
            test_spec_content=(
                "# Test Spec\n\n"
                "## Coverage Matrix\n\n"
                "| Requirement | Test |\n"
                "|-------------|------|\n"
            ),
        )

        untraced_finding = Finding(
            spec_name="99_test",
            file="test_spec.md",
            rule="untraced-requirement",
            severity=SEVERITY_HINT,
            message="Requirement 99-REQ-1.1 is not referenced in test_spec.md",
            line=None,
        )

        with (
            patch(_MOCK_VALIDATE, return_value=[untraced_finding]),
            patch(_MOCK_MERGE_AI, return_value=[untraced_finding]),
            patch(
                _MOCK_GENERATE,
                new_callable=AsyncMock,
                return_value={
                    "99-REQ-1.1": (
                        "### TS-99-42: Auto-generated test\n\n"
                        "**Requirement:** 99-REQ-1.1\n\n"
                        "Description of the test case.\n"
                    )
                },
            ),
        ):
            result = run_lint_specs(specs_dir, ai=True, fix=True)

        content = (spec_path / "test_spec.md").read_text()
        assert "TS-99-42" in content
        assert any(r.rule == "untraced-requirement" for r in result.fix_results)
