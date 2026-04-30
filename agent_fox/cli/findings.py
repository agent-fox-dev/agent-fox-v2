"""CLI command for querying review findings.

Implements the `agent-fox findings` command that queries the knowledge
database for review findings and displays them in a formatted table or
as JSON.

Requirements: 84-REQ-4.1 through 84-REQ-4.6, 84-REQ-4.E1, 84-REQ-4.E2
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
import duckdb

from agent_fox.core.paths import DEFAULT_DB_PATH as _DEFAULT_DB_PATH

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH: Path = _DEFAULT_DB_PATH


@click.command("insights")
@click.option("--spec", default=None, help="Filter by spec name")
@click.option("--severity", default=None, help="Minimum severity level (critical, major, minor, observation)")
@click.option("--archetype", default=None, help="Filter by archetype (skeptic, verifier, oracle)")
@click.option("--run", "run_id", default=None, help="Filter by run ID")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON array")
@click.option(
    "--dismiss",
    nargs=2,
    default=None,
    metavar="ID REASON",
    help="Dismiss a finding by ID: --dismiss <finding-id> <reason>",
)
def findings_cmd(
    spec: str | None,
    severity: str | None,
    archetype: str | None,
    run_id: str | None,
    json_output: bool,
    dismiss: tuple[str, str] | None,
) -> None:
    """Query review findings from the knowledge database.

    Displays active (non-superseded) review findings from skeptic,
    verifier, and oracle archetypes. Use filters to narrow results.

    To dismiss a stale or false-positive finding, use:

        agent-fox insights --dismiss <finding-id> "reason for dismissal"

    Requirements: 84-REQ-4.1 through 84-REQ-4.6, 84-REQ-4.E1, 84-REQ-4.E2,
                  592-AC-3, 592-AC-4
    """
    from agent_fox.knowledge.review_store import dismiss_finding_by_id
    from agent_fox.reporting.findings import format_findings_table, query_findings

    # 84-REQ-4.E1: Handle missing DB gracefully
    if not DEFAULT_DB_PATH.exists():
        click.echo("No knowledge database found")
        return

    try:
        conn = duckdb.connect(str(DEFAULT_DB_PATH))
    except Exception:
        logger.debug("Failed to open knowledge database", exc_info=True)
        click.echo("No knowledge database found")
        return

    dismiss_not_found = False
    dismiss_result: str | None = None
    rows = []

    try:
        if dismiss is not None:
            finding_id, reason = dismiss
            dismiss_result = dismiss_finding_by_id(conn, finding_id, reason)
            if dismiss_result is None:
                dismiss_not_found = True
        else:
            rows = query_findings(
                conn,
                spec=spec,
                severity=severity,
                archetype=archetype,
                run_id=run_id,
                active_only=True,
            )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if dismiss is not None:
        finding_id, reason = dismiss
        if dismiss_not_found:
            click.echo(f"Finding {finding_id} not found", err=True)
            sys.exit(1)
        click.echo(f"Dismissed: {dismiss_result}")
        click.echo(f"Reason: {reason}")
        return

    # 84-REQ-4.E2: Handle empty results gracefully
    if not rows:
        click.echo("No findings match the given filters")
        return

    output = format_findings_table(rows, json_output=json_output)
    click.echo(output)
