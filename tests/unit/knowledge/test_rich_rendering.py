"""Unit tests for rich memory rendering with enrichments.

Test Spec: TS-111-1 through TS-111-25
Requirements: 111-REQ-1.* through 111-REQ-7.*
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb

from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.rendering import (
    Enrichments,
    _format_relative_age,
    _render_fact,
    load_enrichments,
    render_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fact(
    *,
    fact_id: str | None = None,
    content: str = "A test fact",
    category: str = "gotcha",
    spec_name: str = "my_spec",
    confidence: float = 0.90,
    created_at: str = "2026-04-10T12:00:00",
    supersedes: str | None = None,
) -> Fact:
    """Return a Fact with controlled fields for testing."""
    return Fact(
        id=fact_id or str(uuid.uuid4()),
        content=content,
        category=category,
        spec_name=spec_name,
        keywords=[],
        confidence=confidence,
        created_at=created_at,
        supersedes=supersedes,
    )


def _empty_enrichments() -> Enrichments:
    """Return an Enrichments instance with all fields empty."""
    return Enrichments(
        causes={},
        effects={},
        entity_paths={},
        superseded={},
    )


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    *,
    fact_id: str,
    content: str,
    category: str = "gotcha",
    spec_name: str = "test_spec",
    confidence: float = 0.90,
    created_at: str = "2026-04-10T12:00:00",
    superseded_by: str | None = None,
) -> None:
    """Insert a fact into DuckDB for testing."""
    conn.execute(
        """
        INSERT INTO memory_facts (id, content, category, spec_name,
                                  confidence, created_at, superseded_by)
        VALUES (?::UUID, ?, ?, ?, ?, ?::TIMESTAMP, ?::UUID)
        """,
        [fact_id, content, category, spec_name, confidence, created_at, superseded_by],
    )


# ---------------------------------------------------------------------------
# TS-111-1: Summary header with fact count and date
# ---------------------------------------------------------------------------


class TestSummaryHeader:
    """TS-111-1: Summary header shows fact count and last-updated date.

    Requirements: 111-REQ-1.1, 111-REQ-1.2
    """

    def test_summary_header(
        self, schema_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Output contains fact count and last-updated date after the heading."""
        output_path = tmp_path / "memory.md"

        _insert_fact(
            schema_conn,
            fact_id=str(uuid.uuid4()),
            content="Fact 1",
            created_at="2026-04-08T10:00:00",
        )
        _insert_fact(
            schema_conn,
            fact_id=str(uuid.uuid4()),
            content="Fact 2",
            created_at="2026-04-09T10:00:00",
        )
        _insert_fact(
            schema_conn,
            fact_id=str(uuid.uuid4()),
            content="Fact 3",
            created_at="2026-04-10T12:00:00",
        )

        render_summary(conn=schema_conn, output_path=output_path)

        content = output_path.read_text()
        lines = [line for line in content.splitlines() if line.strip()]
        assert lines[0] == "# Agent-Fox Memory"
        assert "_3 facts | last updated: 2026-04-10_" in lines[1]


# ---------------------------------------------------------------------------
# TS-111-2: Summary header with unparseable dates
# ---------------------------------------------------------------------------


class TestSummaryHeaderUnparseableDates:
    """TS-111-2: Summary header omits last-updated when all dates are invalid.

    Requirement: 111-REQ-1.E1
    """

    def test_summary_header_unparseable_dates(self, tmp_path: Path) -> None:
        """Summary line is '_N facts_' when all created_at values are empty."""
        output_path = tmp_path / "memory.md"

        facts = [
            _make_fact(content="Fact 1", created_at=""),
            _make_fact(content="Fact 2", created_at=""),
        ]

        with patch("agent_fox.knowledge.rendering.read_all_facts", return_value=facts):
            render_summary(conn=None, output_path=output_path)

        content = output_path.read_text()
        assert "_2 facts_" in content
        assert "last updated" not in content


# ---------------------------------------------------------------------------
# TS-111-3: Relative age -- days format
# ---------------------------------------------------------------------------


class TestRelativeAgeDays:
    """TS-111-3: _format_relative_age returns 'Xd ago' for ages under 60 days.

    Requirements: 111-REQ-2.1, 111-REQ-2.2, 111-REQ-2.3
    """

    def test_relative_age_days(self) -> None:
        """14 days ago returns '14d ago'."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        created_at = "2026-04-02T12:00:00"  # 14 days before now

        result = _format_relative_age(created_at, now)

        assert result == "14d ago"


# ---------------------------------------------------------------------------
# TS-111-4: Relative age -- months format
# ---------------------------------------------------------------------------


class TestRelativeAgeMonths:
    """TS-111-4: _format_relative_age returns 'Xmo ago' for 60-364 days.

    Requirement: 111-REQ-2.2
    """

    def test_relative_age_months(self) -> None:
        """90 days ago returns '3mo ago'."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        created_at = "2026-01-16T12:00:00"  # 90 days before now

        result = _format_relative_age(created_at, now)

        assert result == "3mo ago"


# ---------------------------------------------------------------------------
# TS-111-5: Relative age -- years format
# ---------------------------------------------------------------------------


class TestRelativeAgeYears:
    """TS-111-5: _format_relative_age returns 'Xy ago' for 365+ days.

    Requirement: 111-REQ-2.2
    """

    def test_relative_age_years(self) -> None:
        """400 days ago returns '1y ago'."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        created_at = "2025-03-12T12:00:00"  # 400 days before 2026-04-16

        result = _format_relative_age(created_at, now)

        assert result == "1y ago"


# ---------------------------------------------------------------------------
# TS-111-6: Relative age -- boundary at 60 days
# ---------------------------------------------------------------------------


class TestRelativeAgeBoundary:
    """TS-111-6: Boundary between 'd ago' and 'mo ago' is at 60 days.

    Requirement: 111-REQ-2.2
    """

    def test_relative_age_59_days_is_days(self) -> None:
        """59 days ago returns '59d ago'."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        # 2026-04-16 - 59 days = 2026-02-16
        created_at = "2026-02-16T12:00:00"

        result = _format_relative_age(created_at, now)

        assert result == "59d ago"

    def test_relative_age_60_days_is_months(self) -> None:
        """60 days ago returns '2mo ago'."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        # 2026-04-16 - 60 days = 2026-02-15
        created_at = "2026-02-15T12:00:00"

        result = _format_relative_age(created_at, now)

        assert result == "2mo ago"


# ---------------------------------------------------------------------------
# TS-111-7: Relative age -- missing created_at
# ---------------------------------------------------------------------------


class TestRelativeAgeMissing:
    """TS-111-7: _format_relative_age returns None for missing/unparseable input.

    Requirement: 111-REQ-2.E1
    """

    def test_relative_age_missing(self) -> None:
        """Empty created_at returns None."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)

        result = _format_relative_age("", now)

        assert result is None

    def test_relative_age_unparseable(self) -> None:
        """Garbage created_at returns None."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)

        result = _format_relative_age("not-a-date", now)

        assert result is None


# ---------------------------------------------------------------------------
# TS-111-8: Metadata parenthetical includes age
# ---------------------------------------------------------------------------


class TestMetadataWithAge:
    """TS-111-8: Metadata parenthetical includes age when created_at is valid.

    Requirement: 111-REQ-2.3
    """

    def test_metadata_with_age(self) -> None:
        """Output contains _(spec: my_spec, confidence: 0.90, 14d ago)_."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact(
            spec_name="my_spec",
            confidence=0.90,
            created_at="2026-04-02T12:00:00",  # 14 days before now
        )

        result = _render_fact(fact, _empty_enrichments(), now)

        assert "_(spec: my_spec, confidence: 0.90, 14d ago)_" in result


# ---------------------------------------------------------------------------
# TS-111-9: Metadata parenthetical without age
# ---------------------------------------------------------------------------


class TestMetadataWithoutAge:
    """TS-111-9: Metadata parenthetical omits age when created_at is invalid.

    Requirement: 111-REQ-2.E1
    """

    def test_metadata_without_age(self) -> None:
        """Output contains _(spec: my_spec, confidence: 0.90)_ without age."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact(
            spec_name="my_spec",
            confidence=0.90,
            created_at="",
        )

        result = _render_fact(fact, _empty_enrichments(), now)

        assert "_(spec: my_spec, confidence: 0.90)_" in result
        assert "ago" not in result


# ---------------------------------------------------------------------------
# TS-111-10: Fact ordering by confidence then date
# ---------------------------------------------------------------------------


class TestFactOrdering:
    """TS-111-10: Facts within a category appear in confidence desc, date desc order.

    Requirement: 111-REQ-3.1
    """

    def test_fact_ordering(
        self, schema_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Facts appear as B (0.90, Apr 10), A (0.90, Apr 1), C (0.60, Apr 15)."""
        output_path = tmp_path / "memory.md"

        _insert_fact(
            schema_conn,
            fact_id=str(uuid.uuid4()),
            content="Fact A",
            category="gotcha",
            confidence=0.90,
            created_at="2026-04-01T10:00:00",
        )
        _insert_fact(
            schema_conn,
            fact_id=str(uuid.uuid4()),
            content="Fact B",
            category="gotcha",
            confidence=0.90,
            created_at="2026-04-10T10:00:00",
        )
        _insert_fact(
            schema_conn,
            fact_id=str(uuid.uuid4()),
            content="Fact C",
            category="gotcha",
            confidence=0.60,
            created_at="2026-04-15T10:00:00",
        )

        render_summary(conn=schema_conn, output_path=output_path)

        content = output_path.read_text()
        pos_a = content.index("Fact A")
        pos_b = content.index("Fact B")
        pos_c = content.index("Fact C")

        # B before A (same confidence, B is newer), C last (lower confidence)
        assert pos_b < pos_a < pos_c


# ---------------------------------------------------------------------------
# TS-111-11: Fact ordering stability
# ---------------------------------------------------------------------------


class TestFactOrderingStability:
    """TS-111-11: Fact ordering is deterministic for identical confidence and date.

    Requirement: 111-REQ-3.E1
    """

    def test_fact_ordering_stability(self, tmp_path: Path) -> None:
        """Two calls with identical facts produce identical output."""
        facts = [
            _make_fact(
                fact_id=str(uuid.uuid4()),
                content=f"Fact {i}",
                confidence=0.90,
                created_at="2026-04-01T10:00:00",
            )
            for i in range(3)
        ]

        out1 = tmp_path / "memory1.md"
        out2 = tmp_path / "memory2.md"

        with patch("agent_fox.knowledge.rendering.read_all_facts", return_value=facts):
            render_summary(conn=None, output_path=out1)
            render_summary(conn=None, output_path=out2)

        assert out1.read_text() == out2.read_text()


# ---------------------------------------------------------------------------
# TS-111-12: Entity path sub-bullets
# ---------------------------------------------------------------------------


class TestEntityPathSubbullets:
    """TS-111-12: Entity paths render as a single 'files:' sub-bullet.

    Requirement: 111-REQ-4.1
    """

    def test_entity_path_subbullets(self) -> None:
        """Two entity paths appear as '  - files: path1, path2'."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        enrichments = Enrichments(
            causes={},
            effects={},
            entity_paths={fact.id: ["path/to/file1.py", "path/to/file2.py"]},
            superseded={},
        )

        result = _render_fact(fact, enrichments, now)

        assert "  - files: path/to/file1.py, path/to/file2.py" in result


# ---------------------------------------------------------------------------
# TS-111-13: Entity path overflow
# ---------------------------------------------------------------------------


class TestEntityPathOverflow:
    """TS-111-13: More than 3 entity paths show '+N more'.

    Requirement: 111-REQ-4.2
    """

    def test_entity_path_overflow(self) -> None:
        """5 entity paths: first 3 shown, '+2 more' appended."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        enrichments = Enrichments(
            causes={},
            effects={},
            entity_paths={
                fact.id: [
                    "path/file1.py",
                    "path/file2.py",
                    "path/file3.py",
                    "path/file4.py",
                    "path/file5.py",
                ]
            },
            superseded={},
        )

        result = _render_fact(fact, enrichments, now)

        assert "path/file1.py" in result
        assert "path/file2.py" in result
        assert "path/file3.py" in result
        assert "path/file4.py" not in result
        assert "+2 more" in result


# ---------------------------------------------------------------------------
# TS-111-14: No entity paths
# ---------------------------------------------------------------------------


class TestNoEntityPaths:
    """TS-111-14: No entity paths means no 'files:' sub-bullet.

    Requirement: 111-REQ-4.E1
    """

    def test_no_entity_paths(self) -> None:
        """Fact with no entities has no 'files:' sub-bullet."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()

        result = _render_fact(fact, _empty_enrichments(), now)

        assert "files:" not in result


# ---------------------------------------------------------------------------
# TS-111-15: Cause sub-bullets
# ---------------------------------------------------------------------------


class TestCauseSubbullets:
    """TS-111-15: Cause sub-bullets with content truncated to 60 chars.

    Requirement: 111-REQ-5.1
    """

    def test_cause_subbullets(self) -> None:
        """Two causes with 80-char content render as truncated 'cause:' bullets."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        long_content = "A" * 80
        enrichments = Enrichments(
            causes={fact.id: [long_content, long_content]},
            effects={},
            entity_paths={},
            superseded={},
        )

        result = _render_fact(fact, enrichments, now)

        cause_lines = [line for line in result.splitlines() if "cause:" in line]
        assert len(cause_lines) == 2
        for line in cause_lines:
            assert "A" * 60 in line
            assert "A" * 61 not in line


# ---------------------------------------------------------------------------
# TS-111-16: Effect sub-bullets
# ---------------------------------------------------------------------------


class TestEffectSubbullets:
    """TS-111-16: Effect sub-bullets appear for facts with causal successors.

    Requirement: 111-REQ-5.2
    """

    def test_effect_subbullets(self) -> None:
        """Two effects render as 'effect:' sub-bullets with their content."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        enrichments = Enrichments(
            causes={},
            effects={fact.id: ["Effect 1 content", "Effect 2 content"]},
            entity_paths={},
            superseded={},
        )

        result = _render_fact(fact, enrichments, now)

        effect_lines = [line for line in result.splitlines() if "effect:" in line]
        assert len(effect_lines) == 2
        assert "Effect 1 content" in result
        assert "Effect 2 content" in result


# ---------------------------------------------------------------------------
# TS-111-17: Cause/effect limit enforcement
# ---------------------------------------------------------------------------


class TestCauseEffectLimit:
    """TS-111-17: Cause and effect sub-bullets capped at 2 each.

    Requirements: 111-REQ-5.1, 111-REQ-5.2
    """

    def test_cause_effect_limit(self) -> None:
        """5 causes and 5 effects yield exactly 2 cause and 2 effect bullets."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        enrichments = Enrichments(
            causes={fact.id: [f"Cause {i}" for i in range(5)]},
            effects={fact.id: [f"Effect {i}" for i in range(5)]},
            entity_paths={},
            superseded={},
        )

        result = _render_fact(fact, enrichments, now)

        cause_lines = [line for line in result.splitlines() if "  - cause:" in line]
        effect_lines = [line for line in result.splitlines() if "  - effect:" in line]
        assert len(cause_lines) == 2
        assert len(effect_lines) == 2


# ---------------------------------------------------------------------------
# TS-111-18: No causal links
# ---------------------------------------------------------------------------


class TestNoCausalLinks:
    """TS-111-18: No causal links means no cause/effect sub-bullets.

    Requirement: 111-REQ-5.E1
    """

    def test_no_causal_links(self) -> None:
        """Fact with no causal links has no cause/effect sub-bullets."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()

        result = _render_fact(fact, _empty_enrichments(), now)

        assert "cause:" not in result
        assert "effect:" not in result


# ---------------------------------------------------------------------------
# TS-111-19: Supersession sub-bullet
# ---------------------------------------------------------------------------


class TestSupersessionSubbullet:
    """TS-111-19: Superseded content renders as a 'replaces:' sub-bullet.

    Requirement: 111-REQ-6.1
    """

    def test_supersession_subbullet(self) -> None:
        """100-char old content renders as 'replaces:' truncated to 80 chars."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        old_content = "B" * 100
        enrichments = Enrichments(
            causes={},
            effects={},
            entity_paths={},
            superseded={fact.id: old_content},
        )

        result = _render_fact(fact, enrichments, now)

        assert "  - replaces:" in result
        assert "B" * 80 in result
        assert "B" * 81 not in result


# ---------------------------------------------------------------------------
# TS-111-20: No supersession
# ---------------------------------------------------------------------------


class TestNoSupersession:
    """TS-111-20: No supersession means no 'replaces:' sub-bullet.

    Requirement: 111-REQ-6.E1
    """

    def test_no_supersession(self) -> None:
        """Fact that superseded nothing has no 'replaces:' sub-bullet."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()

        result = _render_fact(fact, _empty_enrichments(), now)

        assert "replaces:" not in result


# ---------------------------------------------------------------------------
# TS-111-21: Enrichment loading -- batch queries
# ---------------------------------------------------------------------------


class TestEnrichmentLoading:
    """TS-111-21: load_enrichments returns correct data from real DuckDB.

    Requirements: 111-REQ-7.1, 111-REQ-7.2
    """

    def test_enrichment_loading(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """load_enrichments returns causes, effects, entity_paths, superseded."""
        cause_id = str(uuid.uuid4())
        effect_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        fact_id = str(uuid.uuid4())
        old_fact_id = str(uuid.uuid4())

        # Insert facts
        knowledge_conn.execute(
            """
            INSERT INTO memory_facts
                (id, content, category, spec_name, confidence, created_at)
            VALUES
                (?::UUID, 'Main fact', 'gotcha', 'spec1', 0.9, CURRENT_TIMESTAMP),
                (?::UUID, 'Cause fact', 'gotcha', 'spec1', 0.9, CURRENT_TIMESTAMP),
                (?::UUID, 'Effect fact', 'gotcha', 'spec1', 0.9, CURRENT_TIMESTAMP),
                (?::UUID, 'Old superseded fact content', 'gotcha', 'spec1',
                 0.9, CURRENT_TIMESTAMP)
            """,
            [fact_id, cause_id, effect_id, old_fact_id],
        )

        # Causal links: cause_id -> fact_id -> effect_id
        knowledge_conn.execute(
            """
            INSERT INTO fact_causes (cause_id, effect_id)
            VALUES (?::UUID, ?::UUID), (?::UUID, ?::UUID)
            """,
            [cause_id, fact_id, fact_id, effect_id],
        )

        # Entity in entity_graph (lowercase 'file' per EntityType.FILE)
        knowledge_conn.execute(
            """
            INSERT INTO entity_graph (id, entity_type, entity_name, entity_path)
            VALUES (?::UUID, 'file', 'store', 'agent_fox/knowledge/store.py')
            """,
            [entity_id],
        )
        knowledge_conn.execute(
            """
            INSERT INTO fact_entities (fact_id, entity_id)
            VALUES (?::UUID, ?::UUID)
            """,
            [fact_id, entity_id],
        )

        # Mark old_fact_id as superseded by fact_id
        knowledge_conn.execute(
            "UPDATE memory_facts SET superseded_by = ?::UUID WHERE id = ?::UUID",
            [fact_id, old_fact_id],
        )

        enrichments = load_enrichments(knowledge_conn, [fact_id])

        assert fact_id in enrichments.causes
        assert any("Cause fact" in c for c in enrichments.causes[fact_id])

        assert fact_id in enrichments.effects
        assert any("Effect fact" in e for e in enrichments.effects[fact_id])

        assert fact_id in enrichments.entity_paths
        assert "agent_fox/knowledge/store.py" in enrichments.entity_paths[fact_id]

        assert fact_id in enrichments.superseded
        assert "Old superseded fact content" in enrichments.superseded[fact_id]


# ---------------------------------------------------------------------------
# TS-111-22: Enrichment query failure isolation
# ---------------------------------------------------------------------------


class TestEnrichmentQueryFailureIsolation:
    """TS-111-22: A failure in one enrichment query doesn't block the others.

    Requirement: 111-REQ-7.E1
    """

    def test_enrichment_query_failure_isolation(self) -> None:
        """Causes query failure yields empty causes; other enrichments proceed."""
        fact_id = str(uuid.uuid4())
        call_count = [0]

        def execute_side_effect(sql: str, *args: object, **kwargs: object) -> MagicMock:
            call_count[0] += 1
            if call_count[0] == 1:
                raise duckdb.Error("SQL error in causes query")
            cursor = MagicMock()
            cursor.fetchall.return_value = []
            return cursor

        conn = MagicMock()
        conn.execute.side_effect = execute_side_effect

        enrichments = load_enrichments(conn, [fact_id])

        assert enrichments.causes == {}
        assert isinstance(enrichments.effects, dict)
        assert isinstance(enrichments.entity_paths, dict)
        assert isinstance(enrichments.superseded, dict)


# ---------------------------------------------------------------------------
# TS-111-23: Enrichment with None connection
# ---------------------------------------------------------------------------


class TestEnrichmentNoneConnection:
    """TS-111-23: load_enrichments(conn=None) returns empty Enrichments.

    Requirement: 111-REQ-7.E2
    """

    def test_enrichment_none_connection(self) -> None:
        """None connection returns Enrichments with all empty dicts."""
        fact_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

        enrichments = load_enrichments(None, fact_ids)

        assert enrichments.causes == {}
        assert enrichments.effects == {}
        assert enrichments.entity_paths == {}
        assert enrichments.superseded == {}


# ---------------------------------------------------------------------------
# TS-111-24: Content truncation correctness
# ---------------------------------------------------------------------------


class TestContentTruncation:
    """TS-111-24: Truncation boundaries at 60 chars (cause/effect) and 80 (superseded).

    Requirements: 111-REQ-5.1, 111-REQ-6.1
    """

    def test_cause_60_chars_unchanged(self) -> None:
        """60-char cause content is rendered without ellipsis."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        content_60 = "C" * 60
        enrichments = Enrichments(
            causes={fact.id: [content_60]},
            effects={},
            entity_paths={},
            superseded={},
        )

        result = _render_fact(fact, enrichments, now)

        cause_lines = [line for line in result.splitlines() if "cause:" in line]
        assert len(cause_lines) >= 1
        assert content_60 in cause_lines[0]
        assert content_60 + "…" not in cause_lines[0]
        assert content_60 + "..." not in cause_lines[0]

    def test_cause_61_chars_truncated(self) -> None:
        """61-char cause content is truncated to 60 chars plus ellipsis."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        content_61 = "D" * 61
        enrichments = Enrichments(
            causes={fact.id: [content_61]},
            effects={},
            entity_paths={},
            superseded={},
        )

        result = _render_fact(fact, enrichments, now)

        cause_lines = [line for line in result.splitlines() if "cause:" in line]
        assert len(cause_lines) >= 1
        assert "D" * 60 in cause_lines[0]
        assert "D" * 61 not in cause_lines[0]

    def test_superseded_80_chars_unchanged(self) -> None:
        """80-char superseded content is rendered without ellipsis."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        content_80 = "E" * 80
        enrichments = Enrichments(
            causes={},
            effects={},
            entity_paths={},
            superseded={fact.id: content_80},
        )

        result = _render_fact(fact, enrichments, now)

        replaces_lines = [line for line in result.splitlines() if "replaces:" in line]
        assert len(replaces_lines) >= 1
        assert content_80 in replaces_lines[0]
        assert content_80 + "…" not in replaces_lines[0]
        assert content_80 + "..." not in replaces_lines[0]

    def test_superseded_81_chars_truncated(self) -> None:
        """81-char superseded content is truncated to 80 chars plus ellipsis."""
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        fact = _make_fact()
        content_81 = "F" * 81
        enrichments = Enrichments(
            causes={},
            effects={},
            entity_paths={},
            superseded={fact.id: content_81},
        )

        result = _render_fact(fact, enrichments, now)

        replaces_lines = [line for line in result.splitlines() if "replaces:" in line]
        assert len(replaces_lines) >= 1
        assert "F" * 80 in replaces_lines[0]
        assert "F" * 81 not in replaces_lines[0]


# ---------------------------------------------------------------------------
# TS-111-25: Full render with all enrichments
# ---------------------------------------------------------------------------


class TestFullRenderAllEnrichments:
    """TS-111-25: Full render with and without enrichments produces valid markdown.

    Requirements: All
    """

    def test_full_render_with_all_enrichments(self, tmp_path: Path) -> None:
        """Fact 1 has all enrichments; Fact 2 has none. Output is valid markdown."""
        fact1_id = str(uuid.uuid4())
        fact2_id = str(uuid.uuid4())
        output_path = tmp_path / "memory.md"

        fact1 = _make_fact(fact_id=fact1_id, content="Enriched fact", category="gotcha")
        fact2 = _make_fact(fact_id=fact2_id, content="Plain fact", category="pattern")

        enrichments = Enrichments(
            causes={fact1_id: ["Some cause content"]},
            effects={fact1_id: ["Some effect content"]},
            entity_paths={fact1_id: ["agent_fox/knowledge/rendering.py"]},
            superseded={fact1_id: "Old content that was replaced by this fact"},
        )

        with (
            patch("agent_fox.knowledge.rendering.read_all_facts", return_value=[fact1, fact2]),
            patch("agent_fox.knowledge.rendering.load_enrichments", return_value=enrichments),
        ):
            render_summary(conn=None, output_path=output_path)

        content = output_path.read_text()

        # Valid markdown
        assert content.startswith("# Agent-Fox Memory")

        # Summary header present
        assert "_2 facts" in content

        # Both facts in output
        assert "Enriched fact" in content
        assert "Plain fact" in content

        # Fact 1 has all enrichment sub-bullets
        assert "cause:" in content
        assert "effect:" in content
        assert "files:" in content
        assert "replaces:" in content
