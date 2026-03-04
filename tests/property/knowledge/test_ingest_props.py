"""Property tests for ingestion idempotency.

Test Spec: TS-12-P4 (ingestion idempotency)
Property: Property 7 from design.md
Requirements: 12-REQ-4.1, 12-REQ-4.2
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.ingest import KnowledgeIngestor

# -- Helpers -----------------------------------------------------------------


def _fresh_schema_conn() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DuckDB with schema."""
    from tests.unit.knowledge.conftest import create_schema

    conn = duckdb.connect(":memory:")
    create_schema(conn)
    return conn


def _make_embedding(seed: int) -> list[float]:
    """Create a deterministic 1024-dim embedding."""
    raw = [math.sin(seed * (i + 1) * 0.1) for i in range(1024)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw] if norm > 0 else [1.0 / math.sqrt(1024)] * 1024


def _create_n_adr_files(adr_dir: Path, n: int) -> None:
    """Create N unique ADR markdown files."""
    adr_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        name = f"{i + 1:03d}-decision-{i + 1}.md"
        content = f"# ADR {i + 1}: Decision {i + 1}\n\n"
        content += "## Status\n\nAccepted\n\n"
        content += f"## Context\n\nContext for decision {i + 1}.\n\n"
        content += f"## Decision\n\nWe decided on approach {i + 1}.\n"
        (adr_dir / name).write_text(content)


# -- Property Tests ----------------------------------------------------------


class TestIngestionIdempotency:
    """TS-12-P4: Ingestion idempotency.

    Property 7: Ingesting the same source twice does not create
    duplicates. After two ingestions, the fact count equals the
    source count.

    Requirements: 12-REQ-4.1, 12-REQ-4.2
    """

    @given(adr_count=st.integers(min_value=1, max_value=5))
    @settings(max_examples=5, deadline=None)
    def test_adr_ingestion_idempotent(self, adr_count: int) -> None:
        """Ingesting ADRs twice yields same fact count as source count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            adr_dir = project_root / "docs" / "adr"
            _create_n_adr_files(adr_dir, adr_count)

            conn = _fresh_schema_conn()
            mock_embedder = MagicMock(spec=EmbeddingGenerator)
            mock_embedder.embed_text.return_value = _make_embedding(1)
            mock_embedder.embed_batch.return_value = [
                _make_embedding(i) for i in range(adr_count)
            ]

            ingestor = KnowledgeIngestor(conn, mock_embedder, project_root)

            # First ingestion
            result1 = ingestor.ingest_adrs(adr_dir=adr_dir)
            assert result1.facts_added == adr_count

            # Second ingestion (should skip all)
            result2 = ingestor.ingest_adrs(adr_dir=adr_dir)
            assert result2.facts_added == 0
            assert result2.facts_skipped == adr_count

            # Total count matches source count
            total = conn.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE category = 'adr'"
            ).fetchone()
            assert total is not None
            assert total[0] == adr_count

            conn.close()
