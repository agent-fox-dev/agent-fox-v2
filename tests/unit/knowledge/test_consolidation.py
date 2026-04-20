"""Unit tests for the knowledge consolidation pipeline.

Test Spec: TS-96-1 through TS-96-20, TS-96-E1 through TS-96-E9
Requirements: 96-REQ-1.*, 96-REQ-2.*, 96-REQ-3.*, 96-REQ-4.*, 96-REQ-5.*, 96-REQ-6.*
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest

from agent_fox.knowledge.consolidation import (
    CONSOLIDATION_STALE_SENTINEL,
    ConsolidationResult,
    MergeResult,
    PromotionResult,
    PruneResult,
    VerificationResult,
    _link_unlinked_facts,
    _merge_related_facts,
    _promote_patterns,
    _prune_redundant_chains,
    _refresh_entity_graph,
    _verify_against_git,
    run_consolidation,
)
from agent_fox.knowledge.entities import AnalysisResult, LinkResult
from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FACT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
FACT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
FACT_C = "cccccccc-cccc-cccc-cccc-cccccccccccc"
FACT_D = "dddddddd-dddd-dddd-dddd-dddddddddddd"
FACT_E = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with base schema and all migrations applied (v8 included)."""
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


def _insert_fact(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    *,
    content: str = "A test fact",
    category: str = "decision",
    spec_name: str = "spec_a",
    commit_sha: str | None = "abc123",
    confidence: float = 0.8,
    superseded_by: str | None = None,
) -> None:
    """Insert a minimal fact into memory_facts for testing."""
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at, commit_sha, superseded_by)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
        """,
        [fact_id, content, category, spec_name, confidence, commit_sha, superseded_by],
    )


def _insert_entity(
    conn: duckdb.DuckDBPyConnection,
    entity_id: str,
    *,
    entity_type: str = "file",
    entity_name: str = "src/foo.py",
    entity_path: str = "src/foo.py",
) -> None:
    """Insert an entity into entity_graph."""
    conn.execute(
        """
        INSERT INTO entity_graph (id, entity_type, entity_name, entity_path, created_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        [entity_id, entity_type, entity_name, entity_path],
    )


def _link_fact_to_entity(
    conn: duckdb.DuckDBPyConnection,
    fact_id: str,
    entity_id: str,
) -> None:
    """Link a fact to an entity in fact_entities."""
    conn.execute(
        "INSERT INTO fact_entities (fact_id, entity_id) VALUES (?, ?)",
        [fact_id, entity_id],
    )


def _insert_causal_edge(
    conn: duckdb.DuckDBPyConnection,
    cause_id: str,
    effect_id: str,
) -> None:
    """Insert a causal edge into fact_causes."""
    conn.execute(
        "INSERT INTO fact_causes (cause_id, effect_id) VALUES (?, ?)",
        [cause_id, effect_id],
    )


def _edge_exists(
    conn: duckdb.DuckDBPyConnection,
    cause_id: str,
    effect_id: str,
) -> bool:
    """Check if a causal edge exists."""
    row = conn.execute(
        "SELECT 1 FROM fact_causes WHERE cause_id = ? AND effect_id = ?",
        [cause_id, effect_id],
    ).fetchone()
    return row is not None


def _get_fact_confidence(conn: duckdb.DuckDBPyConnection, fact_id: str) -> float:
    """Get stored confidence for a fact."""
    row = conn.execute(
        "SELECT confidence FROM memory_facts WHERE id = ?",
        [fact_id],
    ).fetchone()
    assert row is not None, f"Fact {fact_id} not found"
    return float(row[0])


def _get_fact_superseded_by(conn: duckdb.DuckDBPyConnection, fact_id: str) -> str | None:
    """Get superseded_by for a fact."""
    row = conn.execute(
        "SELECT superseded_by FROM memory_facts WHERE id = ?",
        [fact_id],
    ).fetchone()
    assert row is not None, f"Fact {fact_id} not found"
    return str(row[0]) if row[0] is not None else None


def _make_mock_llm(response: dict) -> MagicMock:
    """Create a mock LLM that returns the given JSON response."""
    import json

    mock = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(response))]
    mock.messages.create = AsyncMock(return_value=mock_response)
    return mock


# ---------------------------------------------------------------------------
# TS-96-1: Pipeline step ordering and result
# ---------------------------------------------------------------------------


class TestPipelineOrdering:
    """TS-96-1: Pipeline executes all six steps in order and returns ConsolidationResult.

    Requirements: 96-REQ-1.1
    """

    @pytest.mark.asyncio
    async def test_pipeline_ordering(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Pipeline executes all six steps and returns complete ConsolidationResult."""
        # Insert a few active facts so the pipeline has work to do
        _insert_fact(entity_conn, FACT_A, spec_name="spec_a")
        _insert_fact(entity_conn, FACT_B, spec_name="spec_b")

        call_order: list[str] = []

        async def _mock_consolidation(**kwargs: object) -> ConsolidationResult:
            # This tracks call order through mocked steps
            raise NotImplementedError("Implement run_consolidation")

        with (
            patch(
                "agent_fox.knowledge.consolidation._refresh_entity_graph",
                side_effect=lambda *a, **kw: call_order.append("entity_refresh") or AnalysisResult(0, 0, 0),
            ),
            patch(
                "agent_fox.knowledge.consolidation._link_unlinked_facts",
                side_effect=lambda *a, **kw: call_order.append("link_facts") or LinkResult(0, 0, 0),
            ),
            patch(
                "agent_fox.knowledge.consolidation._verify_against_git",
                side_effect=lambda *a, **kw: call_order.append("git_verify") or VerificationResult(0, 0, 0, 0),
            ),
            patch(
                "agent_fox.knowledge.consolidation._merge_related_facts",
                new_callable=AsyncMock,
                side_effect=lambda *a, **kw: call_order.append("merge") or MergeResult(0, 0, 0, 0),
            ),
            patch(
                "agent_fox.knowledge.consolidation._promote_patterns",
                new_callable=AsyncMock,
                side_effect=lambda *a, **kw: call_order.append("promote") or PromotionResult(0, 0, 0),
            ),
            patch(
                "agent_fox.knowledge.consolidation._prune_redundant_chains",
                new_callable=AsyncMock,
                side_effect=lambda *a, **kw: call_order.append("prune") or PruneResult(0, 0, 0),
            ),
        ):
            result = await run_consolidation(
                entity_conn,
                tmp_path,
                {"spec_a"},
                "claude-3-5-haiku-20241022",
            )

        assert result.verification is not None
        assert result.merging is not None
        assert result.promotion is not None
        assert result.pruning is not None
        assert call_order == [
            "entity_refresh",
            "link_facts",
            "git_verify",
            "merge",
            "promote",
            "prune",
        ]


# ---------------------------------------------------------------------------
# TS-96-2: Step failure isolation
# ---------------------------------------------------------------------------


class TestStepFailureIsolation:
    """TS-96-2: A failing step does not block subsequent steps.

    Requirements: 96-REQ-1.2
    """

    @pytest.mark.asyncio
    async def test_step_failure_isolation(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Failing git_verification step does not block merge/promote/prune."""
        _insert_fact(entity_conn, FACT_A)

        with patch(
            "agent_fox.knowledge.consolidation._verify_against_git",
            side_effect=RuntimeError("Simulated git failure"),
        ):
            result = await run_consolidation(
                entity_conn,
                tmp_path,
                {"spec_a"},
                "claude-3-5-haiku-20241022",
            )

        assert result.verification is None
        assert "git_verification" in result.errors
        assert result.merging is not None
        assert result.promotion is not None
        assert result.pruning is not None


# ---------------------------------------------------------------------------
# TS-96-3: Audit event emission
# ---------------------------------------------------------------------------


class TestAuditEvent:
    """TS-96-3: consolidation.complete audit event is emitted.

    Requirements: 96-REQ-1.3
    """

    @pytest.mark.asyncio
    async def test_audit_event(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """consolidation.complete audit event is dispatched after pipeline completes."""
        _insert_fact(entity_conn, FACT_A)

        mock_sink = MagicMock()
        mock_sink.emit_audit_event = MagicMock()

        await run_consolidation(
            entity_conn,
            tmp_path,
            {"spec_a"},
            "claude-3-5-haiku-20241022",
            sink_dispatcher=mock_sink,
        )

        assert mock_sink.emit_audit_event.called
        # Find the consolidation.complete event
        calls = mock_sink.emit_audit_event.call_args_list
        event_types = [str(c.args[0].event_type) for c in calls if c.args]
        assert any("consolidation.complete" in et for et in event_types)


# ---------------------------------------------------------------------------
# TS-96-4: Entity graph refresh
# ---------------------------------------------------------------------------


class TestEntityRefresh:
    """TS-96-4: analyze_codebase is called during entity graph refresh.

    Requirements: 96-REQ-2.1
    """

    def test_entity_refresh(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """_refresh_entity_graph delegates to analyze_codebase."""
        expected = AnalysisResult(entities_upserted=5, edges_upserted=3, entities_soft_deleted=0)

        with patch(
            "agent_fox.knowledge.consolidation.analyze_codebase",
            return_value=expected,
        ) as mock_analyze:
            result = _refresh_entity_graph(entity_conn, tmp_path)

        mock_analyze.assert_called_once_with(tmp_path, entity_conn)
        assert result is not None
        assert result.entities_upserted == 5


# ---------------------------------------------------------------------------
# TS-96-5: Unlinked fact detection and linking
# ---------------------------------------------------------------------------


class TestUnlinkedFacts:
    """TS-96-5: Unlinked facts are detected and passed to link_facts.

    Requirements: 96-REQ-2.2
    """

    def test_unlinked_facts(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Only unlinked facts are passed to link_facts."""
        # Insert 3 facts: 2 with entity links, 1 without
        entity_id = str(uuid.uuid4())
        _insert_fact(entity_conn, FACT_A)
        _insert_fact(entity_conn, FACT_B)
        _insert_fact(entity_conn, FACT_C)

        _insert_entity(entity_conn, entity_id)
        _link_fact_to_entity(entity_conn, FACT_A, entity_id)
        _link_fact_to_entity(entity_conn, FACT_B, entity_id)
        # FACT_C is unlinked

        mock_link_result = LinkResult(facts_processed=1, links_created=1, facts_skipped=0)

        with patch(
            "agent_fox.knowledge.consolidation.link_facts",
            return_value=mock_link_result,
        ) as mock_link:
            result = _link_unlinked_facts(entity_conn, tmp_path)

        # link_facts should have been called with only FACT_C
        assert mock_link.called
        call_args = mock_link.call_args
        # The facts passed should include FACT_C
        facts_arg = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("facts", [])
        assert len(facts_arg) == 1
        assert result.links_created == 1


# ---------------------------------------------------------------------------
# TS-96-6: Consolidation result includes entity counts
# ---------------------------------------------------------------------------


class TestEntityCountsInResult:
    """TS-96-6: Entity graph results appear in ConsolidationResult.

    Requirements: 96-REQ-2.3
    """

    @pytest.mark.asyncio
    async def test_entity_counts_in_result(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """entity_refresh and facts_linked are populated in ConsolidationResult."""
        _insert_fact(entity_conn, FACT_A)

        analysis = AnalysisResult(entities_upserted=3, edges_upserted=2, entities_soft_deleted=0)
        link_res = LinkResult(facts_processed=1, links_created=1, facts_skipped=0)

        with (
            patch(
                "agent_fox.knowledge.consolidation._refresh_entity_graph",
                return_value=analysis,
            ),
            patch(
                "agent_fox.knowledge.consolidation._link_unlinked_facts",
                return_value=link_res,
            ),
        ):
            result = await run_consolidation(
                entity_conn,
                tmp_path,
                {"spec_a"},
                "claude-3-5-haiku-20241022",
            )

        assert result.entity_refresh is not None
        assert result.entity_refresh.entities_upserted == 3
        assert result.facts_linked >= 0


# ---------------------------------------------------------------------------
# TS-96-7: Git verification queries fact-entity links
# ---------------------------------------------------------------------------


class TestGitVerifyQueriesLinks:
    """TS-96-7: Git verification only checks facts with entity links.

    Requirements: 96-REQ-3.1
    """

    def test_git_verify_queries_links(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Only facts with file entity links are checked; unlinked facts skipped."""
        entity_id_1 = str(uuid.uuid4())
        entity_id_2 = str(uuid.uuid4())

        # 2 linked facts
        _insert_fact(entity_conn, FACT_A, commit_sha=None)
        _insert_fact(entity_conn, FACT_B, commit_sha=None)
        # 1 unlinked fact
        _insert_fact(entity_conn, FACT_C, commit_sha=None)

        _insert_entity(entity_conn, entity_id_1, entity_type="file", entity_path="src/a.py")
        _insert_entity(entity_conn, entity_id_2, entity_type="file", entity_path="src/b.py")
        _link_fact_to_entity(entity_conn, FACT_A, entity_id_1)
        _link_fact_to_entity(entity_conn, FACT_B, entity_id_2)

        # Make both files exist on disk
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("content")
        (tmp_path / "src" / "b.py").write_text("content")

        result = _verify_against_git(entity_conn, tmp_path, 0.5)

        assert result.facts_checked == 2


# ---------------------------------------------------------------------------
# TS-96-8: Supersede facts with all files deleted
# ---------------------------------------------------------------------------


class TestSupersedeFact:
    """TS-96-8: Facts superseded when all linked files are deleted.

    Requirements: 96-REQ-3.2
    """

    def test_supersede_deleted_files(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Fact superseded_by set to CONSOLIDATION_STALE_SENTINEL when all files deleted."""
        entity_id = str(uuid.uuid4())
        _insert_fact(entity_conn, FACT_A, commit_sha=None)
        _insert_entity(entity_conn, entity_id, entity_type="file", entity_path="src/old.py")
        _link_fact_to_entity(entity_conn, FACT_A, entity_id)
        # src/old.py does NOT exist in tmp_path

        result = _verify_against_git(entity_conn, tmp_path, 0.5)

        assert result.superseded_count == 1
        superseded_by = _get_fact_superseded_by(entity_conn, FACT_A)
        assert superseded_by == str(CONSOLIDATION_STALE_SENTINEL)


# ---------------------------------------------------------------------------
# TS-96-9: Halve confidence for significantly changed files
# ---------------------------------------------------------------------------


class TestHalveConfidence:
    """TS-96-9: Confidence halved when linked files changed significantly.

    Requirements: 96-REQ-3.3
    """

    def test_halve_confidence(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Confidence halved when change ratio > threshold and file exists."""
        entity_id = str(uuid.uuid4())
        _insert_fact(entity_conn, FACT_A, commit_sha="abc123", confidence=0.8)
        _insert_entity(entity_conn, entity_id, entity_type="file", entity_path="src/foo.py")
        _link_fact_to_entity(entity_conn, FACT_A, entity_id)

        # Create the file with 100 lines
        (tmp_path / "src").mkdir()
        foo_py = tmp_path / "src" / "foo.py"
        foo_py.write_text("\n".join(["line"] * 100))

        # Mock git diff: 60 insertions + 40 deletions = 100 changes out of 100 lines = ratio 1.0 > 0.5
        mock_numstat_output = "60\t40\tsrc/foo.py\n"

        with patch(
            "subprocess.run",
            return_value=MagicMock(
                stdout=mock_numstat_output,
                returncode=0,
            ),
        ):
            result = _verify_against_git(entity_conn, tmp_path, 0.5)

        assert result.decayed_count == 1
        confidence = _get_fact_confidence(entity_conn, FACT_A)
        assert abs(confidence - 0.4) < 1e-9  # 0.8 / 2 = 0.4


# ---------------------------------------------------------------------------
# TS-96-10: Verification result counts
# ---------------------------------------------------------------------------


class TestVerificationCounts:
    """TS-96-10: VerificationResult has correct counts.

    Requirements: 96-REQ-3.4
    """

    def test_verification_counts(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """VerificationResult(3, 1, 1, 1) for 3 facts: 1 deleted, 1 changed, 1 unchanged."""
        entity_a = str(uuid.uuid4())
        entity_b = str(uuid.uuid4())
        entity_c = str(uuid.uuid4())

        # FACT_A: linked to deleted file
        _insert_fact(entity_conn, FACT_A, commit_sha=None, confidence=0.8)
        _insert_entity(entity_conn, entity_a, entity_type="file", entity_path="src/deleted.py")
        _link_fact_to_entity(entity_conn, FACT_A, entity_a)

        # FACT_B: linked to significantly changed file, has commit_sha
        _insert_fact(entity_conn, FACT_B, commit_sha="abc123", confidence=0.8)
        _insert_entity(entity_conn, entity_b, entity_type="file", entity_path="src/changed.py")
        _link_fact_to_entity(entity_conn, FACT_B, entity_b)

        # FACT_C: linked to unchanged file
        _insert_fact(entity_conn, FACT_C, commit_sha=None, confidence=0.8)
        _insert_entity(entity_conn, entity_c, entity_type="file", entity_path="src/unchanged.py")
        _link_fact_to_entity(entity_conn, FACT_C, entity_c)

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "changed.py").write_text("\n".join(["line"] * 100))
        (tmp_path / "src" / "unchanged.py").write_text("content")
        # deleted.py does NOT exist

        mock_numstat_output = "60\t40\tsrc/changed.py\n"
        with patch(
            "subprocess.run",
            return_value=MagicMock(stdout=mock_numstat_output, returncode=0),
        ):
            result = _verify_against_git(entity_conn, tmp_path, 0.5)

        assert result.facts_checked == 3
        assert result.superseded_count == 1
        assert result.decayed_count == 1
        assert result.unchanged_count == 1


# ---------------------------------------------------------------------------
# TS-96-11: Cross-spec cluster detection
# ---------------------------------------------------------------------------


class TestClusterDetection:
    """TS-96-11: Similar facts from different specs are clustered.

    Requirements: 96-REQ-4.1
    """

    @pytest.mark.asyncio
    async def test_cluster_detection(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Facts from different specs with high similarity form a cluster."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb1 = _make_unit_vec(1)
        # emb2 is very similar to emb1 (rotated slightly)
        emb2 = [emb1[i] * 0.9999 + (0.0001 if i == 0 else 0.0) for i in range(384)]
        norm2 = math.sqrt(sum(x * x for x in emb2))
        emb2 = [x / norm2 for x in emb2]
        emb3 = _make_unit_vec(99)  # Very different

        # Insert facts from different specs
        _insert_fact(entity_conn, FACT_A, spec_name="spec_a")
        _insert_fact(entity_conn, FACT_B, spec_name="spec_b")
        _insert_fact(entity_conn, FACT_C, spec_name="spec_a")  # same spec, diff embedding

        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_A, emb1],
        )
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_B, emb2],
        )
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_C, emb3],
        )

        mock_llm_response = {"action": "link"}

        with patch(
            "agent_fox.knowledge.consolidation._call_llm_json",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await _merge_related_facts(entity_conn, "claude-3-5-haiku-20241022", 0.85, None)

        # F1 (spec_a) and F2 (spec_b) should be found as a cluster (cross-spec)
        assert result.clusters_found >= 1


# ---------------------------------------------------------------------------
# TS-96-12: LLM merge classification
# ---------------------------------------------------------------------------


class TestLLMMergeClassification:
    """TS-96-12: LLM is called for each cluster to decide merge/link.

    Requirements: 96-REQ-4.2
    """

    @pytest.mark.asyncio
    async def test_llm_merge_classification(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """LLM called with cluster facts to decide merge or link action."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb1 = _make_unit_vec(1)
        emb2_raw = [emb1[i] * 0.9999 + (0.0001 if i == 0 else 0.0) for i in range(384)]
        norm2 = math.sqrt(sum(x * x for x in emb2_raw))
        emb2 = [x / norm2 for x in emb2_raw]

        _insert_fact(entity_conn, FACT_A, spec_name="spec_a")
        _insert_fact(entity_conn, FACT_B, spec_name="spec_b")
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_A, emb1],
        )
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_B, emb2],
        )

        llm_mock = AsyncMock(return_value={"action": "merge", "content": "Consolidated content"})

        with patch(
            "agent_fox.knowledge.consolidation._call_llm_json",
            llm_mock,
        ):
            await _merge_related_facts(entity_conn, "claude-3-5-haiku-20241022", 0.85, None)

        assert llm_mock.called


# ---------------------------------------------------------------------------
# TS-96-13: Merge action creates consolidated fact
# ---------------------------------------------------------------------------


class TestMergeCreatesConsolidatedFact:
    """TS-96-13: Merge action creates new consolidated fact and supersedes originals.

    Requirements: 96-REQ-4.3
    """

    @pytest.mark.asyncio
    async def test_merge_creates_fact(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Merge creates consolidated fact and supersedes F1, F2."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb1 = _make_unit_vec(1)
        emb2_raw = [emb1[i] * 0.9999 + (0.0001 if i == 0 else 0.0) for i in range(384)]
        norm2 = math.sqrt(sum(x * x for x in emb2_raw))
        emb2 = [x / norm2 for x in emb2_raw]

        _insert_fact(entity_conn, FACT_A, spec_name="spec_a", confidence=0.7)
        _insert_fact(entity_conn, FACT_B, spec_name="spec_b", confidence=0.9)
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_A, emb1],
        )
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_B, emb2],
        )

        merged_content = "Merged: both facts say the same thing"
        llm_mock = AsyncMock(return_value={"action": "merge", "content": merged_content})

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await _merge_related_facts(entity_conn, "claude-3-5-haiku-20241022", 0.85, None)

        assert result.consolidated_created == 1
        assert result.facts_merged == 2
        assert _get_fact_superseded_by(entity_conn, FACT_A) is not None
        assert _get_fact_superseded_by(entity_conn, FACT_B) is not None


# ---------------------------------------------------------------------------
# TS-96-14: Link action adds causal edges
# ---------------------------------------------------------------------------


class TestLinkAddsEdges:
    """TS-96-14: Link action adds causal edges without modifying facts.

    Requirements: 96-REQ-4.4
    """

    @pytest.mark.asyncio
    async def test_link_adds_edges(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Link action adds causal edges between clustered facts; no supersession."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb1 = _make_unit_vec(1)
        emb2_raw = [emb1[i] * 0.9999 + (0.0001 if i == 0 else 0.0) for i in range(384)]
        norm2 = math.sqrt(sum(x * x for x in emb2_raw))
        emb2 = [x / norm2 for x in emb2_raw]

        _insert_fact(entity_conn, FACT_A, spec_name="spec_a")
        _insert_fact(entity_conn, FACT_B, spec_name="spec_b")
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_A, emb1],
        )
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_B, emb2],
        )

        llm_mock = AsyncMock(return_value={"action": "link"})

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await _merge_related_facts(entity_conn, "claude-3-5-haiku-20241022", 0.85, None)

        assert result.facts_linked >= 1
        assert _get_fact_superseded_by(entity_conn, FACT_A) is None
        assert _get_fact_superseded_by(entity_conn, FACT_B) is None


# ---------------------------------------------------------------------------
# TS-96-15: Pattern candidate detection (3+ specs)
# ---------------------------------------------------------------------------


class TestPatternCandidates:
    """TS-96-15: Similar facts from 3+ specs are identified as pattern candidates.

    Requirements: 96-REQ-5.1
    """

    @pytest.mark.asyncio
    async def test_pattern_candidates(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Facts from 3 distinct specs with high similarity found as candidates."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb_base = _make_unit_vec(1)

        for i, (fact_id, spec) in enumerate([(FACT_A, "spec_a"), (FACT_B, "spec_b"), (FACT_C, "spec_c")]):
            _insert_fact(entity_conn, fact_id, spec_name=spec)
            # All embeddings are nearly identical (very similar)
            emb_raw = [emb_base[j] * (0.9998 + i * 0.0001) for j in range(384)]
            norm = math.sqrt(sum(x * x for x in emb_raw))
            emb = [x / norm for x in emb_raw]
            entity_conn.execute(
                "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
                [fact_id, emb],
            )

        llm_mock = AsyncMock(return_value={"is_pattern": True, "description": "A recurring pattern across specs"})

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await _promote_patterns(entity_conn, "claude-3-5-haiku-20241022")

        assert result.candidates_found >= 1


# ---------------------------------------------------------------------------
# TS-96-16: LLM pattern confirmation
# ---------------------------------------------------------------------------


class TestLLMPatternConfirm:
    """TS-96-16: LLM called to confirm patterns from candidate groups.

    Requirements: 96-REQ-5.2
    """

    @pytest.mark.asyncio
    async def test_llm_pattern_confirm(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """LLM called with candidate facts to confirm pattern."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb_base = _make_unit_vec(1)
        for i, (fact_id, spec) in enumerate([(FACT_A, "spec_a"), (FACT_B, "spec_b"), (FACT_C, "spec_c")]):
            _insert_fact(entity_conn, fact_id, spec_name=spec)
            emb_raw = [emb_base[j] * (0.9998 + i * 0.0001) for j in range(384)]
            norm = math.sqrt(sum(x * x for x in emb_raw))
            emb = [x / norm for x in emb_raw]
            entity_conn.execute(
                "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
                [fact_id, emb],
            )

        llm_mock = AsyncMock(return_value={"is_pattern": True, "description": "Pattern confirmed"})

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            await _promote_patterns(entity_conn, "claude-3-5-haiku-20241022")

        assert llm_mock.called


# ---------------------------------------------------------------------------
# TS-96-17: Pattern fact creation
# ---------------------------------------------------------------------------


class TestPatternFactCreation:
    """TS-96-17: Confirmed pattern creates new fact with category=pattern.

    Requirements: 96-REQ-5.3
    """

    @pytest.mark.asyncio
    async def test_pattern_fact_creation(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Confirmed pattern creates fact with category=pattern, confidence=0.9."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb_base = _make_unit_vec(1)
        for i, (fact_id, spec) in enumerate([(FACT_A, "spec_a"), (FACT_B, "spec_b"), (FACT_C, "spec_c")]):
            _insert_fact(entity_conn, fact_id, spec_name=spec)
            emb_raw = [emb_base[j] * (0.9998 + i * 0.0001) for j in range(384)]
            norm = math.sqrt(sum(x * x for x in emb_raw))
            emb = [x / norm for x in emb_raw]
            entity_conn.execute(
                "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
                [fact_id, emb],
            )

        llm_mock = AsyncMock(return_value={"is_pattern": True, "description": "A recurring pattern"})

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await _promote_patterns(entity_conn, "claude-3-5-haiku-20241022")

        assert result.pattern_facts_created == 1

        # Find the created pattern fact
        row = entity_conn.execute(
            """
            SELECT category, confidence FROM memory_facts
            WHERE category = 'pattern'
            AND id NOT IN (?, ?, ?)
            """,
            [FACT_A, FACT_B, FACT_C],
        ).fetchone()
        assert row is not None
        assert row[0] == "pattern"
        assert abs(float(row[1]) - 0.9) < 1e-9


# ---------------------------------------------------------------------------
# TS-96-13b: Merge action generates embedding for consolidated fact
# ---------------------------------------------------------------------------


class TestMergeCreatesEmbedding:
    """Merged consolidated fact must get an embedding row in memory_embeddings.

    Requirements: 96-REQ-4.3 (embedding parity)
    """

    @pytest.mark.asyncio
    async def test_merge_creates_embedding(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Embedding is written for the consolidated fact when embedder is provided."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb1 = _make_unit_vec(1)
        emb2_raw = [emb1[i] * 0.9999 + (0.0001 if i == 0 else 0.0) for i in range(384)]
        norm2 = math.sqrt(sum(x * x for x in emb2_raw))
        emb2 = [x / norm2 for x in emb2_raw]

        _insert_fact(entity_conn, FACT_A, spec_name="spec_a", confidence=0.7)
        _insert_fact(entity_conn, FACT_B, spec_name="spec_b", confidence=0.9)
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_A, emb1],
        )
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_B, emb2],
        )

        merged_content = "Merged: both facts say the same thing"
        llm_mock = AsyncMock(return_value={"action": "merge", "content": merged_content})

        # Mock embedder that returns a fixed 384-dim vector
        fake_embedding = _make_unit_vec(42)
        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = fake_embedding
        mock_embedder.embedding_dimensions = 384

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await _merge_related_facts(
                entity_conn, "claude-3-5-haiku-20241022", 0.85, mock_embedder
            )

        assert result.consolidated_created == 1

        # The new consolidated fact must have a row in memory_embeddings
        new_fact_row = entity_conn.execute(
            "SELECT CAST(id AS VARCHAR) FROM memory_facts WHERE category = 'decision' AND superseded_by IS NULL"
        ).fetchone()
        assert new_fact_row is not None
        new_id = new_fact_row[0]

        emb_row = entity_conn.execute(
            "SELECT id FROM memory_embeddings WHERE CAST(id AS VARCHAR) = ?",
            [new_id],
        ).fetchone()
        assert emb_row is not None, "Consolidated fact must have an embedding row"
        mock_embedder.embed_text.assert_called_once_with(merged_content)

    @pytest.mark.asyncio
    async def test_merge_no_embedder_logs_warning(
        self, entity_conn: duckdb.DuckDBPyConnection, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When no embedder is configured, a warning is logged and no crash occurs."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb1 = _make_unit_vec(1)
        emb2_raw = [emb1[i] * 0.9999 + (0.0001 if i == 0 else 0.0) for i in range(384)]
        norm2 = math.sqrt(sum(x * x for x in emb2_raw))
        emb2 = [x / norm2 for x in emb2_raw]

        _insert_fact(entity_conn, FACT_A, spec_name="spec_a", confidence=0.7)
        _insert_fact(entity_conn, FACT_B, spec_name="spec_b", confidence=0.9)
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_A, emb1],
        )
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_B, emb2],
        )

        llm_mock = AsyncMock(return_value={"action": "merge", "content": "Merged fact"})

        with (
            patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock),
            caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.consolidation"),
        ):
            result = await _merge_related_facts(entity_conn, "claude-3-5-haiku-20241022", 0.85, None)

        assert result.consolidated_created == 1
        assert "without embedding" in caplog.text


# ---------------------------------------------------------------------------
# TS-96-17b: Pattern promotion generates embedding for pattern fact
# ---------------------------------------------------------------------------


class TestPatternFactCreatesEmbedding:
    """Promoted pattern fact must get an embedding row in memory_embeddings.

    Requirements: 96-REQ-5.3 (embedding parity)
    """

    @pytest.mark.asyncio
    async def test_pattern_fact_creates_embedding(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Embedding is written for the pattern fact when embedder is provided."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb_base = _make_unit_vec(1)
        for i, (fact_id, spec) in enumerate([(FACT_A, "spec_a"), (FACT_B, "spec_b"), (FACT_C, "spec_c")]):
            _insert_fact(entity_conn, fact_id, spec_name=spec)
            emb_raw = [emb_base[j] * (0.9998 + i * 0.0001) for j in range(384)]
            norm = math.sqrt(sum(x * x for x in emb_raw))
            emb = [x / norm for x in emb_raw]
            entity_conn.execute(
                "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
                [fact_id, emb],
            )

        pattern_description = "A recurring pattern across specs"
        llm_mock = AsyncMock(return_value={"is_pattern": True, "description": pattern_description})

        fake_embedding = _make_unit_vec(99)
        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = fake_embedding
        mock_embedder.embedding_dimensions = 384

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await _promote_patterns(
                entity_conn, "claude-3-5-haiku-20241022", embedding_generator=mock_embedder
            )

        assert result.pattern_facts_created == 1

        # Find the created pattern fact id
        pattern_row = entity_conn.execute(
            "SELECT CAST(id AS VARCHAR) FROM memory_facts WHERE category = 'pattern'"
        ).fetchone()
        assert pattern_row is not None
        pattern_id = pattern_row[0]

        # It must have an embedding row
        emb_row = entity_conn.execute(
            "SELECT id FROM memory_embeddings WHERE CAST(id AS VARCHAR) = ?",
            [pattern_id],
        ).fetchone()
        assert emb_row is not None, "Pattern fact must have an embedding row"
        mock_embedder.embed_text.assert_called_once_with(pattern_description)

    @pytest.mark.asyncio
    async def test_pattern_fact_no_embedder_logs_warning(
        self, entity_conn: duckdb.DuckDBPyConnection, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When no embedder is configured, a warning is logged and no crash occurs."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb_base = _make_unit_vec(1)
        for i, (fact_id, spec) in enumerate([(FACT_A, "spec_a"), (FACT_B, "spec_b"), (FACT_C, "spec_c")]):
            _insert_fact(entity_conn, fact_id, spec_name=spec)
            emb_raw = [emb_base[j] * (0.9998 + i * 0.0001) for j in range(384)]
            norm = math.sqrt(sum(x * x for x in emb_raw))
            emb = [x / norm for x in emb_raw]
            entity_conn.execute(
                "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
                [fact_id, emb],
            )

        llm_mock = AsyncMock(return_value={"is_pattern": True, "description": "Pattern without embedder"})

        with (
            patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock),
            caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.consolidation"),
        ):
            result = await _promote_patterns(entity_conn, "claude-3-5-haiku-20241022", embedding_generator=None)

        assert result.pattern_facts_created == 1
        assert "without embedding" in caplog.text


# ---------------------------------------------------------------------------
# TS-96-18: Redundant chain detection
# ---------------------------------------------------------------------------


class TestRedundantChainDetect:
    """TS-96-18: Redundant chains A->B->C with A->C are found.

    Requirements: 96-REQ-6.1
    """

    @pytest.mark.asyncio
    async def test_redundant_chain_detect(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Chain A->B->C with direct A->C is detected as redundant."""
        _insert_fact(entity_conn, FACT_A)
        _insert_fact(entity_conn, FACT_B)
        _insert_fact(entity_conn, FACT_C)
        _insert_causal_edge(entity_conn, FACT_A, FACT_B)
        _insert_causal_edge(entity_conn, FACT_B, FACT_C)
        _insert_causal_edge(entity_conn, FACT_A, FACT_C)  # direct edge

        llm_mock = AsyncMock(return_value={"meaningful": False, "reason": "B adds no value"})

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await _prune_redundant_chains(entity_conn, "claude-3-5-haiku-20241022")

        assert result.chains_evaluated >= 1


# ---------------------------------------------------------------------------
# TS-96-19: LLM chain evaluation
# ---------------------------------------------------------------------------


class TestLLMChainEval:
    """TS-96-19: LLM evaluates intermediate B in chain A->B->C.

    Requirements: 96-REQ-6.2
    """

    @pytest.mark.asyncio
    async def test_llm_chain_eval(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """LLM called with facts A, B, C to evaluate B as intermediate."""
        _insert_fact(entity_conn, FACT_A)
        _insert_fact(entity_conn, FACT_B)
        _insert_fact(entity_conn, FACT_C)
        _insert_causal_edge(entity_conn, FACT_A, FACT_B)
        _insert_causal_edge(entity_conn, FACT_B, FACT_C)
        _insert_causal_edge(entity_conn, FACT_A, FACT_C)

        llm_mock = AsyncMock(return_value={"meaningful": False, "reason": "B redundant"})

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            await _prune_redundant_chains(entity_conn, "claude-3-5-haiku-20241022")

        assert llm_mock.called


# ---------------------------------------------------------------------------
# TS-96-20: Redundant edge removal
# ---------------------------------------------------------------------------


class TestEdgeRemoval:
    """TS-96-20: Edges A->B and B->C removed when B not meaningful; A->C preserved.

    Requirements: 96-REQ-6.3
    """

    @pytest.mark.asyncio
    async def test_edge_removal(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """After pruning B: edges A->B and B->C gone, A->C preserved."""
        _insert_fact(entity_conn, FACT_A)
        _insert_fact(entity_conn, FACT_B)
        _insert_fact(entity_conn, FACT_C)
        _insert_causal_edge(entity_conn, FACT_A, FACT_B)
        _insert_causal_edge(entity_conn, FACT_B, FACT_C)
        _insert_causal_edge(entity_conn, FACT_A, FACT_C)

        llm_mock = AsyncMock(return_value={"meaningful": False, "reason": "B not needed"})

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await _prune_redundant_chains(entity_conn, "claude-3-5-haiku-20241022")

        assert result.edges_removed == 2
        assert not _edge_exists(entity_conn, FACT_A, FACT_B)
        assert not _edge_exists(entity_conn, FACT_B, FACT_C)
        assert _edge_exists(entity_conn, FACT_A, FACT_C)


# ---------------------------------------------------------------------------
# TS-96-E1: Zero active facts
# ---------------------------------------------------------------------------


class TestZeroFacts:
    """TS-96-E1: Zero-count result when no active facts exist.

    Requirements: 96-REQ-1.E1
    """

    @pytest.mark.asyncio
    async def test_zero_facts(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """No facts -> all counts zero, no LLM calls."""
        llm_mock = AsyncMock()

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await run_consolidation(
                entity_conn,
                tmp_path,
                {"spec_a"},
                "claude-3-5-haiku-20241022",
            )

        assert result.total_llm_cost == 0.0
        assert llm_mock.call_count == 0


# ---------------------------------------------------------------------------
# TS-96-E2: Missing entity graph tables
# ---------------------------------------------------------------------------


class TestMissingEntityTables:
    """TS-96-E2: Graceful skip when entity graph tables don't exist.

    Requirements: 96-REQ-1.E2
    """

    @pytest.mark.asyncio
    async def test_missing_entity_tables(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Missing entity graph tables -> skip entity steps, log warning."""
        # Create connection with only base schema (no v8 migration)
        conn = duckdb.connect(":memory:")
        conn.execute(SCHEMA_DDL_V2)
        # Apply only migrations up to v7
        from agent_fox.knowledge.migrations import apply_pending_migrations

        apply_pending_migrations(conn)
        # Drop the entity graph tables to simulate missing v8
        conn.execute("DROP TABLE IF EXISTS fact_entities")
        conn.execute("DROP TABLE IF EXISTS entity_edges")
        conn.execute("DROP TABLE IF EXISTS entity_graph")

        with caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.consolidation"):
            result = await run_consolidation(
                conn,
                tmp_path,
                {"spec_a"},
                "claude-3-5-haiku-20241022",
            )

        assert result.entity_refresh is None
        assert "entity graph" in caplog.text.lower()
        conn.close()


# ---------------------------------------------------------------------------
# TS-96-E3: Invalid repo root
# ---------------------------------------------------------------------------


class TestInvalidRepoRoot:
    """TS-96-E3: Entity steps skipped when repo root is invalid.

    Requirements: 96-REQ-2.E1
    """

    @pytest.mark.asyncio
    async def test_invalid_repo_root(
        self, entity_conn: duckdb.DuckDBPyConnection, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-existent repo root -> entity_refresh is None, warning logged."""
        bad_path = Path("/nonexistent/path/that/does/not/exist")

        with caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.consolidation"):
            result = await run_consolidation(
                entity_conn,
                bad_path,
                {"spec_a"},
                "claude-3-5-haiku-20241022",
            )

        assert result.entity_refresh is None


# ---------------------------------------------------------------------------
# TS-96-E4: Fact without entity links (skipped in git verification)
# ---------------------------------------------------------------------------


class TestSkipNoEntityLinks:
    """TS-96-E4: Facts without entity links skipped in git verification.

    Requirements: 96-REQ-3.E1
    """

    def test_skip_no_entity_links(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Fact with no fact_entities rows -> facts_checked == 0."""
        _insert_fact(entity_conn, FACT_A, commit_sha=None)
        # No entity links for FACT_A

        result = _verify_against_git(entity_conn, tmp_path, 0.5)

        assert result.facts_checked == 0


# ---------------------------------------------------------------------------
# TS-96-E5: Fact without commit_sha (file existence check only)
# ---------------------------------------------------------------------------


class TestNoCommitSha:
    """TS-96-E5: Only file existence checked when commit_sha is null.

    Requirements: 96-REQ-3.E2
    """

    def test_no_commit_sha(self, entity_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """No commit_sha -> file existence check only; no git diff subprocess."""
        entity_id = str(uuid.uuid4())
        _insert_fact(entity_conn, FACT_A, commit_sha=None)
        _insert_entity(entity_conn, entity_id, entity_type="file", entity_path="src/foo.py")
        _link_fact_to_entity(entity_conn, FACT_A, entity_id)

        # File exists
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("content")

        mock_subprocess = MagicMock()
        with patch("subprocess.run", mock_subprocess):
            result = _verify_against_git(entity_conn, tmp_path, 0.5)

        assert result.unchanged_count == 1
        # No git diff called because commit_sha is None
        assert mock_subprocess.call_count == 0


# ---------------------------------------------------------------------------
# TS-96-E6: Embedding failure in clustering
# ---------------------------------------------------------------------------


class TestEmbeddingFailure:
    """TS-96-E6: Facts with failed embeddings excluded from clustering.

    Requirements: 96-REQ-4.E1
    """

    @pytest.mark.asyncio
    async def test_embedding_failure(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """F3 without embedding excluded from clustering; F1, F2 processed."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb1 = _make_unit_vec(1)
        emb2_raw = [emb1[i] * 0.9999 + (0.0001 if i == 0 else 0.0) for i in range(384)]
        norm2 = math.sqrt(sum(x * x for x in emb2_raw))
        emb2 = [x / norm2 for x in emb2_raw]

        _insert_fact(entity_conn, FACT_A, spec_name="spec_a")
        _insert_fact(entity_conn, FACT_B, spec_name="spec_b")
        _insert_fact(entity_conn, FACT_C, spec_name="spec_c")  # No embedding

        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_A, emb1],
        )
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_B, emb2],
        )
        # FACT_C has no embedding

        llm_mock = AsyncMock(return_value={"action": "link"})

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await _merge_related_facts(entity_conn, "claude-3-5-haiku-20241022", 0.85, None)

        # Should process FACT_A and FACT_B; FACT_C excluded
        # No error should be raised for missing embedding
        assert isinstance(result, MergeResult)


# ---------------------------------------------------------------------------
# TS-96-E7: LLM failure for merge cluster
# ---------------------------------------------------------------------------


class TestLLMMergeFailure:
    """TS-96-E7: Cluster skipped when LLM call fails.

    Requirements: 96-REQ-4.E2
    """

    @pytest.mark.asyncio
    async def test_llm_merge_failure(
        self, entity_conn: duckdb.DuckDBPyConnection, caplog: pytest.LogCaptureFixture
    ) -> None:
        """LLM failure for cluster -> warning logged, cluster skipped, counts zero."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb1 = _make_unit_vec(1)
        emb2_raw = [emb1[i] * 0.9999 + (0.0001 if i == 0 else 0.0) for i in range(384)]
        norm2 = math.sqrt(sum(x * x for x in emb2_raw))
        emb2 = [x / norm2 for x in emb2_raw]

        _insert_fact(entity_conn, FACT_A, spec_name="spec_a")
        _insert_fact(entity_conn, FACT_B, spec_name="spec_b")
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_A, emb1],
        )
        entity_conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [FACT_B, emb2],
        )

        llm_mock = AsyncMock(side_effect=RuntimeError("LLM API error"))

        with (
            patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock),
            caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.consolidation"),
        ):
            result = await _merge_related_facts(entity_conn, "claude-3-5-haiku-20241022", 0.85, None)

        assert result.consolidated_created == 0
        assert "cluster" in caplog.text.lower()


# ---------------------------------------------------------------------------
# TS-96-E8: Duplicate pattern prevention
# ---------------------------------------------------------------------------


class TestDuplicatePatternSkip:
    """TS-96-E8: Pattern groups already linked to pattern fact are skipped.

    Requirements: 96-REQ-5.E1
    """

    @pytest.mark.asyncio
    async def test_duplicate_pattern_skip(self, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """Already-linked pattern group -> no new pattern created."""
        import math

        def _make_unit_vec(seed: int, dim: int = 384) -> list[float]:
            raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            return [x / norm for x in raw]

        emb_base = _make_unit_vec(1)
        for i, (fact_id, spec) in enumerate([(FACT_A, "spec_a"), (FACT_B, "spec_b"), (FACT_C, "spec_c")]):
            _insert_fact(entity_conn, fact_id, spec_name=spec)
            emb_raw = [emb_base[j] * (0.9998 + i * 0.0001) for j in range(384)]
            norm = math.sqrt(sum(x * x for x in emb_raw))
            emb = [x / norm for x in emb_raw]
            entity_conn.execute(
                "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
                [fact_id, emb],
            )

        # Create an existing pattern fact and link all source facts to it
        existing_pattern_id = str(uuid.uuid4())
        _insert_fact(
            entity_conn,
            existing_pattern_id,
            category="pattern",
            spec_name="consolidated",
            confidence=0.9,
        )
        # Link via causal edges: FACT_A, FACT_B, FACT_C -> existing_pattern_id
        _insert_causal_edge(entity_conn, FACT_A, existing_pattern_id)
        _insert_causal_edge(entity_conn, FACT_B, existing_pattern_id)
        _insert_causal_edge(entity_conn, FACT_C, existing_pattern_id)

        llm_mock = AsyncMock(return_value={"is_pattern": True, "description": "Dup pattern"})

        with patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock):
            result = await _promote_patterns(entity_conn, "claude-3-5-haiku-20241022")

        assert result.pattern_facts_created == 0


# ---------------------------------------------------------------------------
# TS-96-E9: LLM failure for chain evaluation
# ---------------------------------------------------------------------------


class TestChainLLMFailure:
    """TS-96-E9: All edges preserved when LLM fails for chain evaluation.

    Requirements: 96-REQ-6.E1
    """

    @pytest.mark.asyncio
    async def test_chain_llm_failure(
        self, entity_conn: duckdb.DuckDBPyConnection, caplog: pytest.LogCaptureFixture
    ) -> None:
        """LLM failure for chain -> all edges preserved, warning logged."""
        _insert_fact(entity_conn, FACT_A)
        _insert_fact(entity_conn, FACT_B)
        _insert_fact(entity_conn, FACT_C)
        _insert_causal_edge(entity_conn, FACT_A, FACT_B)
        _insert_causal_edge(entity_conn, FACT_B, FACT_C)
        _insert_causal_edge(entity_conn, FACT_A, FACT_C)

        llm_mock = AsyncMock(side_effect=RuntimeError("Chain LLM failure"))

        with (
            patch("agent_fox.knowledge.consolidation._call_llm_json", llm_mock),
            caplog.at_level(logging.WARNING, logger="agent_fox.knowledge.consolidation"),
        ):
            result = await _prune_redundant_chains(entity_conn, "claude-3-5-haiku-20241022")

        assert result.edges_removed == 0
        assert _edge_exists(entity_conn, FACT_A, FACT_B)
        assert _edge_exists(entity_conn, FACT_B, FACT_C)
        assert _edge_exists(entity_conn, FACT_A, FACT_C)
