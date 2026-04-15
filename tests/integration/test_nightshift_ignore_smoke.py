"""Integration smoke tests for the .night-shift ignore file feature.

Test Spec: TS-106-SMOKE-1, TS-106-SMOKE-2
Execution Paths: Path 1 (hunt scan applies ignore filtering),
                 Path 2 (init creates .night-shift file)
Requirements: 106-REQ-3.1, 106-REQ-3.2, 106-REQ-4.1, 106-REQ-4.2, 106-REQ-4.4
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_fox.nightshift.ignore import filter_findings, load_ignore_spec

from agent_fox.nightshift.finding import Finding
from agent_fox.nightshift.hunt import HuntCategoryRegistry, HuntScanner
from agent_fox.workspace.init_project import init_project

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    *,
    affected_files: list[str],
    category: str = "todo_fixme",
    title: str = "Smoke Test Finding",
) -> Finding:
    """Create a Finding for smoke testing."""
    return Finding(
        category=category,
        title=title,
        description="Integration smoke test finding.",
        severity="minor",
        affected_files=affected_files,
        suggested_fix="",
        evidence="",
        group_key="smoke",
    )


# ---------------------------------------------------------------------------
# TS-106-SMOKE-1: Hunt scan respects `.night-shift` file
# Execution Path 1 from design.md
# Requirements: 106-REQ-3.1, 106-REQ-3.2
# ---------------------------------------------------------------------------


class TestHuntScanRespectsNightshiftFile:
    """End-to-end test that a hunt scan filters findings based on .night-shift."""

    @pytest.mark.asyncio
    async def test_smoke_hunt_scan_filters_vendor(self, tmp_path: Path) -> None:
        """TS-106-SMOKE-1: Hunt scan excludes vendor/ paths specified in .night-shift.

        Uses real HuntScanner, real load_ignore_spec, real filter_findings.
        Only the hunt category's detect() is mocked to control findings.
        """
        # Create .night-shift excluding vendor/
        (tmp_path / ".night-shift").write_text("vendor/**\n", encoding="utf-8")

        # Build findings that span both ignored and non-ignored paths
        vendor_only = _make_finding(
            affected_files=["vendor/lib.py", "vendor/util.py"],
            category="dead_code",
            title="Dead code in vendor",
        )
        mixed = _make_finding(
            affected_files=["vendor/old.py", "src/active.py"],
            category="todo_fixme",
            title="Todo in mixed files",
        )
        src_only = _make_finding(
            affected_files=["src/main.py"],
            category="linter_debt",
            title="Lint issue in src",
        )

        all_findings = [vendor_only, mixed, src_only]

        # Create a mock category that returns these findings
        mock_category = MagicMock()
        mock_category.name = "mock_smoke_category"
        mock_category.detect = AsyncMock(return_value=all_findings)

        # Wire up a mock registry
        mock_registry = MagicMock(spec=HuntCategoryRegistry)
        mock_registry.enabled.return_value = [mock_category]

        scanner = HuntScanner(mock_registry, MagicMock())
        findings = await scanner.run(tmp_path)

        # Vendor-only finding must be dropped
        vendor_findings = [
            f for f in findings if all(p.startswith("vendor/") for p in f.affected_files)
        ]
        assert len(vendor_findings) == 0, "vendor-only finding should be filtered out"

        # No finding should have vendor/ paths in affected_files
        for finding in findings:
            for path in finding.affected_files:
                assert not path.startswith("vendor/"), (
                    f"vendor/ path {path!r} found in filtered findings"
                )

        # src_only finding must be preserved unchanged
        src_findings = [f for f in findings if f.title == "Lint issue in src"]
        assert len(src_findings) == 1
        assert src_findings[0].affected_files == ["src/main.py"]

    @pytest.mark.asyncio
    async def test_smoke_hunt_scan_uses_real_filter_and_loader(
        self, tmp_path: Path
    ) -> None:
        """TS-106-SMOKE-1: Real load_ignore_spec and filter_findings are called — not mocked."""
        # This test independently verifies the load + filter pipeline is wired
        (tmp_path / ".night-shift").write_text("generated/**\n", encoding="utf-8")

        finding_ignored = _make_finding(
            affected_files=["generated/schema.py"],
            title="In generated code",
        )
        finding_kept = _make_finding(
            affected_files=["src/logic.py"],
            title="In real code",
        )

        # Test the pipeline directly using real functions (not via scanner)
        spec = load_ignore_spec(tmp_path)  # real loader
        result = filter_findings([finding_ignored, finding_kept], spec)  # real filter

        assert len(result) == 1
        assert result[0].title == "In real code"
        assert result[0].affected_files == ["src/logic.py"]


# ---------------------------------------------------------------------------
# TS-106-SMOKE-2: Init creates `.night-shift` and it is loadable
# Execution Path 2 from design.md
# Requirements: 106-REQ-4.1, 106-REQ-4.2, 106-REQ-4.4
# ---------------------------------------------------------------------------


class TestInitCreatesLoadableNightshiftFile:
    """End-to-end test that init_project creates a .night-shift file that can be loaded."""

    def test_smoke_init_creates_loadable_nightshift(self, tmp_path: Path) -> None:
        """TS-106-SMOKE-2: init_project creates .night-shift; load_ignore_spec parses it.

        Uses real _ensure_nightshift_ignore (via init_project) and real load_ignore_spec.
        """
        # Set up minimal project structure needed by init_project
        # (init_project creates .agent-fox/ and config.toml)
        result = init_project(tmp_path, quiet=True)

        # InitResult must have nightshift_ignore field
        assert hasattr(result, "nightshift_ignore"), (
            "InitResult missing nightshift_ignore field"
        )
        assert result.nightshift_ignore == "created"

        # .night-shift file must exist
        night_shift_path = tmp_path / ".night-shift"
        assert night_shift_path.exists(), ".night-shift file was not created by init_project"

        # The file must be loadable by load_ignore_spec
        spec = load_ignore_spec(tmp_path)
        assert spec is not None

        # Default exclusions must be active
        assert spec.is_ignored(".agent-fox/state.jsonl") is True
        assert spec.is_ignored(".git/config") is True

    def test_smoke_init_idempotent_nightshift(self, tmp_path: Path) -> None:
        """TS-106-SMOKE-2: Calling init_project twice does not overwrite .night-shift."""
        # First init
        result1 = init_project(tmp_path, quiet=True)
        assert result1.nightshift_ignore == "created"

        night_shift_path = tmp_path / ".night-shift"
        original_content = night_shift_path.read_text(encoding="utf-8")

        # Add custom content to the file to detect if it's overwritten
        night_shift_path.write_text(original_content + "custom-user-pattern/**\n", encoding="utf-8")
        custom_content = night_shift_path.read_text(encoding="utf-8")

        # Second init (re-init)
        result2 = init_project(tmp_path, quiet=True)
        assert result2.nightshift_ignore == "skipped"

        # File content must be unchanged (not overwritten)
        assert night_shift_path.read_text(encoding="utf-8") == custom_content
