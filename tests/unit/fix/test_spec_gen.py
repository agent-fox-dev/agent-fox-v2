"""Spec generator tests.

Test Spec: TS-08-10 (spec generation)
Edge Cases: TS-08-E6 (cleanup)
Requirements: 08-REQ-4.1, 08-REQ-4.2
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.fix.clusterer import FailureCluster
from agent_fox.fix.spec_gen import cleanup_fix_specs, generate_fix_spec

from .conftest import make_failure_record


class TestFixSpecGeneration:
    """TS-08-10: Fix spec generation creates directory with files.

    Requirement: 08-REQ-4.1, 08-REQ-4.2
    """

    def test_creates_spec_directory(
        self, tmp_path: Path, sample_failure_cluster: FailureCluster,
    ) -> None:
        """generate_fix_spec creates a directory under output_dir."""
        spec = generate_fix_spec(sample_failure_cluster, tmp_path, pass_number=1)
        assert spec.spec_dir.exists()
        assert spec.spec_dir.is_dir()

    def test_creates_requirements_md(
        self, tmp_path: Path, sample_failure_cluster: FailureCluster,
    ) -> None:
        """Generated spec directory contains requirements.md."""
        spec = generate_fix_spec(sample_failure_cluster, tmp_path, pass_number=1)
        assert (spec.spec_dir / "requirements.md").exists()

    def test_creates_design_md(
        self, tmp_path: Path, sample_failure_cluster: FailureCluster,
    ) -> None:
        """Generated spec directory contains design.md."""
        spec = generate_fix_spec(sample_failure_cluster, tmp_path, pass_number=1)
        assert (spec.spec_dir / "design.md").exists()

    def test_creates_tasks_md(
        self, tmp_path: Path, sample_failure_cluster: FailureCluster,
    ) -> None:
        """Generated spec directory contains tasks.md."""
        spec = generate_fix_spec(sample_failure_cluster, tmp_path, pass_number=1)
        assert (spec.spec_dir / "tasks.md").exists()

    def test_task_prompt_non_empty(
        self, tmp_path: Path, sample_failure_cluster: FailureCluster,
    ) -> None:
        """Returned FixSpec has a non-empty task_prompt."""
        spec = generate_fix_spec(sample_failure_cluster, tmp_path, pass_number=1)
        assert len(spec.task_prompt) > 0

    def test_cluster_label_in_spec(
        self, tmp_path: Path, sample_failure_cluster: FailureCluster,
    ) -> None:
        """Returned FixSpec preserves the cluster label."""
        spec = generate_fix_spec(sample_failure_cluster, tmp_path, pass_number=1)
        assert spec.cluster_label == sample_failure_cluster.label


# -- Edge case tests ---------------------------------------------------------


class TestFixSpecCleanup:
    """TS-08-E6: Fix spec cleanup removes generated directories.

    Requirement: 08-REQ-4.2
    """

    def test_cleanup_removes_all_specs(self, tmp_path: Path) -> None:
        """cleanup_fix_specs removes all generated spec directories."""
        cluster1 = FailureCluster(
            label="Test failures",
            failures=[make_failure_record()],
            suggested_approach="Fix the tests",
        )
        cluster2 = FailureCluster(
            label="Lint errors",
            failures=[make_failure_record(output="lint error")],
            suggested_approach="Fix lint issues",
        )

        generate_fix_spec(cluster1, tmp_path, pass_number=1)
        generate_fix_spec(cluster2, tmp_path, pass_number=1)

        # Verify specs exist before cleanup
        assert any(tmp_path.iterdir())

        cleanup_fix_specs(tmp_path)

        # After cleanup, no spec directories should remain
        remaining = [p for p in tmp_path.iterdir() if p.is_dir()]
        assert len(remaining) == 0
