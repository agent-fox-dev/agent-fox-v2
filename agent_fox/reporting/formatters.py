"""Output formatters: table (Rich), JSON, YAML.

Requirements: 07-REQ-3.1, 07-REQ-3.2, 07-REQ-3.3, 07-REQ-3.4
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from enum import StrEnum
from io import StringIO
from pathlib import Path
from typing import Protocol

import yaml
from rich.console import Console
from rich.table import Table
from rich.text import Text

from agent_fox.core.errors import AgentFoxError
from agent_fox.reporting.standup import StandupReport
from agent_fox.reporting.status import StatusReport

logger = logging.getLogger(__name__)


def _format_tokens(count: int) -> str:
    """Format token count for human readability.

    Args:
        count: Raw token count.

    Returns:
        "12.9k" for counts >= 1000, "345" for counts < 1000.

    Requirements: 15-REQ-7.1
    """
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
    YAML = "yaml"


class ReportFormatter(Protocol):
    """Protocol for report formatters."""

    def format_status(self, report: StatusReport) -> str: ...
    def format_standup(self, report: StandupReport) -> str: ...


class TableFormatter:
    """Rich table formatter for terminal output."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def format_status(self, report: StatusReport) -> str:
        """Render status report as Rich tables."""
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=100)

        # Progress summary table
        progress_table = Table(
            title="Task Progress",
            show_header=True,
            header_style="bold",
        )
        progress_table.add_column("Status", style="bold")
        progress_table.add_column("Count", justify="right")

        status_styles = {
            "completed": "green",
            "failed": "red",
            "blocked": "yellow",
            "in_progress": "cyan",
            "pending": "dim",
            "skipped": "dim",
        }
        for status, count in sorted(report.counts.items()):
            style = status_styles.get(status, "")
            progress_table.add_row(
                Text(status, style=style),
                str(count),
            )
        progress_table.add_row(
            Text("TOTAL", style="bold"),
            str(report.total_tasks),
        )
        console.print(progress_table)

        # Token and cost summary
        cost_table = Table(
            title="Resource Usage",
            show_header=True,
            header_style="bold",
        )
        cost_table.add_column("Metric")
        cost_table.add_column("Value", justify="right")
        cost_table.add_row("Input Tokens", f"{report.input_tokens:,}")
        cost_table.add_row("Output Tokens", f"{report.output_tokens:,}")
        cost_table.add_row(
            "Estimated Cost",
            f"${report.estimated_cost:.2f}",
        )
        console.print(cost_table)

        # Problem tasks
        if report.problem_tasks:
            problem_table = Table(
                title="Problem Tasks",
                show_header=True,
                header_style="bold",
            )
            problem_table.add_column("Task ID")
            problem_table.add_column("Title")
            problem_table.add_column("Status")
            problem_table.add_column("Reason")
            for task in report.problem_tasks:
                status_style = "red" if task.status == "failed" else "yellow"
                problem_table.add_row(
                    task.task_id,
                    task.title,
                    Text(task.status, style=status_style),
                    task.reason,
                )
            console.print(problem_table)

        return buf.getvalue()

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

            Queue Status
              {total} total: {done} done | {in_progress} in progress | ...
              Ready: {id1}, {id2}

            Heads Up — File Overlaps
              {path} — commits: {sha1}, {sha2} | agents: {task1}, {task2}

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
                in_tok = _format_tokens(ta.input_tokens)
                out_tok = _format_tokens(ta.output_tokens)
                lines.append(
                    f"  {display_id}: {ta.current_status}. "
                    f"{ta.completed_sessions}/{ta.total_sessions} sessions. "
                    f"tokens {in_tok} in / {out_tok} out. "
                    f"${ta.cost:.2f}"
                )
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

        # Queue Status section (15-REQ-4.1, 15-REQ-4.2, 15-REQ-4.E1)
        lines.append("Queue Status")
        q = report.queue
        lines.append(
            f"  {q.total} total: {q.completed} done | "
            f"{q.in_progress} in progress | "
            f"{q.pending} pending | {q.ready} ready | "
            f"{q.blocked} blocked | {q.failed} failed"
        )
        if q.ready_task_ids:
            display_ids = ", ".join(
                _display_node_id(tid) for tid in q.ready_task_ids
            )
            lines.append(f"  Ready: {display_ids}")
        lines.append("")

        # File Overlaps section — omitted when empty (15-REQ-5.1, 15-REQ-5.E1)
        if report.file_overlaps:
            lines.append("Heads Up \u2014 File Overlaps")
            for overlap in report.file_overlaps:
                commit_shas = ", ".join(
                    sha[:7] for sha in overlap.human_commits
                )
                agent_ids = ", ".join(
                    _display_node_id(tid)
                    for tid in overlap.agent_task_ids
                )
                lines.append(
                    f"  {overlap.path} \u2014 "
                    f"commits: {commit_shas} | agents: {agent_ids}"
                )
            lines.append("")

        # Total Cost line (15-REQ-6.1, 15-REQ-6.E1)
        lines.append(f"Total Cost: ${report.total_cost:.2f}")

        return "\n".join(lines)


class JsonFormatter:
    """JSON formatter for machine-readable output."""

    def format_status(self, report: StatusReport) -> str:
        """Serialize status report as JSON."""
        return json.dumps(asdict(report), indent=2)

    def format_standup(self, report: StandupReport) -> str:
        """Serialize standup report as JSON."""
        return json.dumps(asdict(report), indent=2)


class YamlFormatter:
    """YAML formatter for human-readable structured output."""

    def format_status(self, report: StatusReport) -> str:
        """Serialize status report as YAML."""
        return yaml.dump(
            asdict(report),
            default_flow_style=False,
            sort_keys=False,
        )

    def format_standup(self, report: StandupReport) -> str:
        """Serialize standup report as YAML."""
        return yaml.dump(
            asdict(report),
            default_flow_style=False,
            sort_keys=False,
        )


def get_formatter(
    fmt: OutputFormat,
    console: Console | None = None,
) -> ReportFormatter:
    """Factory function to create the appropriate formatter.

    Args:
        fmt: The desired output format.
        console: Rich console instance (required for table format).

    Returns:
        A formatter implementing ReportFormatter.
    """
    if fmt == OutputFormat.TABLE:
        return TableFormatter(console)  # type: ignore[return-value]
    if fmt == OutputFormat.JSON:
        return JsonFormatter()  # type: ignore[return-value]
    if fmt == OutputFormat.YAML:
        return YamlFormatter()  # type: ignore[return-value]
    msg = f"Unknown output format: {fmt}"
    raise ValueError(msg)


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
