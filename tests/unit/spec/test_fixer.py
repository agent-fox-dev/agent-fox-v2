"""Unit tests for spec fixer: coarse dependency rewrite, missing verification.

Test Spec: TS-20-14 through TS-20-20
Requirements: 20-REQ-6.*
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.fixer import (
    apply_fixes,
    fix_coarse_dependency,
    fix_missing_verification,
)
from agent_fox.spec.validator import Finding

# -- Helpers -------------------------------------------------------------------


def _write_file(tmp_path: Path, name: str, content: str) -> Path:
    """Write a file under tmp_path and return its path."""
    path = tmp_path / name
    path.write_text(content)
    return path


# -- TS-20-14: Fix coarse dependency rewrites table ----------------------------


class TestFixCoarseDependencyRewrite:
    """TS-20-14: Verify fixer rewrites standard-format table to alt format.

    Requirements: 20-REQ-6.3, 20-REQ-6.5
    """

    def test_returns_one_fix_result(self, tmp_path: Path) -> None:
        prd_path = _write_file(
            tmp_path,
            "prd.md",
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Uses Config for settings |\n",
        )
        known_specs = {"01_alpha": [1, 2, 3], "02_beta": [1, 2]}
        results = fix_coarse_dependency("02_beta", prd_path, known_specs, [1, 2])
        assert len(results) == 1

    def test_rule_is_coarse_dependency(self, tmp_path: Path) -> None:
        prd_path = _write_file(
            tmp_path,
            "prd.md",
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Uses Config for settings |\n",
        )
        known_specs = {"01_alpha": [1, 2, 3], "02_beta": [1, 2]}
        results = fix_coarse_dependency("02_beta", prd_path, known_specs, [1, 2])
        assert results[0].rule == "coarse-dependency"

    def test_file_contains_from_group(self, tmp_path: Path) -> None:
        prd_path = _write_file(
            tmp_path,
            "prd.md",
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Uses Config for settings |\n",
        )
        known_specs = {"01_alpha": [1, 2, 3], "02_beta": [1, 2]}
        fix_coarse_dependency("02_beta", prd_path, known_specs, [1, 2])
        content = prd_path.read_text()
        assert "From Group" in content

    def test_file_no_longer_has_this_spec(self, tmp_path: Path) -> None:
        prd_path = _write_file(
            tmp_path,
            "prd.md",
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Uses Config for settings |\n",
        )
        known_specs = {"01_alpha": [1, 2, 3], "02_beta": [1, 2]}
        fix_coarse_dependency("02_beta", prd_path, known_specs, [1, 2])
        content = prd_path.read_text()
        assert "This Spec" not in content

    def test_correct_group_numbers(self, tmp_path: Path) -> None:
        prd_path = _write_file(
            tmp_path,
            "prd.md",
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Uses Config for settings |\n",
        )
        known_specs = {"01_alpha": [1, 2, 3], "02_beta": [1, 2]}
        fix_coarse_dependency("02_beta", prd_path, known_specs, [1, 2])
        content = prd_path.read_text()
        # From Group = last of upstream (3), To Group = first of current (1)
        assert "01_alpha | 3 | 1" in content


# -- TS-20-15: Fix coarse dependency with unknown upstream groups ---------------


class TestFixCoarseDependencyUnknownUpstream:
    """TS-20-15: Verify fixer uses sentinel 0 when upstream has no tasks.

    Requirements: 20-REQ-6.E2
    """

    def test_from_group_is_zero(self, tmp_path: Path) -> None:
        prd_path = _write_file(
            tmp_path,
            "prd.md",
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 03_gamma | Some dependency |\n",
        )
        known_specs: dict[str, list[int]] = {"03_gamma": []}
        fix_coarse_dependency("02_beta", prd_path, known_specs, [1])
        content = prd_path.read_text()
        assert "03_gamma | 0 | 1" in content


# -- TS-20-16: Fix coarse dependency is idempotent -----------------------------


class TestFixCoarseDependencyIdempotent:
    """TS-20-16: Running fixer twice produces same result.

    Requirements: 20-REQ-6.2
    """

    def test_first_call_returns_results(self, tmp_path: Path) -> None:
        prd_path = _write_file(
            tmp_path,
            "prd.md",
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Uses Config |\n",
        )
        known_specs = {"01_alpha": [1, 2, 3], "02_beta": [1]}
        results1 = fix_coarse_dependency("02_beta", prd_path, known_specs, [1])
        assert len(results1) == 1

    def test_second_call_returns_empty(self, tmp_path: Path) -> None:
        prd_path = _write_file(
            tmp_path,
            "prd.md",
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Uses Config |\n",
        )
        known_specs = {"01_alpha": [1, 2, 3], "02_beta": [1]}
        fix_coarse_dependency("02_beta", prd_path, known_specs, [1])
        results2 = fix_coarse_dependency("02_beta", prd_path, known_specs, [1])
        assert len(results2) == 0

    def test_content_unchanged_after_second_call(self, tmp_path: Path) -> None:
        prd_path = _write_file(
            tmp_path,
            "prd.md",
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Uses Config |\n",
        )
        known_specs = {"01_alpha": [1, 2, 3], "02_beta": [1]}
        fix_coarse_dependency("02_beta", prd_path, known_specs, [1])
        content1 = prd_path.read_text()
        fix_coarse_dependency("02_beta", prd_path, known_specs, [1])
        content2 = prd_path.read_text()
        assert content1 == content2


# -- TS-20-17: Fix missing verification appends step ---------------------------


class TestFixMissingVerificationAppend:
    """TS-20-17: Verify fixer appends verification step to groups missing it.

    Requirements: 20-REQ-6.4
    """

    def test_returns_one_fix_result(self, tmp_path: Path) -> None:
        tasks_path = _write_file(
            tmp_path,
            "tasks.md",
            "# Tasks\n\n"
            "- [ ] 1. Write tests\n"
            "  - [ ] 1.1 Create fixtures\n"
            "  - [ ] 1.2 Write unit tests\n",
        )
        results = fix_missing_verification("02_beta", tasks_path)
        assert len(results) == 1

    def test_file_contains_verification_step(self, tmp_path: Path) -> None:
        tasks_path = _write_file(
            tmp_path,
            "tasks.md",
            "# Tasks\n\n"
            "- [ ] 1. Write tests\n"
            "  - [ ] 1.1 Create fixtures\n"
            "  - [ ] 1.2 Write unit tests\n",
        )
        fix_missing_verification("02_beta", tasks_path)
        content = tasks_path.read_text()
        assert "1.V Verify task group 1" in content


# -- TS-20-18: Fix missing verification skips groups that have it ---------------


class TestFixMissingVerificationSkipsExisting:
    """TS-20-18: Verify fixer does not duplicate existing verification steps.

    Requirements: 20-REQ-6.4
    """

    def test_returns_empty(self, tmp_path: Path) -> None:
        tasks_path = _write_file(
            tmp_path,
            "tasks.md",
            "# Tasks\n\n"
            "- [ ] 1. Write tests\n"
            "  - [ ] 1.1 Create fixtures\n"
            "  - [ ] 1.V Verify task group 1\n",
        )
        results = fix_missing_verification("02_beta", tasks_path)
        assert len(results) == 0


# -- TS-20-19: apply_fixes skips unfixable findings ---------------------------


class TestApplyFixesSkipsUnfixable:
    """TS-20-19: Unfixable findings pass through unchanged.

    Requirements: 20-REQ-6.E4
    """

    def test_only_fixable_rules_applied(self, tmp_path: Path) -> None:
        # Create a spec with a coarse dependency (fixable)
        spec_dir = tmp_path / "02_beta"
        spec_dir.mkdir()
        (spec_dir / "prd.md").write_text(
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Core types |\n"
        )
        (spec_dir / "tasks.md").write_text(
            "# Tasks\n\n"
            "- [ ] 1. Task\n"
            "  - [ ] 1.1 Sub\n"
            "  - [ ] 1.V Verify\n"
        )

        specs = [
            SpecInfo(
                name="02_beta",
                prefix=2,
                path=spec_dir,
                has_tasks=True,
                has_prd=True,
            )
        ]

        findings = [
            Finding(
                spec_name="02_beta",
                file="prd.md",
                rule="circular-dependency",
                severity="error",
                message="Cycle detected",
                line=None,
            ),
            Finding(
                spec_name="02_beta",
                file="prd.md",
                rule="coarse-dependency",
                severity="warning",
                message="Use group-level format",
                line=None,
            ),
        ]

        known_specs = {"01_alpha": [1, 2, 3], "02_beta": [1]}
        results = apply_fixes(findings, specs, tmp_path, known_specs)
        rules_fixed = {r.rule for r in results}
        assert "coarse-dependency" in rules_fixed
        assert "circular-dependency" not in rules_fixed


# -- TS-20-20: --fix with no fixable findings is a no-op ---------------------


class TestApplyFixesNoOp:
    """TS-20-20: Verify --fix does not modify files when nothing is fixable.

    Requirements: 20-REQ-6.E1
    """

    def test_returns_empty(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "01_alpha"
        spec_dir.mkdir()
        specs = [
            SpecInfo(
                name="01_alpha",
                prefix=1,
                path=spec_dir,
                has_tasks=False,
                has_prd=False,
            )
        ]
        results = apply_fixes([], specs, tmp_path, {})
        assert len(results) == 0
