"""Tests for agent_fox.knowledge.adr — ADR ingestion, parsing, validation, storage, retrieval.

Test Spec: TS-117-1 through TS-117-22, TS-117-E1 through TS-117-E8,
           TS-117-SMOKE-1, TS-117-SMOKE-2
Requirements: 117-REQ-1.*, 117-REQ-2.*, 117-REQ-3.*, 117-REQ-4.*,
              117-REQ-5.*, 117-REQ-6.*, 117-REQ-7.*
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest
from agent_fox.knowledge.adr import (
    ADREntry,
    detect_adr_changes,
    extract_keywords,
    extract_spec_refs,
    format_adrs_for_prompt,
    ingest_adr,
    parse_madr,
    query_adrs,
    store_adr,
    validate_madr,
)

# ---------------------------------------------------------------------------
# MADR Fixture Constants
# ---------------------------------------------------------------------------

VALID_MADR_CONTENT = """\
---
status: accepted
---
# Use Widget Framework

## Context and Problem Statement

We need to choose a widget framework for building reusable UI components
in our project. The current approach of ad-hoc HTML templates is not
maintainable.

## Considered Options

- Widget Framework A
- Widget Framework B
- Widget Framework C

## Decision Outcome

Chosen option: "Widget Framework A", because it provides the best
performance and has the largest ecosystem of plugins.
"""

VALID_MADR_NO_FRONTMATTER_WITH_STATUS = """\
# Use Widget Framework

## Status

Accepted

## Context and Problem Statement

We need to choose a widget framework for our project.

## Considered Options

- Widget Framework A
- Widget Framework B
- Widget Framework C

## Decision Outcome

Chosen option: "Widget Framework A", because it is simpler.
"""

VALID_MADR_NO_STATUS = """\
# Use Widget Framework

## Context and Problem Statement

We need to choose a widget framework for our project.

## Considered Options

- Widget Framework A
- Widget Framework B
- Widget Framework C

## Decision Outcome

Chosen option: "Widget Framework A", because it is simpler and well-tested.
"""

VALID_MADR_SYNONYM_HEADING = """\
# Use Widget Framework

## Context

We need to choose a widget framework for our project.

## Options Considered

- Widget Framework A
- Widget Framework B
- Widget Framework C

## Decision

Chosen option: "Widget Framework A", because it is simpler.
"""

INVALID_MADR_FEW_OPTIONS = """\
# Use Widget Framework

## Context and Problem Statement

We need to choose a widget framework for our project.

## Considered Options

- Widget Framework A
- Widget Framework B

## Decision Outcome

Chosen option: "Widget Framework A", because it is simpler.
"""

INVALID_MADR_NO_H1 = """\
## Some H2 heading

Body text with no H1 heading present.
"""

MADR_WITH_SPEC_REFS = """\
# Use Rate Limiter

## Context and Problem Statement

As specified in 42-REQ-1.1, we need rate limiting. See also spec 15 for
background on API design patterns. The implementation follows the pattern
from 03_base_app.

## Considered Options

- Token bucket
- Sliding window
- Fixed window

## Decision Outcome

Chosen option: "Token bucket", because it provides smooth rate limiting.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_adr_entries_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the adr_entries table for tests (matches design.md schema)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS adr_entries (
            id              VARCHAR PRIMARY KEY,
            file_path       VARCHAR NOT NULL,
            title           VARCHAR NOT NULL,
            status          VARCHAR NOT NULL DEFAULT 'proposed',
            chosen_option   VARCHAR,
            considered_options TEXT[],
            justification   TEXT,
            summary         TEXT NOT NULL,
            content_hash    VARCHAR NOT NULL,
            keywords        TEXT[] DEFAULT [],
            spec_refs       TEXT[] DEFAULT [],
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            superseded_at   TIMESTAMP
        )
    """)


def _make_adr_entry(
    *,
    id: str = "",
    file_path: str = "docs/adr/01-test.md",
    title: str = "Test ADR",
    status: str = "accepted",
    chosen_option: str = "Option A",
    justification: str = "it is the best choice",
    considered_options: list[str] | None = None,
    summary: str = "",
    content_hash: str = "abc123",
    keywords: list[str] | None = None,
    spec_refs: list[str] | None = None,
    has_context_section: bool = True,
    has_options_section: bool = True,
    has_decision_section: bool = True,
    created_at: datetime | None = None,
    superseded_at: datetime | None = None,
) -> ADREntry:
    """Build an ADREntry with sensible defaults for testing."""
    if not id:
        id = str(uuid.uuid4())
    if considered_options is None:
        considered_options = ["Option A", "Option B", "Option C"]
    if keywords is None:
        keywords = ["test", "adr"]
    if spec_refs is None:
        spec_refs = []
    if not summary:
        others = [o for o in considered_options if o != chosen_option]
        other_str = ", ".join(f'"{o}"' for o in others)
        summary = (
            f'{title}: Chose "{chosen_option}" over {other_str}. {justification}'
        )
    return ADREntry(
        id=id,
        file_path=file_path,
        title=title,
        status=status,
        chosen_option=chosen_option,
        justification=justification,
        considered_options=considered_options,
        summary=summary,
        content_hash=content_hash,
        keywords=keywords,
        spec_refs=spec_refs,
        has_context_section=has_context_section,
        has_options_section=has_options_section,
        has_decision_section=has_decision_section,
        created_at=created_at,
        superseded_at=superseded_at,
    )


class MockSinkDispatcher:
    """Minimal sink that captures audit events for testing."""

    def __init__(self) -> None:
        self.captured_events: list[Any] = []

    def emit_audit_event(self, event: Any) -> None:
        self.captured_events.append(event)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def adr_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with the adr_entries table."""
    conn = duckdb.connect(":memory:")
    _create_adr_entries_table(conn)
    yield conn  # type: ignore[misc]
    conn.close()


@pytest.fixture()
def migrated_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with full migrations applied (including v22)."""
    from agent_fox.knowledge.migrations import run_migrations

    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn  # type: ignore[misc]
    conn.close()


# ===========================================================================
# TS-117-1: Detect ADR paths in touched_files
# ===========================================================================


class TestDetectADRPaths:
    """TS-117-1: Verify detect_adr_changes filters for docs/adr/*.md.

    Requirement: 117-REQ-1.1
    """

    def test_filters_adr_paths(self) -> None:
        """Only docs/adr/*.md paths are returned."""
        touched_files = [
            "docs/adr/01-use-claude.md",
            "agent_fox/cli/code.py",
            "docs/adr/02-remove-fox.md",
            "README.md",
        ]
        result = detect_adr_changes(touched_files)
        assert result == [
            "docs/adr/01-use-claude.md",
            "docs/adr/02-remove-fox.md",
        ]


# ===========================================================================
# TS-117-2: No ADR paths returns empty list
# ===========================================================================


class TestDetectNoADRPaths:
    """TS-117-2: Verify empty list when no ADR paths match.

    Requirement: 117-REQ-1.2
    """

    def test_no_adr_paths(self) -> None:
        touched_files = ["agent_fox/cli/code.py", "tests/test_foo.py"]
        result = detect_adr_changes(touched_files)
        assert result == []


# ===========================================================================
# TS-117-E1: Empty touched_files
# ===========================================================================


class TestDetectEmptyInput:
    """TS-117-E1: Verify detect_adr_changes handles empty input.

    Requirement: 117-REQ-1.E1
    """

    def test_empty_list(self) -> None:
        assert detect_adr_changes([]) == []


# ===========================================================================
# TS-117-E2: Non-.md ADR path excluded
# ===========================================================================


class TestDetectNonMdExcluded:
    """TS-117-E2: Verify non-.md files under docs/adr/ are excluded.

    Requirement: 117-REQ-1.E2
    """

    def test_non_md_extensions_excluded(self) -> None:
        touched_files = [
            "docs/adr/01-test.markdown",
            "docs/adr/notes.txt",
        ]
        result = detect_adr_changes(touched_files)
        assert result == []


# ===========================================================================
# TS-117-3: Parse valid MADR content
# ===========================================================================


class TestParseValidMADR:
    """TS-117-3: Verify parse_madr extracts all fields from valid MADR.

    Requirement: 117-REQ-2.1
    """

    def test_parse_valid_content(self) -> None:
        entry = parse_madr(VALID_MADR_CONTENT)
        assert entry is not None
        assert entry.title == "Use Widget Framework"
        assert len(entry.considered_options) == 3
        assert entry.chosen_option != ""
        assert entry.justification != ""


# ===========================================================================
# TS-117-4: Parse YAML frontmatter status
# ===========================================================================


class TestParseYAMLFrontmatter:
    """TS-117-4: Verify status is extracted from YAML frontmatter.

    Requirement: 117-REQ-2.2
    """

    def test_status_from_frontmatter(self) -> None:
        entry = parse_madr(VALID_MADR_CONTENT)
        assert entry is not None
        assert entry.status == "accepted"


# ===========================================================================
# TS-117-5: Parse status from H2 section
# ===========================================================================


class TestParseStatusSection:
    """TS-117-5: Verify status extraction from ## Status section.

    Requirement: 117-REQ-2.3
    """

    def test_status_from_h2_section(self) -> None:
        entry = parse_madr(VALID_MADR_NO_FRONTMATTER_WITH_STATUS)
        assert entry is not None
        assert entry.status == "accepted"


# ===========================================================================
# TS-117-6: Default status when absent
# ===========================================================================


class TestParseDefaultStatus:
    """TS-117-6: Verify default status 'proposed' when absent.

    Requirement: 117-REQ-2.4
    """

    def test_default_status_proposed(self) -> None:
        entry = parse_madr(VALID_MADR_NO_STATUS)
        assert entry is not None
        assert entry.status == "proposed"


# ===========================================================================
# TS-117-7: Parse synonym section headings
# ===========================================================================


class TestParseSynonymHeadings:
    """TS-117-7: Verify synonym headings are recognized.

    Requirement: 117-REQ-2.5
    """

    def test_options_considered_synonym(self) -> None:
        entry = parse_madr(VALID_MADR_SYNONYM_HEADING)
        assert entry is not None
        assert len(entry.considered_options) == 3


# ===========================================================================
# TS-117-8: Parse Decision Outcome chosen option
# ===========================================================================


class TestParseDecisionOutcome:
    """TS-117-8: Verify extraction of chosen option and justification.

    Requirement: 117-REQ-2.6
    """

    def test_chosen_option_and_justification(self) -> None:
        content = """\
# Test ADR

## Context and Problem Statement

We need to decide.

## Considered Options

- Option A
- Option B
- Option C

## Decision Outcome

Chosen option: "Option A", because it is simpler.
"""
        entry = parse_madr(content)
        assert entry is not None
        assert entry.chosen_option == "Option A"
        assert "simpler" in entry.justification


# ===========================================================================
# TS-117-E3: No H1 heading parse failure
# ===========================================================================


class TestParseNoH1:
    """TS-117-E3: Verify parse_madr returns None when no H1 heading.

    Requirement: 117-REQ-2.E1
    """

    def test_no_h1_returns_none(self) -> None:
        result = parse_madr("## Some H2 heading\n\nBody text")
        assert result is None


# ===========================================================================
# TS-117-9: Validation passes with 3+ options
# ===========================================================================


class TestValidationPasses:
    """TS-117-9: Verify validation passes for well-formed ADREntry.

    Requirements: 117-REQ-3.1, 117-REQ-3.4
    """

    def test_valid_entry_passes(self) -> None:
        entry = _make_adr_entry(
            title="Good ADR",
            chosen_option="Option A",
            considered_options=["Option A", "Option B", "Option C"],
            has_context_section=True,
            has_options_section=True,
            has_decision_section=True,
        )
        result = validate_madr(entry)
        assert result.passed is True
        assert result.diagnostics == []


# ===========================================================================
# TS-117-10: Validation fails with < 3 options
# ===========================================================================


class TestValidationFailsFewOptions:
    """TS-117-10: Verify validation fails with fewer than 3 options.

    Requirement: 117-REQ-3.2
    """

    def test_two_options_fails(self) -> None:
        entry = _make_adr_entry(
            considered_options=["Option A", "Option B"],
        )
        result = validate_madr(entry)
        assert result.passed is False
        assert any("3" in d for d in result.diagnostics)


# ===========================================================================
# TS-117-11: Validation fails with empty chosen option
# ===========================================================================


class TestValidationFailsNoChosen:
    """TS-117-11: Verify validation fails with empty chosen_option.

    Requirement: 117-REQ-3.3
    """

    def test_empty_chosen_option_fails(self) -> None:
        entry = _make_adr_entry(chosen_option="")
        result = validate_madr(entry)
        assert result.passed is False


# ===========================================================================
# TS-117-E4: Empty title validation failure
# ===========================================================================


class TestValidationEmptyTitle:
    """TS-117-E4: Verify validation fails with empty title.

    Requirement: 117-REQ-3.E1
    """

    def test_empty_title_fails(self) -> None:
        entry = _make_adr_entry(title="")
        result = validate_madr(entry)
        assert result.passed is False


# ===========================================================================
# TS-117-12: Store ADR entry in DuckDB
# ===========================================================================


class TestStoreADR:
    """TS-117-12: Verify store_adr inserts a row into adr_entries.

    Requirements: 117-REQ-4.1, 117-REQ-4.4
    """

    def test_store_and_retrieve(self, adr_conn: duckdb.DuckDBPyConnection) -> None:
        entry = _make_adr_entry(
            id="test-store-id",
            file_path="docs/adr/01-test.md",
        )
        count = store_adr(adr_conn, entry)
        assert count == 1

        rows = adr_conn.execute(
            "SELECT * FROM adr_entries WHERE id = ?",
            ["test-store-id"],
        ).fetchall()
        assert len(rows) == 1


# ===========================================================================
# TS-117-13: Content hash is SHA-256
# ===========================================================================


class TestContentHash:
    """TS-117-13: Verify content_hash is SHA-256 of file content.

    Requirement: 117-REQ-4.2
    """

    def test_content_hash_matches_sha256(
        self,
        adr_conn: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        adr_file = adr_dir / "01-test.md"
        adr_file.write_text(VALID_MADR_CONTENT, encoding="utf-8")

        expected_hash = hashlib.sha256(
            VALID_MADR_CONTENT.encode("utf-8")
        ).hexdigest()

        entry = ingest_adr(adr_conn, "docs/adr/01-test.md", tmp_path)
        assert entry is not None
        assert entry.content_hash == expected_hash


# ===========================================================================
# TS-117-14: Supersede on content change
# ===========================================================================


class TestSupersede:
    """TS-117-14: Verify modified ADR supersedes old entry.

    Requirements: 117-REQ-5.1, 117-REQ-5.3
    """

    def test_supersede_on_different_hash(
        self, adr_conn: duckdb.DuckDBPyConnection
    ) -> None:
        entry_v1 = _make_adr_entry(
            id="v1-id",
            file_path="docs/adr/01-test.md",
            content_hash="aaa",
        )
        entry_v2 = _make_adr_entry(
            id="v2-id",
            file_path="docs/adr/01-test.md",
            content_hash="bbb",
        )

        store_adr(adr_conn, entry_v1)
        store_adr(adr_conn, entry_v2)

        rows = adr_conn.execute(
            "SELECT superseded_at FROM adr_entries "
            "WHERE file_path = ? ORDER BY created_at",
            ["docs/adr/01-test.md"],
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] is not None  # v1 superseded
        assert rows[1][0] is None  # v2 active


# ===========================================================================
# TS-117-15: Skip duplicate ingestion
# ===========================================================================


class TestSkipDuplicate:
    """TS-117-15: Verify re-ingesting same content_hash is a no-op.

    Requirements: 117-REQ-5.2, 117-REQ-4.E2
    """

    def test_duplicate_returns_zero(
        self, adr_conn: duckdb.DuckDBPyConnection
    ) -> None:
        entry = _make_adr_entry(
            id="dup-id",
            file_path="docs/adr/01-test.md",
            content_hash="aaa",
        )
        store_adr(adr_conn, entry)

        entry_same_hash = _make_adr_entry(
            id="dup-id-2",
            file_path="docs/adr/01-test.md",
            content_hash="aaa",
        )
        count = store_adr(adr_conn, entry_same_hash)
        assert count == 0

        row_count = adr_conn.execute(
            "SELECT COUNT(*) FROM adr_entries WHERE file_path = ?",
            ["docs/adr/01-test.md"],
        ).fetchone()
        assert row_count is not None
        assert row_count[0] == 1


# ===========================================================================
# TS-117-E8: Superseded file_path with new content
# ===========================================================================


class TestSupersededWithNew:
    """TS-117-E8: Verify new entry is active when all existing are superseded.

    Requirement: 117-REQ-5.E1
    """

    def test_new_entry_active_after_all_superseded(
        self, adr_conn: duckdb.DuckDBPyConnection
    ) -> None:
        # Manually insert a superseded entry
        adr_conn.execute(
            "INSERT INTO adr_entries "
            "(id, file_path, title, status, summary, content_hash, superseded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                "old-id",
                "docs/adr/01-test.md",
                "Old ADR",
                "accepted",
                "Old summary",
                "old-hash",
                datetime.now(UTC),
            ],
        )

        new_entry = _make_adr_entry(
            id="new-id",
            file_path="docs/adr/01-test.md",
            content_hash="new-hash",
        )
        store_adr(adr_conn, new_entry)

        active = adr_conn.execute(
            "SELECT id FROM adr_entries "
            "WHERE file_path = ? AND superseded_at IS NULL",
            ["docs/adr/01-test.md"],
        ).fetchall()
        assert len(active) == 1
        assert active[0][0] == "new-id"


# ===========================================================================
# TS-117-E5: DB unavailable during store
# ===========================================================================


class TestStoreDBUnavailable:
    """TS-117-E5: Verify store_adr returns 0 when DB unavailable.

    Requirement: 117-REQ-4.E1
    """

    def test_closed_conn_returns_zero(self) -> None:
        conn = duckdb.connect(":memory:")
        _create_adr_entries_table(conn)
        conn.close()

        entry = _make_adr_entry()
        result = store_adr(conn, entry)
        assert result == 0


# ===========================================================================
# TS-117-16: Query ADRs by spec_refs match
# ===========================================================================


class TestQuerySpecRefs:
    """TS-117-16: Verify retrieval matches by spec reference.

    Requirement: 117-REQ-6.1
    """

    def test_query_by_spec_ref(
        self, adr_conn: duckdb.DuckDBPyConnection
    ) -> None:
        entry = _make_adr_entry(
            spec_refs=["42"],
            keywords=["rate", "limiter"],
        )
        store_adr(adr_conn, entry)

        results = query_adrs(adr_conn, "42_rate_limiting", "implement rate limiter")
        assert len(results) == 1
        assert "42" in results[0].spec_refs


# ===========================================================================
# TS-117-E6: adr_entries table missing during query
# ===========================================================================


class TestQueryNoTable:
    """TS-117-E6: Verify query_adrs returns empty list when table missing.

    Requirement: 117-REQ-6.E1
    """

    def test_missing_table_returns_empty(self) -> None:
        conn = duckdb.connect(":memory:")
        result = query_adrs(conn, "any_spec", "any task")
        assert result == []
        conn.close()


# ===========================================================================
# TS-117-E7: No matching ADRs
# ===========================================================================


class TestQueryNoMatch:
    """TS-117-E7: Verify empty return when no ADRs match.

    Requirement: 117-REQ-6.E2
    """

    def test_no_matching_adrs(
        self, adr_conn: duckdb.DuckDBPyConnection
    ) -> None:
        entry = _make_adr_entry(
            spec_refs=["10"],
            keywords=["widget"],
        )
        store_adr(adr_conn, entry)

        result = query_adrs(adr_conn, "99_unrelated", "unrelated task")
        assert result == []


# ===========================================================================
# TS-117-17: Format ADR for prompt
# ===========================================================================


class TestFormatPrompt:
    """TS-117-17: Verify prompt formatting produces [ADR]-prefixed string.

    Requirement: 117-REQ-6.2
    """

    def test_format_adr_for_prompt(self) -> None:
        entry = _make_adr_entry(
            title="Use DuckDB",
            chosen_option="DuckDB",
            justification="embedded, zero-config",
            considered_options=["DuckDB", "SQLite", "PostgreSQL", "Redis"],
            summary=(
                'Use DuckDB: Chose "DuckDB" over "SQLite", "PostgreSQL", "Redis". '
                "embedded, zero-config"
            ),
        )
        result = format_adrs_for_prompt([entry])
        assert len(result) == 1
        assert result[0].startswith("[ADR] ")
        assert '"DuckDB"' in result[0]
        assert '"SQLite"' in result[0]


# ===========================================================================
# TS-117-19: Extract spec refs from content
# ===========================================================================


class TestExtractSpecRefs:
    """TS-117-19: Verify spec reference extraction from content.

    Requirement: 117-REQ-6.4
    """

    def test_extract_spec_refs(self) -> None:
        content = (
            "As specified in 42-REQ-1.1, we need this.\n"
            "See also spec 15 for background.\n"
            "The pattern from 03_base_app is relevant."
        )
        refs = extract_spec_refs(content)
        assert "42" in refs
        assert "15" in refs
        assert "03" in refs


# ===========================================================================
# TS-117-20: Extract keywords from title
# ===========================================================================


class TestExtractKeywords:
    """TS-117-20: Verify keyword extraction from ADR title.

    Requirement: 117-REQ-6.5
    """

    def test_extract_keywords(self) -> None:
        keywords = extract_keywords("Use Claude Exclusively for Coding Agents")
        assert "claude" in keywords
        assert "exclusively" in keywords
        assert "coding" in keywords
        assert "agents" in keywords
        assert "use" not in keywords
        assert "for" not in keywords


# ===========================================================================
# TS-117-21: Validation warning emits audit event
# ===========================================================================


class TestValidationWarningAudit:
    """TS-117-21: Verify failed validation emits ADR_VALIDATION_FAILED event.

    Requirements: 117-REQ-7.1, 117-REQ-7.2, 117-REQ-7.3
    """

    def test_validation_failure_emits_audit_event(
        self,
        adr_conn: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        # Write an ADR with only 1 considered option (fails validation)
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        invalid_content = """\
# Bad ADR

## Context and Problem Statement

Context.

## Considered Options

- Only One Option

## Decision Outcome

Chosen option: "Only One Option", because there is no choice.
"""
        (adr_dir / "01-bad.md").write_text(invalid_content, encoding="utf-8")

        sink = MockSinkDispatcher()
        result = ingest_adr(
            adr_conn,
            "docs/adr/01-bad.md",
            tmp_path,
            sink=sink,
            run_id="test",
        )

        # Validation failure: should not be ingested
        assert result is None

        # Should have emitted an audit event
        events = sink.captured_events
        assert any(
            e.event_type.value == "adr.validation_failed"
            for e in events
        )


# ===========================================================================
# TS-117-22: Successful ingestion emits audit event
# ===========================================================================


class TestIngestionAudit:
    """TS-117-22: Verify successful ingestion emits ADR_INGESTED event.

    Requirement: 117-REQ-7.4
    """

    def test_successful_ingestion_emits_audit_event(
        self,
        adr_conn: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "01-good.md").write_text(
            VALID_MADR_NO_STATUS, encoding="utf-8"
        )

        sink = MockSinkDispatcher()
        entry = ingest_adr(
            adr_conn,
            "docs/adr/01-good.md",
            tmp_path,
            sink=sink,
            run_id="test",
        )
        assert entry is not None

        events = sink.captured_events
        assert any(
            e.event_type.value == "adr.ingested"
            for e in events
        )


# ===========================================================================
# TS-117-18: FoxKnowledgeProvider.retrieve includes ADRs
# ===========================================================================


class TestProviderRetrieveIncludesADRs:
    """TS-117-18: Verify FoxKnowledgeProvider.retrieve returns ADR strings.

    Requirement: 117-REQ-6.3
    """

    def test_retrieve_includes_adr_items(
        self, migrated_conn: duckdb.DuckDBPyConnection
    ) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.db import KnowledgeDB
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        # Store an ADR entry matching spec "42"
        entry = _make_adr_entry(
            spec_refs=["42"],
            keywords=["rate", "limiter"],
        )
        store_adr(migrated_conn, entry)

        # Create provider
        db = KnowledgeDB.__new__(KnowledgeDB)
        db._conn = migrated_conn

        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())
        results = provider.retrieve("42_rate_limiting", "implement rate limiter")

        adr_items = [r for r in results if r.startswith("[ADR]")]
        assert len(adr_items) >= 1


# ===========================================================================
# TS-117-SMOKE-1: Full Ingest Pipeline
# ===========================================================================


class TestSmokeIngestPipeline:
    """TS-117-SMOKE-1: Full ingest pipeline with real components.

    Execution Path 1 from design.md.
    Must NOT satisfy with mocking parse_madr, validate_madr, or store_adr.
    """

    def test_full_ingest_pipeline(
        self,
        migrated_conn: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        # Setup: write a valid MADR file
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "07-test.md").write_text(
            VALID_MADR_NO_STATUS, encoding="utf-8"
        )

        # Execute
        entry = ingest_adr(
            migrated_conn,
            "docs/adr/07-test.md",
            tmp_path,
        )

        # Verify
        assert entry is not None

        rows = migrated_conn.execute(
            "SELECT title FROM adr_entries WHERE file_path = ?",
            ["docs/adr/07-test.md"],
        ).fetchall()
        assert len(rows) == 1

        # Verify content hash
        file_content = (adr_dir / "07-test.md").read_text(encoding="utf-8")
        expected_hash = hashlib.sha256(
            file_content.encode("utf-8")
        ).hexdigest()
        assert entry.content_hash == expected_hash


# ===========================================================================
# TS-117-SMOKE-2: Full Retrieve Pipeline
# ===========================================================================


class TestSmokeRetrievePipeline:
    """TS-117-SMOKE-2: Full retrieve pipeline with real components.

    Execution Path 2 from design.md.
    Must NOT satisfy with mocking query_adrs or format_adrs_for_prompt.
    """

    def test_full_retrieve_pipeline(
        self,
        migrated_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        from agent_fox.core.config import KnowledgeProviderConfig
        from agent_fox.knowledge.db import KnowledgeDB
        from agent_fox.knowledge.fox_provider import FoxKnowledgeProvider

        # Store an ADR entry with spec_ref "42"
        entry = _make_adr_entry(
            spec_refs=["42"],
            keywords=["rate", "limiter"],
        )
        store_adr(migrated_conn, entry)

        # Create provider
        db = KnowledgeDB.__new__(KnowledgeDB)
        db._conn = migrated_conn

        provider = FoxKnowledgeProvider(db, KnowledgeProviderConfig())

        # Execute
        results = provider.retrieve("42_rate_limiting", "implement rate limiter")

        # Verify
        adr_items = [r for r in results if r.startswith("[ADR]")]
        assert len(adr_items) >= 1


# ===========================================================================
# Additional: Query by keyword overlap (covers 117-REQ-6.1 keyword path)
# ===========================================================================


class TestQueryKeywordOverlap:
    """Verify query_adrs matches by keyword overlap with task_description.

    Requirement: 117-REQ-6.1 (keyword matching sub-case)
    """

    def test_keyword_overlap_match(
        self, adr_conn: duckdb.DuckDBPyConnection
    ) -> None:
        entry = _make_adr_entry(
            spec_refs=[],
            keywords=["widget", "framework", "performance"],
        )
        store_adr(adr_conn, entry)

        results = query_adrs(
            adr_conn,
            "99_unrelated_spec",
            "improve widget performance",
        )
        assert len(results) >= 1


# ===========================================================================
# Additional: Deleted ADR file skipped (covers 117-REQ-1.3)
# ===========================================================================


class TestDeletedADRFileSkipped:
    """Verify ingest_adr returns None for deleted ADR file.

    Requirement: 117-REQ-1.3
    """

    def test_deleted_file_returns_none(
        self,
        adr_conn: duckdb.DuckDBPyConnection,
        tmp_path: Path,
    ) -> None:
        # File does not exist on disk
        result = ingest_adr(
            adr_conn,
            "docs/adr/01-deleted.md",
            tmp_path,
        )
        assert result is None


# ===========================================================================
# Additional: store_adr with missing table (covers 117-REQ-4.4)
# ===========================================================================


class TestStoreMissingTable:
    """Verify store_adr returns 0 when adr_entries table is missing.

    Requirement: 117-REQ-4.4
    """

    def test_missing_table_returns_zero(self) -> None:
        conn = duckdb.connect(":memory:")
        entry = _make_adr_entry()
        result = store_adr(conn, entry)
        assert result == 0
        conn.close()
