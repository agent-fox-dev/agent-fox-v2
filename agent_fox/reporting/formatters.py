"""Output formatters: table (Rich), JSON, YAML.

Requirements: 07-REQ-3.1, 07-REQ-3.2, 07-REQ-3.3, 07-REQ-3.4
"""

from __future__ import annotations

# noqa: F401 -- imported for patching in tests
import json  # noqa: F401
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import rich  # noqa: F401

from agent_fox.reporting.standup import StandupReport
from agent_fox.reporting.status import StatusReport


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

    def __init__(self, console: object | None = None) -> None:
        self._console = console

    def format_status(self, report: StatusReport) -> str:
        """Render status report as Rich tables."""
        raise NotImplementedError

    def format_standup(self, report: StandupReport) -> str:
        """Render standup report as Rich tables."""
        raise NotImplementedError


class JsonFormatter:
    """JSON formatter for machine-readable output."""

    def format_status(self, report: StatusReport) -> str:
        """Serialize status report as JSON."""
        raise NotImplementedError

    def format_standup(self, report: StandupReport) -> str:
        """Serialize standup report as JSON."""
        raise NotImplementedError


class YamlFormatter:
    """YAML formatter for human-readable structured output."""

    def format_status(self, report: StatusReport) -> str:
        """Serialize status report as YAML."""
        raise NotImplementedError

    def format_standup(self, report: StandupReport) -> str:
        """Serialize standup report as YAML."""
        raise NotImplementedError


def get_formatter(
    fmt: OutputFormat,
    console: object | None = None,
) -> ReportFormatter:
    """Factory function to create the appropriate formatter.

    Args:
        fmt: The desired output format.
        console: Rich console instance (required for table format).

    Returns:
        A formatter implementing ReportFormatter.
    """
    raise NotImplementedError


def write_output(
    content: str,
    output_path: Path | None = None,
    console: object | None = None,
) -> None:
    """Write formatted output to stdout or a file.

    Args:
        content: The formatted report string.
        output_path: If set, write to this file instead of stdout.
        console: Rich console for styled stdout output.

    Raises:
        AgentFoxError: If the output path is not writable.
    """
    raise NotImplementedError
