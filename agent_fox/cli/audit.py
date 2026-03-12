"""CLI command for querying the structured audit log.

Requirements: 40-REQ-13.1, 40-REQ-13.2, 40-REQ-13.3, 40-REQ-13.4,
              40-REQ-13.5, 40-REQ-13.6, 40-REQ-13.7,
              40-REQ-13.E1, 40-REQ-13.E2
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click

logger = logging.getLogger(__name__)

# Default DuckDB path relative to project root
_DEFAULT_DB_PATH = Path(".agent-fox/knowledge.db")


def _get_audit_conn():
    """Open a DuckDB connection to the knowledge database.

    Returns None if the database does not exist or the audit_events table
    is missing.

    Requirements: 40-REQ-13.E2
    """
    try:
        import duckdb

        db_path = _DEFAULT_DB_PATH
        if not db_path.exists():
            return None

        conn = duckdb.connect(str(db_path), read_only=True)
        # Verify the audit_events table exists
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        if "audit_events" not in tables:
            conn.close()
            return None
        return conn
    except Exception:
        logger.debug("Failed to open audit database", exc_info=True)
        return None


def _parse_since(since: str) -> datetime | None:
    """Parse a --since value to a UTC datetime.

    Accepts:
    - Relative durations: ``24h``, ``7d``, ``30m``
    - ISO-8601 datetime strings

    Returns None if parsing fails.
    """
    # Relative duration: e.g. "24h", "7d", "30m"
    match = re.fullmatch(r"(\d+)([hHdDmM])", since.strip())
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        if unit == "h":
            delta = timedelta(hours=amount)
        elif unit == "d":
            delta = timedelta(days=amount)
        elif unit == "m":
            delta = timedelta(minutes=amount)
        else:
            delta = timedelta(hours=amount)
        return datetime.now(UTC) - delta

    # ISO-8601 datetime
    try:
        dt = datetime.fromisoformat(since)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        pass

    return None


def _format_row(row: dict) -> str:
    """Format a single audit event row as a human-readable string."""
    ts = row.get("timestamp", "")
    run_id = row.get("run_id", "")
    event_type = row.get("event_type", "")
    severity = row.get("severity", "info")
    node_id = row.get("node_id", "")
    parts = [f"{ts}  {run_id}  {event_type}  [{severity}]"]
    if node_id:
        parts.append(f"  node={node_id}")
    return "".join(parts)


@click.command("audit")
@click.option("--list-runs", is_flag=True, help="List available run IDs.")
@click.option("--run", "run_id", default=None, help="Filter by run ID.")
@click.option(
    "--event-type", "event_type", default=None, help="Filter by event type."
)
@click.option("--node-id", "node_id", default=None, help="Filter by node ID.")
@click.option(
    "--since",
    default=None,
    help="Filter events after datetime (ISO-8601 or relative: 24h, 7d).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Output as JSON.",
)
def audit_cmd(
    list_runs: bool,
    run_id: str | None,
    event_type: str | None,
    node_id: str | None,
    since: str | None,
    json_output: bool,
) -> None:
    """Query the structured audit log.

    Requirements: 40-REQ-13.1 through 40-REQ-13.7, 40-REQ-13.E1, 40-REQ-13.E2
    """
    conn = _get_audit_conn()

    if conn is None:
        click.echo("No audit data available. Run agent-fox to generate audit events.")
        return

    try:
        if list_runs:
            _cmd_list_runs(conn, json_output=json_output)
        else:
            _cmd_query_events(
                conn,
                run_id=run_id,
                event_type=event_type,
                node_id=node_id,
                since=since,
                json_output=json_output,
            )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _cmd_list_runs(conn, *, json_output: bool) -> None:
    """List all available run IDs with timestamps and event counts.

    Requirements: 40-REQ-13.2
    """
    rows = conn.execute(
        """
        SELECT
            run_id,
            MIN(timestamp) AS first_event,
            MAX(timestamp) AS last_event,
            COUNT(*) AS event_count
        FROM audit_events
        GROUP BY run_id
        ORDER BY MIN(timestamp) DESC
        """
    ).fetchall()

    if json_output:
        data = [
            {
                "run_id": row[0],
                "first_event": str(row[1]),
                "last_event": str(row[2]),
                "event_count": row[3],
            }
            for row in rows
        ]
        click.echo(json.dumps(data, indent=2))
        return

    if not rows:
        click.echo("No runs found.")
        return

    # Header
    click.echo(f"{'RUN ID':<35}  {'FIRST EVENT':<25}  {'EVENTS':>6}")
    click.echo("-" * 72)
    for run_id, first_event, _last_event, event_count in rows:
        click.echo(f"{run_id:<35}  {str(first_event):<25}  {event_count:>6}")


def _cmd_query_events(
    conn,
    *,
    run_id: str | None,
    event_type: str | None,
    node_id: str | None,
    since: str | None,
    json_output: bool,
) -> None:
    """Query audit events with optional filters.

    Requirements: 40-REQ-13.3, 40-REQ-13.4, 40-REQ-13.5, 40-REQ-13.6
    """
    conditions: list[str] = []
    params: list = []

    if run_id is not None:
        conditions.append("run_id = ?")
        params.append(run_id)

    if event_type is not None:
        conditions.append("event_type = ?")
        params.append(event_type)

    if node_id is not None:
        conditions.append("node_id = ?")
        params.append(node_id)

    if since is not None:
        since_dt = _parse_since(since)
        if since_dt is not None:
            conditions.append("timestamp >= ?")
            params.append(since_dt)
        else:
            click.echo(
                f"Warning: could not parse --since value {since!r}. Ignoring.",
                err=True,
            )

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"""
        SELECT
            id, timestamp, run_id, event_type, node_id,
            session_id, archetype, severity, payload
        FROM audit_events
        {where_clause}
        ORDER BY timestamp ASC
    """

    rows = conn.execute(query, params).fetchall()

    if json_output:
        data = []
        for row in rows:
            payload_raw = row[8]
            try:
                payload = (
                    json.loads(payload_raw)
                    if isinstance(payload_raw, str)
                    else payload_raw
                )
            except (json.JSONDecodeError, TypeError):
                payload = {}
            data.append(
                {
                    "id": row[0],
                    "timestamp": str(row[1]),
                    "run_id": row[2],
                    "event_type": row[3],
                    "node_id": row[4],
                    "session_id": row[5],
                    "archetype": row[6],
                    "severity": row[7],
                    "payload": payload,
                }
            )
        click.echo(json.dumps(data, indent=2))
        return

    # Requirements: 40-REQ-13.E1: empty result exits 0 (handled by return)
    if not rows:
        return

    for row in rows:
        row_dict = {
            "timestamp": str(row[1]),
            "run_id": row[2],
            "event_type": row[3],
            "node_id": row[4] or "",
            "severity": row[7],
        }
        click.echo(_format_row(row_dict))
