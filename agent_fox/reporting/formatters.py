"""Output formatters: table (Rich) and JSON.

Requirements: 07-REQ-3.1, 07-REQ-3.2, 07-REQ-3.4,
              23-REQ-8.4, 23-REQ-8.5
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from enum import StrEnum
from pathlib import Path

from rich.console import Console

from agent_fox.core.errors import AgentFoxError
from agent_fox.reporting.standup import StandupReport

logger = logging.getLogger(__name__)


def format_tokens(count: int | None) -> str:
    """Format token count for human readability.

    Args:
        count: Raw token count, or None if unavailable.

    Returns:
        "?k" if None, "1.5M" for counts >= 1_000_000,
        "12.9k" for counts >= 1000, "345" for counts < 1000.

    Requirements: 15-REQ-7.1
    """
    if count is None:
        return "?k"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1000:
        return f"{count / 1000:.1f}k"
    return str(count)


def _display_node_id(node_id: str) -> str:
    """Convert internal node ID to display format.

    Args:
        node_id: Internal format "spec_name:group_number".

    Returns:
        Display format "spec_name/group_number".

    Requirements: 15-REQ-8.1
    """
    return node_id.replace(":", "/")


class OutputFormat(StrEnum):
    TABLE = "table"
    JSON = "json"


class TableFormatter:
    """Rich table formatter for terminal output."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def format_standup(self, report: StandupReport) -> str:
        """Render standup report as indented plain text.

        Output structure:
            Standup Report — last {hours}h
            Generated: {timestamp}

            Agent Activity
              {task_id}: {status}. {n}/{m} sessions. tokens ...
              ...

            Human Commits
              {sha7} {author}: {subject}
              ...

            Cost by Spec:
              {spec}: ${cost}

            Cost by Archetype:
              {archetype}: ${cost}

            Total Cost: ${all_time}

        Requirements: 15-REQ-1.1, 15-REQ-1.2, 15-REQ-1.3, 15-REQ-2.1,
                      15-REQ-2.2, 15-REQ-3.1, 15-REQ-4.1, 15-REQ-4.2,
                      15-REQ-5.1, 15-REQ-6.1, 15-REQ-8.2
        """
        lines: list[str] = []

        # Header (15-REQ-1.1, 15-REQ-1.2, 15-REQ-1.3)
        lines.append(f"Standup Report \u2014 last {report.window_hours}h")
        lines.append(f"Generated: {report.window_end}")
        lines.append("")

        # Agent Activity section (15-REQ-2.1, 15-REQ-2.2, 15-REQ-2.E1)
        lines.append("Agent Activity")
        if report.task_activities:
            for ta in report.task_activities:
                display_id = _display_node_id(ta.task_id)
                if ta.total_sessions > 0:
                    in_tok = format_tokens(ta.input_tokens)
                    out_tok = format_tokens(ta.output_tokens)
                    lines.append(
                        f"  {display_id} [{ta.archetype}]: {ta.current_status}. "
                        f"{ta.completed_sessions}/{ta.total_sessions} sessions. "
                        f"tokens {in_tok} in / {out_tok} out. "
                        f"${ta.cost:.2f}"
                    )
                else:
                    lines.append(f"  {display_id} [{ta.archetype}]: {ta.current_status}")
        else:
            lines.append("  (no agent activity)")
        lines.append("")

        # Agent Commits section
        lines.append("Agent Commits")
        if report.agent_commits:
            for commit in report.agent_commits:
                sha7 = commit.sha[:7]
                lines.append(f"  {sha7} {commit.subject}")
        else:
            lines.append("  (no agent commits)")
        lines.append("")

        # Human Commits section (15-REQ-3.1, 15-REQ-3.E1)
        lines.append("Human Commits")
        if report.human_commits:
            for commit in report.human_commits:
                sha7 = commit.sha[:7]
                lines.append(f"  {sha7} {commit.author}: {commit.subject}")
        else:
            lines.append("  (no human commits)")
        lines.append("")

        # Per-spec cost breakdown
        if report.cost_by_spec:
            lines.append("Cost by Spec:")
            for spec, cost in sorted(report.cost_by_spec.items()):
                lines.append(f"  {spec}: ${cost:.2f}")
            lines.append("")

        # Per-archetype cost breakdown
        if report.cost_by_archetype:
            lines.append("Cost by Archetype:")
            for archetype, cost in sorted(report.cost_by_archetype.items()):
                lines.append(f"  {archetype}: ${cost:.2f}")
            lines.append("")

        # Total Cost line (15-REQ-6.1, 15-REQ-6.E1)
        if report.total_cost is None:
            lines.append("Total Cost: no session data")
        else:
            lines.append(f"Total Cost: ${report.total_cost:.2f}")

        return "\n".join(lines)


class JsonFormatter:
    """JSON formatter for machine-readable output."""

    def format_standup(self, report: StandupReport) -> str:
        """Serialize standup report as JSON."""
        return json.dumps(asdict(report), indent=2)


def get_formatter(
    fmt: OutputFormat,
    console: Console | None = None,
) -> TableFormatter | JsonFormatter:
    """Create the appropriate formatter for the given output format."""
    if fmt == OutputFormat.JSON:
        return JsonFormatter()
    return TableFormatter(console)


def write_output(
    content: str,
    output_path: Path | None = None,
    console: Console | None = None,
) -> None:
    """Write formatted output to stdout or a file.

    Args:
        content: The formatted report string.
        output_path: If set, write to this file instead of stdout.
        console: Rich console for styled stdout output.

    Raises:
        AgentFoxError: If the output path is not writable.
    """
    if output_path is not None:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content)
        except OSError as exc:
            raise AgentFoxError(
                f"Cannot write to {output_path}: {exc}",
                path=str(output_path),
            ) from exc
    elif console is not None:
        console.print(content, end="")
    else:
        print(content, end="")  # noqa: T201
