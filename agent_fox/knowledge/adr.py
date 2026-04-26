"""ADR ingestion: parsing, validation, storage, retrieval, and formatting.

Detects ADR files in session ``touched_files``, parses MADR 4.0.0 format,
validates structural compliance, stores in DuckDB, and retrieves relevant
ADRs for prompt injection.  Follows the errata module pattern:
self-contained dataclasses, pure functions, and DB operations with
graceful degradation.

Requirements: 117-REQ-1.*, 117-REQ-2.*, 117-REQ-3.*, 117-REQ-4.*,
              117-REQ-5.*, 117-REQ-6.*, 117-REQ-7.*
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADR_PATH_PATTERN = re.compile(r"^docs/adr/[^/]+\.md$")

_STOP_WORDS: frozenset[str] = frozenset(
    {
        # Common English stop words — short words (< 3 chars) are filtered
        # separately, so only words ≥ 3 chars appear here.
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "had",
        "her",
        "was",
        "one",
        "our",
        "out",
        "use",
        "has",
        "its",
        "how",
        "who",
        "did",
        "get",
        "may",
        "him",
        "old",
        "see",
        "now",
        "way",
        "few",
        "new",
        "own",
        "say",
        "she",
        "too",
        "any",
        "per",
        "via",
        "set",
        "also",
        "been",
        "from",
        "have",
        "into",
        "just",
        "like",
        "more",
        "most",
        "much",
        "must",
        "only",
        "over",
        "some",
        "such",
        "than",
        "that",
        "them",
        "then",
        "this",
        "very",
        "what",
        "when",
        "will",
        "with",
        "each",
        "make",
        "many",
        "were",
        "been",
        "does",
        "done",
        "about",
        "after",
        "being",
        "could",
        "every",
        "other",
        "their",
        "there",
        "these",
        "those",
        "which",
        "while",
        "would",
        "should",
    }
)

# Heading synonyms for mandatory MADR sections
_CONTEXT_HEADINGS = frozenset({"context and problem statement", "context"})
_OPTIONS_HEADINGS = frozenset(
    {"considered options", "options considered", "considered alternatives"}
)
_DECISION_HEADINGS = frozenset({"decision outcome", "decision"})


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ADREntry:
    """Structured representation of a parsed MADR document."""

    id: str
    file_path: str
    title: str
    status: str
    chosen_option: str
    justification: str
    considered_options: list[str]
    summary: str
    content_hash: str
    keywords: list[str]
    spec_refs: list[str]
    has_context_section: bool = False
    has_options_section: bool = False
    has_decision_section: bool = False
    created_at: datetime | None = None
    superseded_at: datetime | None = None


@dataclass(frozen=True)
class ADRValidationResult:
    """Result of MADR structural validation."""

    passed: bool
    diagnostics: list[str]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect_adr_changes(touched_files: list[str] | None) -> list[str]:
    """Filter touched_files for ``docs/adr/*.md`` paths.

    Returns paths matching one directory level under ``docs/adr/`` with
    ``.md`` extension only.  Preserves input order.

    Requirements: 117-REQ-1.1, 117-REQ-1.2, 117-REQ-1.E1, 117-REQ-1.E2
    """
    if not touched_files:
        return []
    return [p for p in touched_files if _ADR_PATH_PATTERN.match(p)]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_madr(content: str) -> ADREntry | None:
    """Parse MADR markdown content into an ADREntry.

    Extracts the title (first H1 heading), status, considered options,
    chosen option, justification, and tracks which mandatory sections
    are present.  Returns ``None`` on parse failure (no H1 heading).

    Requirements: 117-REQ-2.1 through 117-REQ-2.6, 117-REQ-2.E1
    """
    # 1. Strip YAML frontmatter if present
    frontmatter: dict[str, str] = {}
    body = content
    stripped = content.lstrip()
    if stripped.startswith("---"):
        end_idx = stripped.find("---", 3)
        if end_idx != -1:
            fm_text = stripped[3:end_idx].strip()
            for line in fm_text.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip().lower()] = value.strip()
            body = stripped[end_idx + 3 :].strip()

    # 2. Extract H1 title — return None if absent (117-REQ-2.E1)
    h1_match = re.search(r"^# (.+)$", body, re.MULTILINE)
    if not h1_match:
        return None
    title = h1_match.group(1).strip()

    # 3. Parse H2 sections into {heading: body} dict
    sections: dict[str, str] = {}
    section_re = re.compile(r"^## (.+)$", re.MULTILINE)
    section_matches = list(section_re.finditer(body))
    for i, match in enumerate(section_matches):
        heading = match.group(1).strip()
        start = match.end()
        end_pos = (
            section_matches[i + 1].start()
            if i + 1 < len(section_matches)
            else len(body)
        )
        sections[heading] = body[start:end_pos].strip()

    # 4. Determine status: frontmatter > ## Status section > default
    status = frontmatter.get("status", "").strip().lower()
    if not status:
        for heading, section_body in sections.items():
            if heading.lower() == "status":
                lines = [ln.strip() for ln in section_body.split("\n") if ln.strip()]
                if lines:
                    status = lines[0].lower()
                break
    if not status:
        status = "proposed"

    # 5. Detect mandatory section presence
    has_context = any(h.lower() in _CONTEXT_HEADINGS for h in sections)
    has_options = any(h.lower() in _OPTIONS_HEADINGS for h in sections)
    has_decision = any(h.lower() in _DECISION_HEADINGS for h in sections)

    # 6. Extract considered options from bullet list
    considered_options: list[str] = []
    for heading in sections:
        if heading.lower() in _OPTIONS_HEADINGS:
            for line in sections[heading].split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    considered_options.append(line[2:].strip())
            break

    # 7. Extract chosen option and justification from Decision Outcome
    chosen_option = ""
    justification = ""
    for heading in sections:
        if heading.lower() in _DECISION_HEADINGS:
            section_body = sections[heading]
            chosen_match = re.search(
                r'Chosen option:\s*"([^"]+)"(?:\s*,\s*because\s+(.+))?',
                section_body,
                re.DOTALL,
            )
            if chosen_match:
                chosen_option = chosen_match.group(1).strip()
                if chosen_match.group(2):
                    justification = chosen_match.group(2).strip()
            break

    # 8. Extract metadata
    spec_refs = extract_spec_refs(content)
    keywords = extract_keywords(title)

    # 9. Generate summary
    summary = _build_summary(title, chosen_option, considered_options, justification)

    return ADREntry(
        id=str(uuid.uuid4()),
        file_path="",
        title=title,
        status=status,
        chosen_option=chosen_option,
        justification=justification,
        considered_options=considered_options,
        summary=summary,
        content_hash="",
        keywords=keywords,
        spec_refs=spec_refs,
        has_context_section=has_context,
        has_options_section=has_options,
        has_decision_section=has_decision,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_madr(entry: ADREntry) -> ADRValidationResult:
    """Validate MADR structural compliance.

    Checks for non-empty title, presence of all three mandatory sections
    (context, considered options, decision outcome), at least 3 considered
    options, and a non-empty chosen option.

    Requirements: 117-REQ-3.1 through 117-REQ-3.4, 117-REQ-3.E1
    """
    diagnostics: list[str] = []

    if not entry.title:
        diagnostics.append("Title is empty or missing.")

    if not entry.has_context_section:
        diagnostics.append(
            "Missing mandatory section: Context and Problem Statement."
        )

    if not entry.has_options_section:
        diagnostics.append("Missing mandatory section: Considered Options.")

    if not entry.has_decision_section:
        diagnostics.append("Missing mandatory section: Decision Outcome.")

    if len(entry.considered_options) < 3:
        diagnostics.append(
            f"Considered options count ({len(entry.considered_options)}) "
            f"is below the minimum required (3)."
        )

    if not entry.chosen_option:
        diagnostics.append("Chosen option is empty or missing.")

    passed = len(diagnostics) == 0
    return ADRValidationResult(passed=passed, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def extract_spec_refs(content: str) -> list[str]:
    r"""Extract spec references from ADR content.

    Patterns (returning the *numeric* spec identifier only):
      - ``(\d+)-REQ-`` — requirement references (e.g. "42-REQ-1.1" → "42")
      - ``spec[_\s]+(\d+)`` — prose references (e.g. "spec 15" → "15")
      - ``(\d{1,3})_[a-z][a-z_]+`` — spec folder names (e.g. "03_base_app" → "03")

    Requirement: 117-REQ-6.4
    """
    refs: set[str] = set()

    # Pattern 1: requirement references
    for m in re.finditer(r"(\d+)-REQ-", content):
        refs.add(m.group(1))

    # Pattern 2: prose references (case-insensitive)
    for m in re.finditer(r"spec[_\s]+(\d+)", content, re.IGNORECASE):
        refs.add(m.group(1))

    # Pattern 3: spec folder names — extract numeric prefix only
    for m in re.finditer(r"(\d{1,3})_[a-z][a-z_]+", content):
        refs.add(m.group(1))

    return sorted(refs)


def extract_keywords(title: str) -> list[str]:
    """Extract searchable keywords from ADR title.

    Splits on whitespace and hyphens, lowercases, filters words shorter
    than 3 characters and common stop words.

    Requirement: 117-REQ-6.5
    """
    words = re.split(r"[\s\-]+", title)
    keywords: list[str] = []
    seen: set[str] = set()
    for word in words:
        w = word.lower().strip()
        if not w or len(w) < 3 or w in _STOP_WORDS:
            continue
        if w not in seen:
            keywords.append(w)
            seen.add(w)
    return keywords


# ---------------------------------------------------------------------------
# Summary and formatting
# ---------------------------------------------------------------------------


def generate_adr_summary(entry: ADREntry) -> str:
    """Produce a concise one-line summary of an ADR.

    Format: ``{title}: Chose "{chosen}" over {others}. {justification}``

    Requirement: 117-REQ-6.2
    """
    return _build_summary(
        entry.title,
        entry.chosen_option,
        entry.considered_options,
        entry.justification,
    )


def _build_summary(
    title: str,
    chosen_option: str,
    considered_options: list[str],
    justification: str,
) -> str:
    """Build summary string from components."""
    others = [o for o in considered_options if o != chosen_option]
    other_str = ", ".join(f'"{o}"' for o in others)
    return f'{title}: Chose "{chosen_option}" over {other_str}. {justification}'


def format_adrs_for_prompt(adrs: list[ADREntry]) -> list[str]:
    """Format ADR entries as ``[ADR]``-prefixed prompt strings.

    Returns one string per entry, suitable for inclusion in coder session
    context alongside ``[REVIEW]`` and ``[ERRATA]`` items.

    Requirement: 117-REQ-6.2
    """
    return [f"[ADR] {adr.summary}" for adr in adrs]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def store_adr(
    conn: duckdb.DuckDBPyConnection,
    entry: ADREntry,
) -> int:
    """Insert ADR entry into DuckDB, handling supersession.

    Returns number of rows inserted (0 or 1).  Handles missing table,
    closed connection, and duplicate content_hash gracefully.

    Requirements: 117-REQ-4.1, 117-REQ-4.4, 117-REQ-4.E1, 117-REQ-4.E2,
                  117-REQ-5.1, 117-REQ-5.2, 117-REQ-5.3, 117-REQ-5.E1
    """
    try:
        # Check for existing active entry with same file_path
        existing = conn.execute(
            "SELECT content_hash FROM adr_entries "
            "WHERE file_path = ? AND superseded_at IS NULL",
            [entry.file_path],
        ).fetchone()

        if existing:
            if existing[0] == entry.content_hash:
                # Same content hash — skip (idempotent, 117-REQ-5.2)
                return 0
            # Different content — supersede old entry (117-REQ-5.1)
            conn.execute(
                "UPDATE adr_entries SET superseded_at = CURRENT_TIMESTAMP "
                "WHERE file_path = ? AND superseded_at IS NULL",
                [entry.file_path],
            )

        # Insert new entry
        conn.execute(
            "INSERT INTO adr_entries "
            "(id, file_path, title, status, chosen_option, considered_options, "
            "justification, summary, content_hash, keywords, spec_refs, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                entry.id,
                entry.file_path,
                entry.title,
                entry.status,
                entry.chosen_option,
                entry.considered_options,
                entry.justification,
                entry.summary,
                entry.content_hash,
                entry.keywords,
                entry.spec_refs,
                entry.created_at or datetime.now(UTC),
            ],
        )
        return 1
    except duckdb.CatalogException:
        logger.debug("adr_entries table does not exist, skipping store")
        return 0
    except Exception:
        logger.warning("Failed to store ADR entry", exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def query_adrs(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    task_description: str,
    *,
    limit: int = 10,
) -> list[ADREntry]:
    """Query active ADRs matching by spec_refs or keyword overlap.

    Active entries (``superseded_at IS NULL``) are matched against the
    spec number extracted from ``spec_name`` and keywords extracted from
    ``task_description``.

    Requirements: 117-REQ-6.1, 117-REQ-6.E1, 117-REQ-6.E2
    """
    try:
        # Extract spec number from spec_name (e.g. "42_rate_limiting" → "42")
        spec_num_match = re.match(r"(\d+)", spec_name)
        spec_num = spec_num_match.group(1) if spec_num_match else ""

        # Extract keywords from task_description
        task_words: set[str] = set()
        for word in re.split(r"[\s\-]+", task_description):
            w = word.lower().strip()
            if w and len(w) >= 3 and w not in _STOP_WORDS:
                task_words.add(w)

        # Query all active entries
        rows = conn.execute(
            "SELECT id, file_path, title, status, chosen_option, "
            "considered_options, justification, summary, content_hash, "
            "keywords, spec_refs, created_at, superseded_at "
            "FROM adr_entries WHERE superseded_at IS NULL "
            "ORDER BY created_at DESC",
        ).fetchall()

        results: list[ADREntry] = []
        for row in rows:
            entry_spec_refs: list[str] = row[10] if row[10] else []
            entry_keywords: list[str] = row[9] if row[9] else []

            matched = False
            # Match by spec_refs
            if spec_num and spec_num in entry_spec_refs:
                matched = True
            # Match by keyword overlap
            elif task_words and set(entry_keywords) & task_words:
                matched = True

            if matched:
                results.append(
                    ADREntry(
                        id=row[0],
                        file_path=row[1],
                        title=row[2],
                        status=row[3],
                        chosen_option=row[4] or "",
                        justification=row[6] or "",
                        considered_options=row[5] if row[5] else [],
                        summary=row[7],
                        content_hash=row[8],
                        keywords=entry_keywords,
                        spec_refs=entry_spec_refs,
                        created_at=row[11],
                        superseded_at=row[12],
                    )
                )
                if len(results) >= limit:
                    break

        return results
    except duckdb.CatalogException:
        logger.debug("adr_entries table does not exist")
        return []
    except Exception:
        logger.debug("Could not query ADRs")
        return []


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------


def ingest_adr(
    conn: duckdb.DuckDBPyConnection,
    file_path: str,
    project_root: Path,
    *,
    sink: Any | None = None,
    run_id: str = "",
) -> ADREntry | None:
    """Full ingest pipeline: read → parse → validate → store.

    Returns the ingested ADREntry or None on failure (file missing,
    parse error, or validation failure).

    Requirements: 117-REQ-7.1 through 117-REQ-7.4, 117-REQ-7.E1
    """
    # Read file (117-REQ-1.3: skip deleted files)
    full_path = project_root / file_path
    if not full_path.exists():
        logger.debug("ADR file does not exist: %s", full_path)
        return None

    try:
        content = full_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("Failed to read ADR file: %s", full_path)
        return None

    # Compute content hash (117-REQ-4.2)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # Parse
    entry = parse_madr(content)
    if entry is None:
        logger.warning("Failed to parse MADR content from %s", file_path)
        return None

    # Validate
    validation = validate_madr(entry)
    if not validation.passed:
        logger.warning(
            "ADR validation failed for %s: %s",
            file_path,
            "; ".join(validation.diagnostics),
        )
        # Emit audit event for validation failure (117-REQ-7.2)
        _emit_audit_event(
            sink,
            run_id,
            "ADR_VALIDATION_FAILED",
            "WARNING",
            {
                "file_path": file_path,
                "diagnostics": validation.diagnostics,
            },
        )
        return None

    # Build final entry with file_path and content_hash
    final_entry = ADREntry(
        id=entry.id,
        file_path=file_path,
        title=entry.title,
        status=entry.status,
        chosen_option=entry.chosen_option,
        justification=entry.justification,
        considered_options=entry.considered_options,
        summary=entry.summary,
        content_hash=content_hash,
        keywords=entry.keywords,
        spec_refs=entry.spec_refs,
        has_context_section=entry.has_context_section,
        has_options_section=entry.has_options_section,
        has_decision_section=entry.has_decision_section,
    )

    # Store
    rows_inserted = store_adr(conn, final_entry)

    # Emit audit event for successful ingestion (117-REQ-7.4)
    if rows_inserted > 0:
        _emit_audit_event(
            sink,
            run_id,
            "ADR_INGESTED",
            "INFO",
            {
                "file_path": file_path,
                "title": final_entry.title,
                "considered_options_count": len(final_entry.considered_options),
            },
        )

    return final_entry


def _emit_audit_event(
    sink: Any | None,
    run_id: str,
    event_type_name: str,
    severity_name: str,
    payload: dict[str, Any],
) -> None:
    """Emit an audit event via the sink, swallowing all errors.

    Requirement: 117-REQ-7.E1 — audit emission failure must not
    disrupt the pipeline.
    """
    if sink is None:
        return
    try:
        from agent_fox.knowledge.audit import (
            AuditEvent,
            AuditEventType,
            AuditSeverity,
        )

        event_type = AuditEventType(getattr(AuditEventType, event_type_name))
        severity = AuditSeverity(severity_name.lower())
        sink.emit_audit_event(
            AuditEvent(
                run_id=run_id,
                event_type=event_type,
                severity=severity,
                payload=payload,
            )
        )
    except Exception:
        logger.debug("Failed to emit audit event %s", event_type_name)
