"""CLI command for querying review findings.

Stub module — implementation in task group 4.

Requirements: 84-REQ-4.1 through 84-REQ-4.6, 84-REQ-4.E1, 84-REQ-4.E2
"""

from __future__ import annotations

from pathlib import Path

import click

from agent_fox.core.paths import DEFAULT_DB_PATH as _DEFAULT_DB_PATH

DEFAULT_DB_PATH: Path = _DEFAULT_DB_PATH


@click.command("findings")
@click.option("--spec", default=None, help="Filter by spec name")
@click.option("--severity", default=None, help="Minimum severity level")
@click.option("--archetype", default=None, help="Filter by archetype")
@click.option("--run", "run_id", default=None, help="Filter by run ID")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON array")
def findings_cmd(
    spec: str | None,
    severity: str | None,
    archetype: str | None,
    run_id: str | None,
    json_output: bool,
) -> None:
    """Query review findings from the knowledge database.

    Stub — raises NotImplementedError until task group 4.
    """
    raise NotImplementedError("findings_cmd not yet implemented")
