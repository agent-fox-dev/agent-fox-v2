"""Unit tests for coarse-dependency and circular-dependency lint rules.

Test Spec: TS-20-8 through TS-20-13
Requirements: 20-REQ-3.*, 20-REQ-4.*
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.validators import (
    _check_circular_dependency,
    _check_coarse_dependency,
)

# -- Helpers -------------------------------------------------------------------


def _write_prd(tmp_path: Path, content: str) -> Path:
    """Write content to a prd.md file and return its path."""
    prd_path = tmp_path / "prd.md"
    prd_path.write_text(content)
    return prd_path


def _make_spec(
    tmp_path: Path,
    name: str,
    prd_content: str,
) -> SpecInfo:
    """Create a SpecInfo with a prd.md containing the given content."""
    spec_dir = tmp_path / name
    spec_dir.mkdir(exist_ok=True)
    (spec_dir / "prd.md").write_text(prd_content)
    return SpecInfo(
        name=name,
        prefix=int(name.split("_")[0]),
        path=spec_dir,
        has_tasks=False,
        has_prd=True,
    )


# -- TS-20-8: Coarse dependency detected --------------------------------------


class TestCoarseDependencyDetected:
    """TS-20-8: Detect specs using standard dependency format.

    Requirements: 20-REQ-3.1, 20-REQ-3.2, 20-REQ-3.3
    """

    def test_returns_one_warning(self, tmp_path: Path) -> None:
        prd_path = _write_prd(
            tmp_path,
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Core types |\n",
        )
        findings = _check_coarse_dependency("02_beta", prd_path)
        assert len(findings) == 1

    def test_severity_is_warning(self, tmp_path: Path) -> None:
        prd_path = _write_prd(
            tmp_path,
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Core types |\n",
        )
        findings = _check_coarse_dependency("02_beta", prd_path)
        assert findings[0].severity == "warning"

    def test_message_mentions_group_level(self, tmp_path: Path) -> None:
        prd_path = _write_prd(
            tmp_path,
            "# PRD\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_beta | 01_alpha | Core types |\n",
        )
        findings = _check_coarse_dependency("02_beta", prd_path)
        msg = findings[0].message.lower()
        assert "group-level" in msg or "from group" in msg


# -- TS-20-9: Group-level dependency produces no finding -----------------------


class TestGroupLevelDependencyNoFinding:
    """TS-20-9: Group-level format should not be flagged.

    Requirements: 20-REQ-3.E2
    """

    def test_no_findings(self, tmp_path: Path) -> None:
        prd_path = _write_prd(
            tmp_path,
            "# PRD\n\n"
            "| Spec | From Group | To Group | Relationship |\n"
            "|------|-----------|----------|---------------|\n"
            "| 01_alpha | 3 | 1 | Uses config |\n",
        )
        findings = _check_coarse_dependency("02_beta", prd_path)
        assert len(findings) == 0


# -- TS-20-10: No dependency table produces no finding -------------------------


class TestNoDependencyTable:
    """TS-20-10: No dependency table should produce nothing.

    Requirements: 20-REQ-3.E1
    """

    def test_no_findings(self, tmp_path: Path) -> None:
        prd_path = _write_prd(
            tmp_path,
            "# PRD\n\nThis spec has no dependencies.\n",
        )
        findings = _check_coarse_dependency("01_alpha", prd_path)
        assert len(findings) == 0


# -- TS-20-11: Circular dependency detected -----------------------------------


class TestCircularDependencyDetected:
    """TS-20-11: Detect dependency cycles across specs.

    Requirements: 20-REQ-4.1, 20-REQ-4.3
    Three specs: A -> B -> C -> A (cycle).
    """

    def test_returns_at_least_one_finding(self, tmp_path: Path) -> None:
        specs = [
            _make_spec(
                tmp_path,
                "01_alpha",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 01_alpha | 03_gamma | Something |\n",
            ),
            _make_spec(
                tmp_path,
                "02_beta",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 02_beta | 01_alpha | Something |\n",
            ),
            _make_spec(
                tmp_path,
                "03_gamma",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 03_gamma | 02_beta | Something |\n",
            ),
        ]
        findings = _check_circular_dependency(specs)
        assert len(findings) >= 1

    def test_severity_is_error(self, tmp_path: Path) -> None:
        specs = [
            _make_spec(
                tmp_path,
                "01_alpha",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 01_alpha | 03_gamma | Something |\n",
            ),
            _make_spec(
                tmp_path,
                "02_beta",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 02_beta | 01_alpha | Something |\n",
            ),
            _make_spec(
                tmp_path,
                "03_gamma",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 03_gamma | 02_beta | Something |\n",
            ),
        ]
        findings = _check_circular_dependency(specs)
        assert findings[0].severity == "error"

    def test_message_lists_specs(self, tmp_path: Path) -> None:
        specs = [
            _make_spec(
                tmp_path,
                "01_alpha",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 01_alpha | 03_gamma | Something |\n",
            ),
            _make_spec(
                tmp_path,
                "02_beta",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 02_beta | 01_alpha | Something |\n",
            ),
            _make_spec(
                tmp_path,
                "03_gamma",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 03_gamma | 02_beta | Something |\n",
            ),
        ]
        findings = _check_circular_dependency(specs)
        msg = findings[0].message
        # At least some of the cycle specs should be mentioned
        assert "01_alpha" in msg or "02_beta" in msg or "03_gamma" in msg


# -- TS-20-12: Acyclic dependencies produce no cycle finding -------------------


class TestAcyclicNoCycleFinding:
    """TS-20-12: No false positives on acyclic dependency graph.

    Requirements: 20-REQ-4.2, 20-REQ-4.E2
    Specs: A -> B -> C (linear, no cycle).
    """

    def test_no_findings(self, tmp_path: Path) -> None:
        specs = [
            _make_spec(
                tmp_path,
                "01_alpha",
                "# PRD\n\nNo dependencies.\n",
            ),
            _make_spec(
                tmp_path,
                "02_beta",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 02_beta | 01_alpha | Something |\n",
            ),
            _make_spec(
                tmp_path,
                "03_gamma",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 03_gamma | 02_beta | Something |\n",
            ),
        ]
        findings = _check_circular_dependency(specs)
        assert len(findings) == 0


# -- TS-20-13: Missing spec reference skipped in cycle detection ---------------


class TestMissingSpecSkipped:
    """TS-20-13: Edges to non-existent specs are skipped.

    Requirements: 20-REQ-4.E1
    Spec A depends on "99_nonexistent" (not in discovered set).
    """

    def test_no_findings(self, tmp_path: Path) -> None:
        specs = [
            _make_spec(
                tmp_path,
                "01_alpha",
                "# PRD\n\n"
                "| This Spec | Depends On | What It Uses |\n"
                "|-----------|-----------|---------------|\n"
                "| 01_alpha | 99_nonexistent | Something |\n",
            ),
        ]
        findings = _check_circular_dependency(specs)
        assert len(findings) == 0
