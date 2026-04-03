"""Aggregate project model: spec outcomes, module stability, archetype effectiveness.

Provides a read-only view of project health computed from execution outcomes,
review findings, and drift findings.

Requirements: 39-REQ-7.1, 39-REQ-7.2, 39-REQ-7.3, 39-REQ-7.4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class SpecMetrics:
    """Aggregate metrics for a single specification.

    Attributes:
        spec_name: The specification identifier.
        avg_cost: Average total cost across sessions.
        avg_duration_ms: Average execution duration in milliseconds.
        failure_rate: Fraction of sessions that failed (0.0 to 1.0).
        session_count: Total number of sessions observed.
    """

    spec_name: str
    avg_cost: float
    avg_duration_ms: int
    failure_rate: float
    session_count: int


@dataclass
class ProjectModel:
    """Aggregate project-level model derived from execution history.

    Attributes:
        spec_outcomes: Per-spec metrics keyed by spec name.
        module_stability: Finding density per spec (findings / sessions).
        archetype_effectiveness: Success rate per archetype type.
        knowledge_staleness: Days since last session per spec (placeholder).
        active_drift_areas: Specs with recent oracle drift findings.
    """

    spec_outcomes: dict[str, SpecMetrics] = field(default_factory=dict)
    module_stability: dict[str, float] = field(default_factory=dict)
    archetype_effectiveness: dict[str, float] = field(default_factory=dict)
    knowledge_staleness: dict[str, int] = field(default_factory=dict)
    active_drift_areas: list[str] = field(default_factory=list)


def build_project_model(conn: duckdb.DuckDBPyConnection) -> ProjectModel:
    """Aggregate project metrics from execution history.

    Queries execution_outcomes (joined with complexity_assessments) for
    per-spec and per-archetype metrics, and review_findings for module
    stability scores.

    Args:
        conn: DuckDB connection with the required tables.

    Returns:
        A populated ProjectModel instance.

    Requirements: 39-REQ-7.1, 39-REQ-7.2, 39-REQ-7.3
    """
    model = ProjectModel()

    _compute_spec_outcomes(conn, model)
    _compute_module_stability(conn, model)
    _compute_archetype_effectiveness(conn, model)
    _compute_active_drift(conn, model)

    return model


def _compute_spec_outcomes(conn: duckdb.DuckDBPyConnection, model: ProjectModel) -> None:
    """Compute per-spec average cost, duration, failure rate, session count.

    Requirement: 39-REQ-7.1
    """
    try:
        rows = conn.execute(
            """
            SELECT
                ca.spec_name,
                AVG(eo.total_cost) AS avg_cost,
                AVG(eo.duration_ms) AS avg_duration_ms,
                SUM(CASE WHEN eo.outcome != 'completed' THEN 1 ELSE 0 END)
                    * 1.0 / COUNT(*) AS failure_rate,
                COUNT(*) AS session_count
            FROM execution_outcomes eo
            JOIN complexity_assessments ca ON eo.assessment_id = ca.id
            GROUP BY ca.spec_name
            """
        ).fetchall()
    except duckdb.Error:
        logger.warning("Failed to query spec outcomes", exc_info=True)
        return

    for spec_name, avg_cost, avg_duration, failure_rate, count in rows:
        model.spec_outcomes[spec_name] = SpecMetrics(
            spec_name=spec_name,
            avg_cost=float(avg_cost),
            avg_duration_ms=int(avg_duration),
            failure_rate=float(failure_rate),
            session_count=int(count),
        )


def _compute_module_stability(conn: duckdb.DuckDBPyConnection, model: ProjectModel) -> None:
    """Compute module stability as finding density per spec.

    Finding density = total review findings / total sessions (from outcomes).

    Requirement: 39-REQ-7.2
    """
    try:
        # Count review findings per spec
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

    for spec_name, findings in finding_map.items():
        sessions = model.spec_outcomes.get(spec_name)
        if sessions and sessions.session_count > 0:
            model.module_stability[spec_name] = findings / sessions.session_count
        else:
            # No outcome data; use findings as-is (density = findings / 1)
            model.module_stability[spec_name] = float(findings)


def _compute_archetype_effectiveness(conn: duckdb.DuckDBPyConnection, model: ProjectModel) -> None:
    """Compute archetype effectiveness as success rate per archetype.

    Requirement: 39-REQ-7.3
    """
    try:
        rows = conn.execute(
            """
            SELECT
                json_extract_string(ca.feature_vector, '$.archetype') AS archetype,
                SUM(CASE WHEN eo.outcome = 'completed' THEN 1 ELSE 0 END)
                    * 1.0 / COUNT(*) AS success_rate
            FROM execution_outcomes eo
            JOIN complexity_assessments ca ON eo.assessment_id = ca.id
            GROUP BY json_extract_string(ca.feature_vector, '$.archetype')
            """
        ).fetchall()
    except duckdb.Error:
        logger.warning("Failed to query archetype effectiveness", exc_info=True)
        return

    for archetype, success_rate in rows:
        if archetype:
            model.archetype_effectiveness[archetype] = float(success_rate)


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

    # Spec outcomes
    lines.append("spec_outcomes:")
    if model.spec_outcomes:
        for name, metrics in sorted(model.spec_outcomes.items()):
            lines.append(
                f"  {name}: avg_cost={metrics.avg_cost:.2f}, "
                f"avg_duration={metrics.avg_duration_ms}ms, "
                f"failure_rate={metrics.failure_rate:.1%}, "
                f"sessions={metrics.session_count}"
            )
    else:
        lines.append("  (no data)")

    lines.append("")

    # Module stability
    lines.append("module_stability:")
    if model.module_stability:
        for name, density in sorted(model.module_stability.items()):
            lines.append(f"  {name}: {density:.2f} findings/session")
    else:
        lines.append("  (no data)")

    lines.append("")

    # Archetype effectiveness
    lines.append("archetype_effectiveness:")
    if model.archetype_effectiveness:
        for arch, rate in sorted(model.archetype_effectiveness.items()):
            lines.append(f"  {arch}: {rate:.1%} success rate")
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
