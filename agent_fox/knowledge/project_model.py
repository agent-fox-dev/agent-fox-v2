"""Aggregate project model: module stability, active drift areas.

Provides a read-only view of project health computed from review findings
and drift findings.

Requirements: 39-REQ-7.2, 39-REQ-7.4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class ProjectModel:
    """Aggregate project-level model derived from execution history.

    Attributes:
        module_stability: Finding density per spec (findings / sessions).
        knowledge_staleness: Days since last session per spec (placeholder).
        active_drift_areas: Specs with recent oracle drift findings.
    """

    module_stability: dict[str, float] = field(default_factory=dict)
    knowledge_staleness: dict[str, int] = field(default_factory=dict)
    active_drift_areas: list[str] = field(default_factory=list)


def build_project_model(conn: duckdb.DuckDBPyConnection) -> ProjectModel:
    """Aggregate project metrics from execution history.

    Queries review_findings for module stability scores and drift_findings
    for active drift areas.

    Args:
        conn: DuckDB connection with the required tables.

    Returns:
        A populated ProjectModel instance.

    Requirements: 39-REQ-7.2
    """
    model = ProjectModel()

    _compute_module_stability(conn, model)
    _compute_active_drift(conn, model)

    return model


def _compute_module_stability(conn: duckdb.DuckDBPyConnection, model: ProjectModel) -> None:
    """Compute module stability as finding density per spec.

    Finding density = total review findings / total sessions from session_outcomes.

    Requirement: 39-REQ-7.2
    """
    try:
        finding_counts = conn.execute(
            """
            SELECT spec_name, COUNT(*) AS cnt
            FROM review_findings
            GROUP BY spec_name
            """
        ).fetchall()
    except duckdb.Error:
        return

    finding_map: dict[str, int] = {row[0]: int(row[1]) for row in finding_counts}

    try:
        session_counts = conn.execute(
            """
            SELECT spec_name, COUNT(*) AS cnt
            FROM session_outcomes
            GROUP BY spec_name
            """
        ).fetchall()
    except duckdb.Error:
        session_counts = []

    session_map: dict[str, int] = {row[0]: int(row[1]) for row in session_counts}

    for spec_name, findings in finding_map.items():
        sessions = session_map.get(spec_name, 0)
        if sessions > 0:
            model.module_stability[spec_name] = findings / sessions
        else:
            model.module_stability[spec_name] = float(findings)


def _compute_active_drift(conn: duckdb.DuckDBPyConnection, model: ProjectModel) -> None:
    """Find specs with recent unsuperseded drift findings."""
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT spec_name
            FROM drift_findings
            WHERE superseded_by IS NULL
            """
        ).fetchall()
    except duckdb.Error:
        return

    model.active_drift_areas = [row[0] for row in rows]


def format_project_model(model: ProjectModel) -> str:
    """Format the project model for human-readable status output.

    Args:
        model: A ProjectModel instance.

    Returns:
        A formatted string suitable for display.

    Requirement: 39-REQ-7.4
    """
    lines: list[str] = []
    lines.append("== Project Model ==")
    lines.append("")

    # Module stability
    lines.append("module_stability:")
    if model.module_stability:
        for name, density in sorted(model.module_stability.items()):
            lines.append(f"  {name}: {density:.2f} findings/session")
    else:
        lines.append("  (no data)")

    lines.append("")

    # Active drift areas
    if model.active_drift_areas:
        lines.append("active_drift_areas:")
        for spec in sorted(model.active_drift_areas):
            lines.append(f"  - {spec}")
    else:
        lines.append("active_drift_areas: none")

    return "\n".join(lines)
