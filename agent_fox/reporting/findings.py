"""Query and format review findings from DuckDB.

Stub module — implementation in task group 4.

Requirements: 84-REQ-4.1 through 84-REQ-4.6, 84-REQ-5.1, 84-REQ-5.2
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FindingRow:
    """Unified row for displaying findings from any review table."""

    id: str
    severity: str
    archetype: str  # "skeptic", "verifier", "oracle"
    spec_name: str
    task_group: str
    description: str
    created_at: datetime


@dataclass(frozen=True)
class FindingsSummary:
    """Per-spec summary of active findings by severity."""

    spec_name: str
    critical: int
    major: int
    minor: int
    observation: int


def query_findings(
    conn: Any,
    *,
    spec: str | None = None,
    severity: str | None = None,
    archetype: str | None = None,
    run_id: str | None = None,
    active_only: bool = True,
) -> list[FindingRow]:
    """Query findings from DuckDB with optional filters.

    Stub — raises NotImplementedError until task group 4.
    """
    raise NotImplementedError("query_findings not yet implemented")


def query_findings_summary(
    conn: Any,
) -> list[FindingsSummary]:
    """Query per-spec summary of active critical/major findings.

    Stub — raises NotImplementedError until task group 4.
    """
    raise NotImplementedError("query_findings_summary not yet implemented")


def format_findings_table(
    findings: list[FindingRow],
    json_output: bool = False,
) -> str:
    """Format findings as a table or JSON array.

    Stub — raises NotImplementedError until task group 4.
    """
    raise NotImplementedError("format_findings_table not yet implemented")
