"""Property tests for cross-spec vector retrieval invariants.

Tests: TS-94-P1 through TS-94-P5
Properties: Deduplication Invariant, Budget Independence, Graceful Degradation
            Identity, Metadata Bullet Exclusion, Superseded Exclusion
Requirements: 94-REQ-3.1, 94-REQ-3.E1, 94-REQ-4.1, 94-REQ-2.2,
              94-REQ-5.1, 94-REQ-2.E1, 94-REQ-1.2, 94-REQ-2.2
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig, KnowledgeConfig
from agent_fox.engine import session_lifecycle
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.search import SearchResult, VectorSearch

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_FACT_IDS = st.sampled_from(
    [
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "dddddddd-dddd-dddd-dddd-dddddddddddd",
        "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
        "44444444-4444-4444-4444-444444444444",
    ]
)


@st.composite
def fact_list(draw: st.DrawFn, min_size: int = 0, max_size: int = 10) -> list[Fact]:
    """Generate a list of Fact objects with unique IDs."""
    ids = draw(
        st.lists(
            _FACT_IDS,
            min_size=min_size,
            max_size=max_size,
            unique=True,
        )
    )
    return [
        Fact(
            id=fact_id,
            content=f"Fact content {fact_id}",
            category="pattern",
            spec_name="test_spec",
            keywords=[],
            confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
        )
        for fact_id in ids
    ]


@st.composite
def search_result_list(draw: st.DrawFn, min_size: int = 0, max_size: int = 10) -> list[SearchResult]:
    """Generate a list of SearchResult objects with unique fact_ids."""
    ids = draw(
        st.lists(
            _FACT_IDS,
            min_size=min_size,
            max_size=max_size,
            unique=True,
        )
    )
    return [
        SearchResult(
            fact_id=fact_id,
            content=f"Search result {fact_id}",
            category="pattern",
            spec_name="other_spec",
            session_id=None,
            commit_sha=None,
            similarity=0.8,
        )
        for fact_id in ids
    ]


# ---------------------------------------------------------------------------
# DuckDB schema for property tests that need it
# ---------------------------------------------------------------------------

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS memory_facts (
    id            UUID PRIMARY KEY,
    content       TEXT NOT NULL,
    category      TEXT,
    spec_name     TEXT,
    session_id    TEXT,
    commit_sha    TEXT,
    confidence    DOUBLE DEFAULT 0.6,
    created_at    TIMESTAMP,
    superseded_by UUID
);

CREATE TABLE IF NOT EXISTS memory_embeddings (
    id        UUID PRIMARY KEY REFERENCES memory_facts(id),
    embedding FLOAT[384]
);
"""


def _make_deterministic_embedding(seed: int, dim: int = 384) -> list[float]:
    """Generate a deterministic normalized embedding for property tests."""
    raw = [math.sin(seed * (i + 1) * 0.1) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    if norm == 0:
        return [1.0 / math.sqrt(dim)] * dim
    return [x / norm for x in raw]


# ---------------------------------------------------------------------------
# TS-94-P1: Deduplication invariant
# Property 1 from design.md
# Requirements: 94-REQ-3.1, 94-REQ-3.E1
# ---------------------------------------------------------------------------


@given(
    spec_facts=fact_list(min_size=0, max_size=10),
    cross_results=search_result_list(min_size=0, max_size=10),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_deduplication_invariant(
    spec_facts: list[Fact],
    cross_results: list[SearchResult],
) -> None:
    """TS-94-P1: Merged result has no duplicate IDs; all spec fact IDs preserved."""
    merged = session_lifecycle.merge_cross_spec_facts(spec_facts, cross_results)

    ids = [f.id for f in merged]
    # No duplicate IDs
    assert len(ids) == len(set(ids)), "Merged result must not contain duplicate IDs"

    # All spec-specific fact IDs preserved
    spec_ids = {f.id for f in spec_facts}
    merged_ids = set(ids)
    assert spec_ids.issubset(merged_ids), "All spec-specific fact IDs must be in merged result"


# ---------------------------------------------------------------------------
# TS-94-P2: Budget independence
# Property 2 from design.md
# Requirements: 94-REQ-4.1, 94-REQ-2.2
# ---------------------------------------------------------------------------


@given(top_k=st.integers(min_value=0, max_value=50))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_budget_independence(top_k: int) -> None:
    """TS-94-P2: Number of cross-spec facts in merged result never exceeds top_k."""
    # Generate cross_results with exactly top_k items (unique IDs)
    cross_result_ids = [str(uuid.uuid4()) for _ in range(top_k)]
    cross_results = [
        SearchResult(
            fact_id=fid,
            content=f"Content {fid}",
            category="pattern",
            spec_name="other_spec",
            session_id=None,
            commit_sha=None,
            similarity=0.8,
        )
        for fid in cross_result_ids
    ]

    merged = session_lifecycle.merge_cross_spec_facts([], cross_results)

    # The cross-spec contribution must be at most top_k
    assert len(merged) <= top_k, f"Merged result ({len(merged)}) exceeds top_k ({top_k})"


# ---------------------------------------------------------------------------
# TS-94-P3: Graceful degradation identity
# Property 3 from design.md
# Requirements: 94-REQ-5.1, 94-REQ-2.E1
# ---------------------------------------------------------------------------


@given(
    spec_facts=fact_list(min_size=0, max_size=10),
    exc_type=st.sampled_from([RuntimeError, ValueError, OSError]),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_graceful_degradation_identity(
    tmp_path: Path,
    spec_facts: list[Fact],
    exc_type: type[Exception],
) -> None:
    """TS-94-P3: Any exception during retrieval → output equals spec-specific input."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir(exist_ok=True)
    # Write a tasks.md so extraction doesn't fail
    (spec_dir / "tasks.md").write_text("- [ ] 2. Some group\n\n  - [ ] 2.1 Subtask\n    - Do something\n")

    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.embed_text.side_effect = exc_type("test error")

    runner = NodeSessionRunner(
        "12_rate_limiting:2",
        AgentFoxConfig(),
        knowledge_db=MagicMock(spec=KnowledgeDB),
        embedder=mock_embedder,
    )

    result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)

    assert result == spec_facts, "On exception, must return spec-specific facts unchanged"


# ---------------------------------------------------------------------------
# TS-94-P4: Metadata bullet exclusion
# Property 4 from design.md
# Requirements: 94-REQ-1.2
# ---------------------------------------------------------------------------


@given(
    non_metadata_bullets=st.lists(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                whitelist_characters=" _()[]",
                blacklist_characters="_",
            ).filter(lambda c: c != "_"),
            min_size=2,
            max_size=40,
        ).filter(lambda s: s.strip() and not s.startswith("_")),
        min_size=1,
        max_size=5,
    ),
    metadata_bullets=st.lists(
        st.text(min_size=2, max_size=30).map(lambda s: f"_{s}_"),
        min_size=0,
        max_size=5,
    ),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_metadata_exclusion(
    tmp_path: Path,
    non_metadata_bullets: list[str],
    metadata_bullets: list[str],
) -> None:
    """TS-94-P4: No extracted description starts with '_' (underscore)."""
    # Build a tasks.md with mixed metadata and non-metadata bullets
    lines = ["- [ ] 1. Some group", "", "  - [ ] 1.1 Subtask"]
    # Add metadata bullets first, then non-metadata
    for mb in metadata_bullets:
        lines.append(f"    - {mb}")
    for nb in non_metadata_bullets:
        lines.append(f"    - {nb}")

    spec_dir = tmp_path / f"spec_{hash(str(non_metadata_bullets))}"
    spec_dir.mkdir(exist_ok=True)
    (spec_dir / "tasks.md").write_text("\n".join(lines) + "\n")

    result = session_lifecycle.extract_subtask_descriptions(spec_dir, 1)

    for desc in result:
        assert not desc.startswith("_"), f"Extracted description must not start with '_': {desc!r}"


# ---------------------------------------------------------------------------
# TS-94-P5: Superseded exclusion
# Property 5 from design.md
# Requirements: 94-REQ-2.2
# ---------------------------------------------------------------------------


@given(
    active_count=st.integers(min_value=1, max_value=5),
    superseded_count=st.integers(min_value=0, max_value=5),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_superseded_exclusion(
    active_count: int,
    superseded_count: int,
) -> None:
    """TS-94-P5: VectorSearch with exclude_superseded=True never returns superseded facts."""
    conn = duckdb.connect(":memory:")
    conn.execute(_SCHEMA_DDL)

    config = KnowledgeConfig()
    query_embedding = _make_deterministic_embedding(0)

    # Insert active facts with embeddings
    active_ids = []
    for i in range(active_count):
        fid = str(uuid.uuid4())
        active_ids.append(fid)
        emb = _make_deterministic_embedding(i + 1)
        conn.execute(
            "INSERT INTO memory_facts (id, content, category, spec_name, confidence, created_at)"
            " VALUES (?, ?, 'pattern', 'test_spec', 0.9, CURRENT_TIMESTAMP)",
            [fid, f"Active fact {i}"],
        )
        conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [fid, emb],
        )

    # Insert superseded facts (superseded_by = some other UUID)
    superseded_ids = []
    for i in range(superseded_count):
        fid = str(uuid.uuid4())
        superseded_ids.append(fid)
        emb = _make_deterministic_embedding(i + 100)
        conn.execute(
            "INSERT INTO memory_facts (id, content, category, spec_name, confidence,"
            " created_at, superseded_by)"
            " VALUES (?, ?, 'pattern', 'test_spec', 0.9, CURRENT_TIMESTAMP, ?)",
            [fid, f"Superseded fact {i}", str(uuid.uuid4())],
        )
        conn.execute(
            "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?::FLOAT[384])",
            [fid, emb],
        )

    vs = VectorSearch(conn, config)
    results = vs.search(query_embedding, top_k=100, exclude_superseded=True)

    result_ids = {r.fact_id for r in results}

    # No superseded fact IDs should appear in results
    for sid in superseded_ids:
        assert sid not in result_ids, f"Superseded fact {sid!r} appeared in results despite exclude_superseded=True"

    conn.close()
