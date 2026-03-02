"""Fix specification generator.

Generates fix specifications for each failure cluster, writing them to
`.agent-fox/fix_specs/` with requirements, design, and task files.

Requirements: 08-REQ-4.1, 08-REQ-4.2
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_fox.fix.clusterer import FailureCluster  # noqa: F401


@dataclass(frozen=True)
class FixSpec:
    """A generated fix specification."""

    cluster_label: str  # Label of the failure cluster
    spec_dir: Path  # Path to the generated spec directory
    task_prompt: str  # The assembled task prompt for the session


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
    raise NotImplementedError


def cleanup_fix_specs(output_dir: Path) -> None:
    """Remove all generated fix spec directories."""
    raise NotImplementedError
