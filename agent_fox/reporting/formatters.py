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
                Text(status, style=style), str(count),
            )
        progress_table.add_row(
            Text("TOTAL", style="bold"), str(report.total_tasks),
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
            "Estimated Cost", f"${report.estimated_cost:.2f}",
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
        """Render standup report as Rich tables."""
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=100)

        # Header
        console.print(
            f"\n[bold]Standup Report[/bold] "
            f"(last {report.window_hours} hours)",
        )
        console.print(
            f"Window: {report.window_start} to {report.window_end}\n",
        )

        # Agent activity
        agent_table = Table(
            title="Agent Activity",
            show_header=True,
            header_style="bold",
        )
        agent_table.add_column("Metric")
        agent_table.add_column("Value", justify="right")
        agent_table.add_row(
            "Tasks Completed", str(report.agent.tasks_completed),
        )
        agent_table.add_row("Sessions Run", str(report.agent.sessions_run))
        agent_table.add_row(
            "Input Tokens", f"{report.agent.input_tokens:,}",
        )
        agent_table.add_row(
            "Output Tokens", f"{report.agent.output_tokens:,}",
        )
        agent_table.add_row("Cost", f"${report.agent.cost:.2f}")
        console.print(agent_table)

        # Human commits
        if report.human_commits:
            commits_table = Table(
                title="Human Commits",
                show_header=True,
                header_style="bold",
            )
            commits_table.add_column("SHA", max_width=8)
            commits_table.add_column("Author")
            commits_table.add_column("Subject")
            commits_table.add_column("Files", justify="right")
            for commit in report.human_commits:
                commits_table.add_row(
                    commit.sha[:8],
                    commit.author,
                    commit.subject,
                    str(len(commit.files_changed)),
                )
            console.print(commits_table)

        # File overlaps
        if report.file_overlaps:
            overlap_table = Table(
                title="File Overlaps (agent + human)",
                show_header=True,
                header_style="bold",
            )
            overlap_table.add_column("File Path")
            overlap_table.add_column("Agent Tasks")
            overlap_table.add_column("Human Commits")
            for overlap in report.file_overlaps:
                overlap_table.add_row(
                    overlap.path,
                    ", ".join(overlap.agent_task_ids),
                    str(len(overlap.human_commits)),
                )
            console.print(overlap_table)

        # Cost breakdown
        if report.cost_breakdown:
            cost_table = Table(
                title="Cost Breakdown",
                show_header=True,
                header_style="bold",
            )
            cost_table.add_column("Tier")
            cost_table.add_column("Sessions", justify="right")
            cost_table.add_column("Cost", justify="right")
            for cb in report.cost_breakdown:
                cost_table.add_row(
                    cb.tier, str(cb.sessions), f"${cb.cost:.2f}",
                )
            console.print(cost_table)

        # Queue summary
        queue_table = Table(
            title="Task Queue",
            show_header=True,
            header_style="bold",
        )
        queue_table.add_column("Status")
        queue_table.add_column("Count", justify="right")
        queue_table.add_row("Ready", str(report.queue.ready))
        queue_table.add_row("Pending", str(report.queue.pending))
        queue_table.add_row("Blocked", str(report.queue.blocked))
        queue_table.add_row("Failed", str(report.queue.failed))
        queue_table.add_row("Completed", str(report.queue.completed))
        console.print(queue_table)

        return buf.getvalue()


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
            asdict(report), default_flow_style=False, sort_keys=False,
        )

    def format_standup(self, report: StandupReport) -> str:
        """Serialize standup report as YAML."""
        return yaml.dump(
            asdict(report), default_flow_style=False, sort_keys=False,
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
