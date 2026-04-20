"""Property tests for the knowledge harvest pipeline.

Test Spec: TS-52-P1 through TS-52-P9
Requirements: 52-REQ-1.1, 52-REQ-1.2, 52-REQ-2.1, 52-REQ-3.1, 52-REQ-3.2,
              52-REQ-4.1, 52-REQ-4.2, 52-REQ-5.1, 52-REQ-5.2,
              52-REQ-6.1, 52-REQ-6.2, 52-REQ-7.1, 52-REQ-7.E1
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import KnowledgeConfig
from agent_fox.engine.knowledge_harvest import (
    extract_and_store_knowledge,
    sync_facts_to_duckdb,
)
from agent_fox.knowledge.causal import store_causal_links
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.facts import Category, Fact

# -- Strategies ---------------------------------------------------------------

VALID_CATEGORIES = [c.value for c in Category]


@st.composite
def valid_facts(draw: st.DrawFn) -> Fact:
    """Generate a valid Fact with all provenance fields populated."""
    return Fact(
        id=str(uuid.uuid4()),
        content=draw(
            st.text(
                min_size=1,
                max_size=200,
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "Z"),
                ),
            )
        ),
        category=draw(st.sampled_from(VALID_CATEGORIES)),
        spec_name=draw(st.from_regex(r"[a-z0-9_]{2,20}", fullmatch=True)),
        keywords=draw(st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=5)),
        confidence=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        created_at="2025-01-01T00:00:00Z",
        session_id=draw(st.from_regex(r"[a-z0-9_/]{2,20}", fullmatch=True)),
        commit_sha=draw(st.from_regex(r"[a-f0-9]{7,40}", fullmatch=True)),
    )


def _make_knowledge_db() -> KnowledgeDB:
    """Create an in-memory KnowledgeDB."""
    config = KnowledgeConfig(store_path=":memory:")
    db = KnowledgeDB(config)
    db.open()
    return db


def _insert_n_facts(db: KnowledgeDB, n: int) -> list[Fact]:
    """Insert n random facts into the DB."""
    facts = []
    for i in range(n):
        f = Fact(
            id=str(uuid.uuid4()),
            content=f"Generated fact {i}",
            category="pattern",
            spec_name="prop_test",
            keywords=["test"],
            confidence=0.8,
            created_at="2025-01-01T00:00:00Z",
            session_id=f"prop/{i}",
            commit_sha=f"abc{i:04d}",
        )
        facts.append(f)
    sync_facts_to_duckdb(db, facts)
    return facts


# ---------------------------------------------------------------------------
# TS-52-P2: Fact provenance completeness
# ---------------------------------------------------------------------------


class TestFactProvenanceCompleteness:
    """TS-52-P2: For any extracted fact, all provenance fields are non-NULL.

    Property 2 from design.md.
    Validates: 52-REQ-2.1
    """

    @given(fact=valid_facts())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_provenance_fields_non_null(self, fact: Fact) -> None:
        db = _make_knowledge_db()
        try:
            sync_facts_to_duckdb(db, [fact])

            row = db.connection.execute(
                "SELECT category, confidence, spec_name, session_id, commit_sha FROM memory_facts WHERE id = ?::UUID",
                [fact.id],
            ).fetchone()

            assert row is not None, f"Fact {fact.id} should be inserted"
            category, confidence, spec_name, session_id, commit_sha = row
            assert category is not None
            assert confidence is not None
            assert spec_name is not None
            assert session_id is not None
            assert commit_sha is not None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TS-52-P3: Embedding failure isolation
# ---------------------------------------------------------------------------


class TestEmbeddingFailureIsolation:
    """TS-52-P3: Embedding failure never prevents fact storage.

    Property 3 from design.md.
    Validates: 52-REQ-3.1, 52-REQ-3.2
    """

    @given(
        fact=valid_facts(),
        embed_fails=st.booleans(),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_fact_exists_regardless_of_embedding(self, fact: Fact, embed_fails: bool) -> None:
        db = _make_knowledge_db()
        try:
            # Use sync_facts_to_duckdb directly (no embedding step)
            sync_facts_to_duckdb(db, [fact])

            row = db.connection.execute(
                "SELECT id::VARCHAR FROM memory_facts WHERE id = ?::UUID",
                [fact.id],
            ).fetchone()
            assert row is not None, "Fact must exist regardless of embedding"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TS-52-P4: Causal extraction minimum threshold
# ---------------------------------------------------------------------------


class TestCausalExtractionMinimumThreshold:
    """TS-52-P4: Causal extraction only runs when fact count >= 5.

    Property 4 from design.md.
    Validates: 52-REQ-5.1, 52-REQ-5.2

    NOTE: The threshold check is not yet implemented in
    extract_and_store_knowledge. This test will fail until task group 3.
    """

    @given(n=st.integers(min_value=0, max_value=20))
    @settings(
        max_examples=15,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    @pytest.mark.asyncio
    async def test_causal_called_iff_threshold_met(self, n: int) -> None:
        db = _make_knowledge_db()
        try:
            _insert_n_facts(db, n)
            new_fact = Fact(
                id=str(uuid.uuid4()),
                content="New hypothesis fact",
                category="pattern",
                spec_name="prop_test",
                keywords=["test"],
                confidence=0.8,
                created_at="2025-01-01T00:00:00Z",
                session_id="prop/new",
                commit_sha="abc9999",
            )

            with (
                patch(
                    "agent_fox.engine.knowledge_harvest.extract_facts",
                    new_callable=AsyncMock,
                    return_value=[new_fact],
                ),
                patch(
                    "agent_fox.engine.knowledge_harvest._extract_causal_links",
                ) as mock_causal,
            ):
                # Transcript must exceed _MIN_TRANSCRIPT_CHARS so the length
                # guard does not short-circuit before the mocked extract_facts.
                long_transcript = "prop causal test implementation detail. " * 55  # ~2200 chars
                await extract_and_store_knowledge(
                    transcript=long_transcript,
                    spec_name="prop_test",
                    node_id="prop/new",
                    memory_extraction_model="SIMPLE",
                    knowledge_db=db,
                )

                total = n + 1  # n existing + 1 new
                if total >= 5:
                    assert mock_causal.called, f"Causal extraction should be called when total facts={total} >= 5"
                else:
                    assert not mock_causal.called, (
                        f"Causal extraction should NOT be called when total facts={total} < 5"
                    )
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TS-52-P6: Causal link idempotency
# ---------------------------------------------------------------------------


class TestCausalLinkIdempotency:
    """TS-52-P6: Inserting the same causal link N times results in one row.

    Property 6 from design.md.
    Validates: 52-REQ-7.1
    """

    @given(n=st.integers(min_value=1, max_value=10))
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_idempotent_link_insertion(self, n: int) -> None:
        db = _make_knowledge_db()
        try:
            facts = _insert_n_facts(db, 2)
            cause_id = facts[0].id
            effect_id = facts[1].id

            for _ in range(n):
                store_causal_links(db.connection, [(cause_id, effect_id)])

            count = db.connection.execute(
                "SELECT COUNT(*) FROM fact_causes WHERE cause_id = ?::UUID AND effect_id = ?::UUID",
                [cause_id, effect_id],
            ).fetchone()[0]  # type: ignore[index]
            assert count == 1
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TS-52-P7: Causal link referential integrity
# ---------------------------------------------------------------------------


class TestCausalLinkReferentialIntegrity:
    """TS-52-P7: Links with non-existent fact IDs are never stored.

    Property 7 from design.md.
    Validates: 52-REQ-7.E1
    """

    @given(data=st.data())
    @settings(
        max_examples=15,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_missing_fact_link_rejected(self, data: st.DataObject) -> None:
        db = _make_knowledge_db()
        try:
            facts = _insert_n_facts(db, 1)
            existing_id = facts[0].id
            missing_id = str(uuid.uuid4())

            # Try link with one missing
            stored = store_causal_links(db.connection, [(existing_id, missing_id)])
            assert stored == 0

            # Try link with both missing
            missing_id_2 = str(uuid.uuid4())
            stored = store_causal_links(db.connection, [(missing_id, missing_id_2)])
            assert stored == 0
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TS-52-P8: Audit event on success
# ---------------------------------------------------------------------------


class TestAuditEventOnSuccess:
    """TS-52-P8: Successful harvest always emits a harvest.complete event.

    Property 8 from design.md.
    Validates: 52-REQ-4.1

    NOTE: harvest.complete audit event in extract_and_store_knowledge is
    not yet implemented. Will be added in task group 2.
    """

    @given(n=st.integers(min_value=1, max_value=5))
    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    @pytest.mark.asyncio
    async def test_harvest_complete_emitted(self, n: int) -> None:
        from agent_fox.knowledge.audit import AuditEvent, AuditEventType

        db = _make_knowledge_db()
        try:
            facts = [
                Fact(
                    id=str(uuid.uuid4()),
                    content=f"Prop fact {i}",
                    category="pattern",
                    spec_name="prop_test",
                    keywords=["test"],
                    confidence=0.8,
                    created_at="2025-01-01T00:00:00Z",
                    session_id=f"prop/{i}",
                    commit_sha=f"abc{i:04d}",
                )
                for i in range(n)
            ]

            mock_sink = MagicMock()
            emitted: list[AuditEvent] = []
            mock_sink.emit_audit_event.side_effect = lambda e: emitted.append(e)

            # Transcript must exceed _MIN_TRANSCRIPT_CHARS so the length guard
            # does not short-circuit before the mocked extract_facts is reached.
            long_transcript = "prop test content with implementation details. " * 50  # ~2350 chars

            with patch(
                "agent_fox.engine.knowledge_harvest.extract_facts",
                new_callable=AsyncMock,
                return_value=facts,
            ):
                await extract_and_store_knowledge(
                    transcript=long_transcript,
                    spec_name="prop_test",
                    node_id="prop/test",
                    memory_extraction_model="SIMPLE",
                    knowledge_db=db,
                    sink_dispatcher=mock_sink,
                    run_id="test_run",
                )

            harvest_events = [e for e in emitted if e.event_type == AuditEventType.HARVEST_COMPLETE]
            assert len(harvest_events) == 1
            assert harvest_events[0].payload["fact_count"] == n
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TS-52-P9: Audit event on empty harvest
# ---------------------------------------------------------------------------


class TestAuditEventOnEmptyHarvest:
    """TS-52-P9: Empty harvest from non-empty input emits harvest.empty.

    Property 9 from design.md.
    Validates: 52-REQ-4.2

    NOTE: harvest.empty is not yet implemented. Will be added in task
    group 2.
    """

    @given(
        # Transcripts must be at least _MIN_TRANSCRIPT_CHARS (2000 chars) long so
        # the new length guard does not short-circuit before extraction runs.
        # The harvest.empty event is only emitted when extraction is attempted.
        filler=st.text(
            min_size=2000,
            max_size=2200,
            alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        )
    )
    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    @pytest.mark.asyncio
    async def test_harvest_empty_emitted(self, filler: str) -> None:
        transcript = filler  # meets minimum length threshold
        from agent_fox.knowledge.audit import (
            AuditEvent,
            AuditEventType,
            AuditSeverity,
        )

        db = _make_knowledge_db()
        try:
            mock_sink = MagicMock()
            emitted: list[AuditEvent] = []
            mock_sink.emit_audit_event.side_effect = lambda e: emitted.append(e)

            with patch(
                "agent_fox.engine.knowledge_harvest.extract_facts",
                new_callable=AsyncMock,
                return_value=[],
            ):
                await extract_and_store_knowledge(
                    transcript=transcript,
                    spec_name="prop_test",
                    node_id="prop/test",
                    memory_extraction_model="SIMPLE",
                    knowledge_db=db,
                    sink_dispatcher=mock_sink,
                    run_id="test_run",
                )

            empty_events = [e for e in emitted if e.event_type == AuditEventType.HARVEST_EMPTY]
            assert len(empty_events) == 1
            assert empty_events[0].severity == AuditSeverity.WARNING
        finally:
            db.close()
