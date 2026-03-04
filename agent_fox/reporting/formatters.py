"""Output formatters: table (Rich), JSON, YAML.

Requirements: 07-REQ-3.1, 07-REQ-3.2, 07-REQ-3.3, 07-REQ-3.4
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import asdict
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import yaml
from rich.console import Console

from agent_fox.core.errors import AgentFoxError
from agent_fox.reporting.standup import StandupReport
from agent_fox.reporting.status import StatusReport

logger = logging.getLogger(__name__)


def format_tokens(count: int) -> str:
    """Format token count for human readability.

    Args:
        count: Raw token count.

    Returns:
        "1.5M" for counts >= 1_000_000, "12.9k" for counts >= 1000,
        "345" for counts < 1000.

    Requirements: 15-REQ-7.1
    """
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
        """Render status report as compact text lines."""
        lines: list[str] = []

        # Tasks line
        done = report.counts.get("completed", 0)
        in_progress = report.counts.get("in_progress", 0)
        pending = report.counts.get("pending", 0)
        failed = report.counts.get("failed", 0)
        lines.append(
            f"Tasks: {done}/{report.total_tasks} done | "
            f"{in_progress} in progress | "
            f"{pending} pending | "
            f"{failed} failed"
        )

        # Memory line
        if report.memory_total > 0:
            cat_parts = ", ".join(
                f"{count} {cat}"
                for cat, count in sorted(report.memory_by_category.items())
            )
            lines.append(f"Memory: {report.memory_total} facts ({cat_parts})")
        else:
            lines.append("Memory: 0 facts")

        # Tokens line
        in_tok = format_tokens(report.input_tokens)
        out_tok = format_tokens(report.output_tokens)
        lines.append(
            f"Tokens: {in_tok} in / {out_tok} out | ${report.estimated_cost:.2f}"
        )

        # Problem tasks (compact)
        if report.problem_tasks:
            lines.append("")
            lines.append("Problems:")
            for task in report.problem_tasks:
                lines.append(f"  {task.task_id}: {task.status} — {task.reason}")

        return "\n".join(lines) + "\n"

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
                in_tok = format_tokens(ta.input_tokens)
                out_tok = format_tokens(ta.output_tokens)
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
            display_ids = ", ".join(_display_node_id(tid) for tid in q.ready_task_ids)
            lines.append(f"  Ready: {display_ids}")
        lines.append("")

        # File Overlaps section — omitted when empty (15-REQ-5.1, 15-REQ-5.E1)
        if report.file_overlaps:
            lines.append("Heads Up \u2014 File Overlaps")
            for overlap in report.file_overlaps:
                commit_shas = ", ".join(sha[:7] for sha in overlap.human_commits)
                agent_ids = ", ".join(
                    _display_node_id(tid) for tid in overlap.agent_task_ids
                )
                lines.append(
                    f"  {overlap.path} \u2014 "
                    f"commits: {commit_shas} | agents: {agent_ids}"
                )
            lines.append("")

        # Total Cost line (15-REQ-6.1, 15-REQ-6.E1)
        lines.append(f"Total Cost: ${report.total_cost:.2f}")

        return "\n".join(lines)


class StructuredFormatter:
    """Formatter that serializes reports via a pluggable serializer."""

    def __init__(
        self,
        serializer: Callable[[dict[str, Any]], str],
    ) -> None:
        self._serializer = serializer

    def format_status(self, report: StatusReport) -> str:
        """Serialize status report."""
        return self._serializer(asdict(report))

    def format_standup(self, report: StandupReport) -> str:
        """Serialize standup report."""
        return self._serializer(asdict(report))


def _json_serializer(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2)


def _yaml_serializer(data: dict[str, Any]) -> str:
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def JsonFormatter() -> StructuredFormatter:  # noqa: N802
    """JSON formatter for machine-readable output."""
    return StructuredFormatter(_json_serializer)


def YamlFormatter() -> StructuredFormatter:  # noqa: N802
    """YAML formatter for human-readable structured output."""
    return StructuredFormatter(_yaml_serializer)


_FORMATTERS: dict[OutputFormat, Callable[..., ReportFormatter]] = {
    OutputFormat.TABLE: lambda console: TableFormatter(console),  # type: ignore[dict-item]
    OutputFormat.JSON: lambda _: JsonFormatter(),  # type: ignore[dict-item]
    OutputFormat.YAML: lambda _: YamlFormatter(),  # type: ignore[dict-item]
}


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
    factory = _FORMATTERS.get(fmt)
    if factory is None:
        msg = f"Unknown output format: {fmt}"
        raise ValueError(msg)
    return factory(console)


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
