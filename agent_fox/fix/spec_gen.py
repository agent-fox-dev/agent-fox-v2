"""Fix specification generator.

Generates fix specifications for each failure cluster, writing them to
`.agent-fox/fix_specs/` with requirements, design, and task files.

Requirements: 08-REQ-4.1, 08-REQ-4.2
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from agent_fox.fix.clusterer import FailureCluster  # noqa: F401

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FixSpec:
    """A generated fix specification."""

    cluster_label: str  # Label of the failure cluster
    spec_dir: Path  # Path to the generated spec directory
    task_prompt: str  # The assembled task prompt for the session


def _sanitize_label(label: str) -> str:
    """Sanitize a cluster label into a filesystem-safe directory name.

    Converts to lowercase, replaces non-alphanumeric characters with
    underscores, and collapses multiple underscores.
    """
    # Replace non-alphanumeric characters with underscores
    safe = re.sub(r"[^a-zA-Z0-9]", "_", label.lower())
    # Collapse multiple underscores
    safe = re.sub(r"_+", "_", safe)
    # Strip leading/trailing underscores
    safe = safe.strip("_")
    return safe or "unnamed"


def _build_requirements_md(cluster: FailureCluster) -> str:
    """Build the requirements.md content for a failure cluster."""
    lines = [
        f"# Fix: {cluster.label}",
        "",
        "## Problem",
        "",
        "The following quality check failures need to be fixed:",
        "",
    ]

    for i, failure in enumerate(cluster.failures):
        lines.append(f"### Failure {i + 1}: {failure.check.name} (exit code {failure.exit_code})")
        lines.append("")
        lines.append("```")
        lines.append(failure.output)
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "## Requirements",
            "",
            "- [ ] All failures listed above must be resolved",
            "- [ ] Quality checks must pass after the fix",
        ]
    )

    return "\n".join(lines)


def _build_design_md(cluster: FailureCluster) -> str:
    """Build the design.md content for a failure cluster."""
    lines = [
        f"# Fix Approach: {cluster.label}",
        "",
        "## Suggested Approach",
        "",
        cluster.suggested_approach,
        "",
        "## Affected Checks",
        "",
    ]

    check_names = {f.check.name for f in cluster.failures}
    for name in sorted(check_names):
        lines.append(f"- {name}")

    return "\n".join(lines)


def _build_tasks_md(cluster: FailureCluster) -> str:
    """Build the tasks.md content for a failure cluster."""
    lines = [
        f"# Tasks: Fix {cluster.label}",
        "",
        "## Tasks",
        "",
        f"- [ ] 1. Fix: {cluster.label}",
    ]

    for i, failure in enumerate(cluster.failures):
        lines.append(f"  - [ ] 1.{i + 1} Resolve {failure.check.name} failure")

    lines.extend(
        [
            "",
            "- [ ] 2. Verify all quality checks pass",
        ]
    )

    return "\n".join(lines)


def _build_task_prompt(cluster: FailureCluster) -> str:
    """Build the task prompt for the session runner."""
    lines = [
        f"Fix the following quality check failures: {cluster.label}",
        "",
        f"Suggested approach: {cluster.suggested_approach}",
        "",
        "Failure details:",
        "",
    ]

    for i, failure in enumerate(cluster.failures):
        lines.append(f"[{i + 1}] {failure.check.name} (exit code {failure.exit_code}):")
        lines.append(failure.output)
        lines.append("")

    lines.append("Fix all failures and verify that the checks pass.")

    return "\n".join(lines)


def generate_fix_spec(
    cluster: FailureCluster,
    output_dir: Path,
    pass_number: int,
) -> FixSpec:
    """Generate a fix specification for a failure cluster.

    Creates a directory under output_dir with:
    - requirements.md: what needs to be fixed
    - design.md: suggested approach
    - tasks.md: task list for the session

    The task_prompt field contains the fully assembled prompt for the
    session runner, including failure output and fix instructions.
    """
    # Build filesystem-safe directory name
    sanitized = _sanitize_label(cluster.label)
    dir_name = f"pass_{pass_number}_{sanitized}"
    spec_dir = output_dir / dir_name
    spec_dir.mkdir(parents=True, exist_ok=True)

    # Write specification files
    (spec_dir / "requirements.md").write_text(_build_requirements_md(cluster), encoding="utf-8")
    (spec_dir / "design.md").write_text(_build_design_md(cluster), encoding="utf-8")
    (spec_dir / "tasks.md").write_text(_build_tasks_md(cluster), encoding="utf-8")

    # Build the task prompt
    task_prompt = _build_task_prompt(cluster)

    logger.info("Generated fix spec for '%s' at %s", cluster.label, spec_dir)

    return FixSpec(
        cluster_label=cluster.label,
        spec_dir=spec_dir,
        task_prompt=task_prompt,
    )


def cleanup_fix_specs(output_dir: Path) -> None:
    """Remove all generated fix spec directories."""
    if not output_dir.exists():
        return

    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    logger.info("Cleaned up fix specs in %s", output_dir)
