"""Generate human-readable markdown summary of all facts.

Reads facts from DuckDB instead of JSONL. Enriches each fact with causal
chains, entity links, supersession history, and relative age metadata.

Requirements: 05-REQ-6.1, 05-REQ-6.2, 05-REQ-6.3, 05-REQ-6.E1,
              05-REQ-6.E2, 39-REQ-2.1,
              111-REQ-1.*, 111-REQ-2.*, 111-REQ-3.*, 111-REQ-4.*,
              111-REQ-5.*, 111-REQ-6.*, 111-REQ-7.*
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.store import read_all_facts

logger = logging.getLogger("agent_fox.knowledge.rendering")

DEFAULT_SUMMARY_PATH = Path("docs/memory.md")

CATEGORY_TITLES: dict[str, str] = {
    "gotcha": "Gotchas",
    "pattern": "Patterns",
    "decision": "Decisions",
    "convention": "Conventions",
    "anti_pattern": "Anti-Patterns",
    "fragile_area": "Fragile Areas",
}

# ---------------------------------------------------------------------------
# Enrichment constants
# ---------------------------------------------------------------------------

_MAX_CAUSES = 2
_MAX_EFFECTS = 2
_MAX_ENTITY_PATHS = 3
_CAUSE_TRUNCATE = 60
_SUPERSEDED_TRUNCATE = 80


# ---------------------------------------------------------------------------
# Enrichments data container
# ---------------------------------------------------------------------------


@dataclass
class Enrichments:
    """Container for batch-loaded enrichment data keyed by fact ID."""

    causes: dict[str, list[str]] = field(default_factory=dict)
    effects: dict[str, list[str]] = field(default_factory=dict)
    entity_paths: dict[str, list[str]] = field(default_factory=dict)
    superseded: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Age formatting
# ---------------------------------------------------------------------------


def _format_relative_age(created_at: str, now: datetime) -> str | None:
    """Compute relative age string from ISO timestamp.

    Returns None if created_at is missing or unparseable.
    Format: "Xd ago" (<60 days), "Xmo ago" (60-364 days), "Xy ago" (365+ days).

    Uses integer division: months = days // 30, years = days // 365.
    Future timestamps are clamped to 0 days.
    """
    if not created_at:
        return None
    try:
        # Try parsing with timezone info first, then without.
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(created_at, fmt)
                break
            except ValueError:
                continue
        else:
            return None

        # Normalise to UTC for comparison.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        delta = now - dt
        days = max(0, delta.days)

        if days < 60:
            return f"{days}d ago"
        elif days < 365:
            return f"{days // 30}mo ago"
        else:
            return f"{days // 365}y ago"

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Enrichment loading
# ---------------------------------------------------------------------------


def load_enrichments(
    conn: duckdb.DuckDBPyConnection | None,
    fact_ids: list[str],
) -> Enrichments:
    """Batch-load all enrichment data for the given fact IDs.

    Executes at most 4 queries:
    1. Causes: fact_causes WHERE effect_id IN (fact_ids) JOIN memory_facts
    2. Effects: fact_causes WHERE cause_id IN (fact_ids) JOIN memory_facts
    3. Entity paths: fact_entities JOIN entity_graph WHERE entity_type='file'
    4. Superseded: memory_facts WHERE superseded_by IN (fact_ids)

    Returns an empty Enrichments if conn is None or any query fails.
    Each query failure is independent -- other queries still execute.

    Requirements: 111-REQ-7.1, 111-REQ-7.2, 111-REQ-7.E1, 111-REQ-7.E2
    """
    if conn is None or not fact_ids:
        return Enrichments()

    placeholders = ", ".join(["?::UUID"] * len(fact_ids))
    enrichments = Enrichments()

    # -- Query 1: Causes (facts that caused the rendered facts) ---------------
    try:
        rows = conn.execute(
            f"""
            SELECT CAST(fc.effect_id AS VARCHAR), mf.content
            FROM fact_causes fc
            JOIN memory_facts mf ON fc.cause_id = mf.id
            WHERE fc.effect_id IN ({placeholders})
            """,
            fact_ids,
        ).fetchall()
        for effect_id, content in rows:
            enrichments.causes.setdefault(effect_id, []).append(content)
    except Exception as exc:
        logger.warning("Enrichment query 1 (causes) failed: %s", exc)

    # -- Query 2: Effects (facts that the rendered facts caused) --------------
    try:
        rows = conn.execute(
            f"""
            SELECT CAST(fc.cause_id AS VARCHAR), mf.content
            FROM fact_causes fc
            JOIN memory_facts mf ON fc.effect_id = mf.id
            WHERE fc.cause_id IN ({placeholders})
            """,
            fact_ids,
        ).fetchall()
        for cause_id, content in rows:
            enrichments.effects.setdefault(cause_id, []).append(content)
    except Exception as exc:
        logger.warning("Enrichment query 2 (effects) failed: %s", exc)

    # -- Query 3: Entity paths -----------------------------------------------
    # Note: entity_type is stored as lowercase 'file' (EntityType.FILE = "file")
    try:
        rows = conn.execute(
            f"""
            SELECT CAST(fe.fact_id AS VARCHAR), eg.entity_path
            FROM fact_entities fe
            JOIN entity_graph eg ON fe.entity_id = eg.id
            WHERE fe.fact_id IN ({placeholders})
              AND eg.entity_type = 'file'
              AND eg.deleted_at IS NULL
            """,
            fact_ids,
        ).fetchall()
        for fact_id, entity_path in rows:
            enrichments.entity_paths.setdefault(fact_id, []).append(entity_path)
    except Exception as exc:
        logger.warning("Enrichment query 3 (entity_paths) failed: %s", exc)

    # -- Query 4: Superseded content -----------------------------------------
    try:
        rows = conn.execute(
            f"""
            SELECT CAST(superseded_by AS VARCHAR), content
            FROM memory_facts
            WHERE superseded_by IS NOT NULL
              AND CAST(superseded_by AS VARCHAR) IN ({placeholders})
            """,
            fact_ids,
        ).fetchall()
        for superseding_id, content in rows:
            # Last-write-wins for multiple superseded rows (documented invariant)
            enrichments.superseded[superseding_id] = content
    except Exception as exc:
        logger.warning("Enrichment query 4 (superseded) failed: %s", exc)

    return enrichments


# ---------------------------------------------------------------------------
# Fact renderer
# ---------------------------------------------------------------------------


def _truncate(text: str, limit: int) -> str:
    """Truncate text to at most limit characters, appending ellipsis if cut."""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _render_fact(
    fact: Fact,
    enrichments: Enrichments,
    now: datetime,
) -> str:
    """Render a single fact as markdown with optional enrichment sub-bullets.

    Output format:
        - {content} _(spec: {spec_name}, confidence: {confidence}, {age})_
          - cause: {truncated content}
          - effect: {truncated content}
          - files: {path1}, {path2}, {path3} +N more
          - replaces: {truncated old content}

    Requirements: 111-REQ-2.3, 111-REQ-4.1, 111-REQ-4.2, 111-REQ-5.1,
                  111-REQ-5.2, 111-REQ-6.1
    """
    conf = f"{fact.confidence:.2f}"
    age = _format_relative_age(fact.created_at, now)

    if age:
        meta = f"_(spec: {fact.spec_name}, confidence: {conf}, {age})_"
    else:
        meta = f"_(spec: {fact.spec_name}, confidence: {conf})_"

    lines = [f"- {fact.content} {meta}"]

    # -- Cause sub-bullets ---------------------------------------------------
    causes = enrichments.causes.get(fact.id, [])
    for cause_content in causes[:_MAX_CAUSES]:
        lines.append(f"  - cause: {_truncate(cause_content, _CAUSE_TRUNCATE)}")

    # -- Effect sub-bullets --------------------------------------------------
    effects = enrichments.effects.get(fact.id, [])
    for effect_content in effects[:_MAX_EFFECTS]:
        lines.append(f"  - effect: {_truncate(effect_content, _CAUSE_TRUNCATE)}")

    # -- Entity path sub-bullet ----------------------------------------------
    paths = enrichments.entity_paths.get(fact.id, [])
    if paths:
        shown = paths[:_MAX_ENTITY_PATHS]
        overflow = len(paths) - _MAX_ENTITY_PATHS
        path_str = ", ".join(shown)
        if overflow > 0:
            path_str += f" +{overflow} more"
        lines.append(f"  - files: {path_str}")

    # -- Supersession sub-bullet ---------------------------------------------
    old_content = enrichments.superseded.get(fact.id)
    if old_content is not None:
        lines.append(f"  - replaces: {_truncate(old_content, _SUPERSEDED_TRUNCATE)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Summary renderer
# ---------------------------------------------------------------------------


def _sort_key(fact: Fact) -> tuple[float, str]:
    """Sort key: confidence descending, then created_at descending (newest first)."""
    # Negate confidence for descending sort.
    # For created_at, we negate by using the string in reversed byte order trick:
    # ISO timestamps sort lexicographically, so we can reverse them with "-".
    # Use a leading "-" trick: since we're negating a string we use a complement.
    # Simplest: return (-confidence, inverted_timestamp).
    # For strings: lexicographic desc means we can invert by providing a tuple
    # where we negate the derived datetime.
    try:
        dt = datetime.fromisoformat(fact.created_at) if fact.created_at else None
    except ValueError:
        dt = None

    # For descending sort: negate confidence, negate timestamp as epoch seconds.
    neg_conf = -fact.confidence
    if dt is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        neg_ts = -dt.timestamp()
    else:
        neg_ts = 0.0  # Facts without timestamps sort after those with timestamps

    return (neg_conf, neg_ts)


def render_summary(
    conn: duckdb.DuckDBPyConnection | None = None,
    output_path: Path = DEFAULT_SUMMARY_PATH,
) -> None:
    """Generate an enriched human-readable markdown summary of all facts.

    Creates `docs/memory.md` with facts organized by category. Each fact
    entry includes content, spec name, confidence, relative age, and
    optional enrichment sub-bullets (causal links, entity paths,
    supersession history).

    Uses :func:`read_all_facts` so that facts are always available even
    when *conn* is ``None`` — falls back to a read-only DuckDB open,
    then to the JSONL file.

    Creates the output directory if it does not exist.

    Args:
        conn: DuckDB connection. Falls back automatically when ``None``.
        output_path: Path to the output markdown file.

    Requirements: 111-REQ-1.1, 111-REQ-1.2, 111-REQ-1.E1, 111-REQ-3.1,
                  111-REQ-3.E1, 111-REQ-7.1, 111-REQ-7.2, 111-REQ-7.E2
    """
    facts: list[Fact] = read_all_facts(conn)

    # Create the output directory if it doesn't exist.
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not facts:
        output_path.write_text(_render_empty_summary(), encoding="utf-8")
        logger.info("Rendered empty memory summary to %s", output_path)
        return

    # Sort all facts globally by confidence desc, then created_at desc.
    sorted_facts = sorted(facts, key=_sort_key)

    # Build summary header line.
    n = len(sorted_facts)
    # Find the most recent created_at among all facts.
    last_updated: str | None = None
    for fact in sorted_facts:
        if fact.created_at:
            try:
                dt = datetime.fromisoformat(fact.created_at)
                date_str = dt.strftime("%Y-%m-%d")
                # Since sorted_facts is sorted by created_at desc within each
                # confidence group, we find the absolute maximum separately.
                if last_updated is None or date_str > last_updated:
                    last_updated = date_str
            except ValueError:
                pass

    if last_updated:
        summary_line = f"_{n} facts | last updated: {last_updated}_"
    else:
        summary_line = f"_{n} facts_"

    # Load enrichment data in batch.
    fact_ids = [f.id for f in sorted_facts]
    enrichments = load_enrichments(conn, fact_ids)

    # Group facts by category (preserving sorted order).
    by_category: dict[str, list[Fact]] = {}
    for fact in sorted_facts:
        by_category.setdefault(fact.category, []).append(fact)

    # Get current time for age computation.
    now = datetime.now(UTC)

    # Build the markdown content.
    lines: list[str] = ["# Agent-Fox Memory", "", summary_line, ""]

    for category_value, title in CATEGORY_TITLES.items():
        category_facts = by_category.get(category_value)
        if not category_facts:
            continue
        lines.append(f"## {title}")
        lines.append("")
        for fact in category_facts:
            lines.append(_render_fact(fact, enrichments, now))
        lines.append("")

    content = "\n".join(lines)
    output_path.write_text(content, encoding="utf-8")
    logger.info("Rendered memory summary to %s", output_path)


def _render_empty_summary() -> str:
    """Render the summary content when no facts exist."""
    return "# Agent-Fox Memory\n\n_No facts have been recorded yet._\n"
