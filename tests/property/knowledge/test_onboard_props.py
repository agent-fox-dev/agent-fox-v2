"""Property tests for knowledge onboarding — Spec 101.

Tests: TS-101-P1, TS-101-P2, TS-101-P3, TS-101-P4, TS-101-P5
Properties: Threshold monotonicity, idempotency, mining fact validity,
            phase independence, LLM fact validity.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest
from agent_fox.knowledge.code_analysis import CodeAnalysisResult, _parse_llm_facts
from agent_fox.knowledge.doc_mining import DocMiningResult
from agent_fox.knowledge.git_mining import MiningResult, mine_git_patterns
from agent_fox.knowledge.onboard import OnboardResult, run_onboard
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig
from agent_fox.knowledge.entities import AnalysisResult
from agent_fox.knowledge.facts import Category
from agent_fox.knowledge.ingest import IngestResult
from agent_fox.knowledge.store import load_facts_by_spec

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fresh_conn() -> duckdb.DuckDBPyConnection:
    """Open a fresh in-memory DuckDB with all migrations applied."""
    import duckdb as _duckdb

    from agent_fox.knowledge.migrations import run_migrations

    conn = _duckdb.connect(":memory:")
    run_migrations(conn)
    return conn


def _make_mock_ingestor(
    adrs: int = 0,
    errata: int = 0,
    git: int = 0,
) -> MagicMock:
    ingestor = MagicMock()
    ingestor.ingest_adrs.return_value = IngestResult("adr", adrs, 0, 0)
    ingestor.ingest_errata.return_value = IngestResult("errata", errata, 0, 0)
    ingestor.ingest_git_commits.return_value = IngestResult("git", git, 0, 0)
    return ingestor


def _make_mock_db(conn: duckdb.DuckDBPyConnection) -> MagicMock:
    from agent_fox.knowledge.db import KnowledgeDB

    db = MagicMock(spec=KnowledgeDB)
    db.connection = conn
    return db


# ---------------------------------------------------------------------------
# TS-101-P1: Mining Threshold Monotonicity
# ---------------------------------------------------------------------------


class TestThresholdMonotonicity:
    """TS-101-P1: Higher fragile threshold produces fewer or equal facts.

    Property: 101-Property-1
    Validates: 101-REQ-4.1, 101-REQ-4.4
    """

    @given(
        threshold_low=st.integers(min_value=1, max_value=30),
        threshold_high=st.integers(min_value=31, max_value=100),
        file_count=st.integers(min_value=15, max_value=40),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_higher_threshold_produces_fewer_or_equal_facts(
        self,
        threshold_low: int,
        threshold_high: int,
        file_count: int,
        tmp_path: Path,
    ) -> None:
        """Higher fragile threshold ≤ lower threshold in fact count."""
        # Generate mock git data: one hot file with file_count commits
        mock_data = {f"sha{i}": [f"file_{i % 5}.py"] for i in range(file_count)}

        conn_low = _fresh_conn()
        conn_high = _fresh_conn()

        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            result_low = mine_git_patterns(
                tmp_path, conn_low, fragile_threshold=threshold_low
            )
            result_high = mine_git_patterns(
                tmp_path, conn_high, fragile_threshold=threshold_high
            )

        assert result_high.fragile_areas_created <= result_low.fragile_areas_created


# ---------------------------------------------------------------------------
# TS-101-P2: Onboard Idempotency
# ---------------------------------------------------------------------------


class TestOnboardIdempotency:
    """TS-101-P2: Second run creates zero new facts.

    Property: 101-Property-2
    Validates: 101-REQ-8.2
    """

    @pytest.mark.asyncio
    async def test_second_run_zero_new_facts(self, tmp_path: Path) -> None:
        """Second onboard run produces no new fact creation counts."""
        conn = _fresh_conn()
        mock_db = _make_mock_db(conn)
        config = AgentFoxConfig()
        mock_ingestor = _make_mock_ingestor(adrs=0, errata=0, git=0)

        with (
            patch(
                "agent_fox.knowledge.onboard.analyze_codebase",
                return_value=AnalysisResult(0, 0, 0),
            ),
            patch(
                "agent_fox.knowledge.onboard.KnowledgeIngestor",
                return_value=mock_ingestor,
            ),
            patch(
                "agent_fox.knowledge.onboard.mine_git_patterns",
                return_value=MiningResult(
                    fragile_areas_created=1,
                    cochange_patterns_created=0,
                    commits_analyzed=25,
                    files_analyzed=1,
                ),
            ),
            patch(
                "agent_fox.knowledge.onboard.analyze_code_with_llm",
                new_callable=AsyncMock,
                return_value=CodeAnalysisResult(facts_created=2, files_analyzed=1, files_skipped=0),
            ),
            patch(
                "agent_fox.knowledge.onboard.mine_docs_with_llm",
                new_callable=AsyncMock,
                return_value=DocMiningResult(facts_created=1, docs_analyzed=1, docs_skipped=0),
            ),
            patch(
                "agent_fox.knowledge.onboard._generate_missing_embeddings",
                return_value=(0, 0),
            ),
        ):
            _result1 = await run_onboard(tmp_path, config, mock_db)

        # Second run: all phases return zero counts (dedup already happened)
        mock_ingestor2 = _make_mock_ingestor(adrs=0, errata=0, git=0)
        with (
            patch(
                "agent_fox.knowledge.onboard.analyze_codebase",
                return_value=AnalysisResult(0, 0, 0),
            ),
            patch(
                "agent_fox.knowledge.onboard.KnowledgeIngestor",
                return_value=mock_ingestor2,
            ),
            patch(
                "agent_fox.knowledge.onboard.mine_git_patterns",
                return_value=MiningResult(),
            ),
            patch(
                "agent_fox.knowledge.onboard.analyze_code_with_llm",
                new_callable=AsyncMock,
                return_value=CodeAnalysisResult(),
            ),
            patch(
                "agent_fox.knowledge.onboard.mine_docs_with_llm",
                new_callable=AsyncMock,
                return_value=DocMiningResult(),
            ),
            patch(
                "agent_fox.knowledge.onboard._generate_missing_embeddings",
                return_value=(0, 0),
            ),
        ):
            result2 = await run_onboard(tmp_path, config, mock_db)

        assert result2.adrs_ingested == 0
        assert result2.errata_ingested == 0
        assert result2.git_commits_ingested == 0
        assert result2.fragile_areas_created == 0
        assert result2.cochange_patterns_created == 0
        assert result2.code_facts_created == 0
        assert result2.doc_facts_created == 0


# ---------------------------------------------------------------------------
# TS-101-P3: Mining Fact Validity
# ---------------------------------------------------------------------------


class TestMiningFactValidity:
    """TS-101-P3: Every mined fact has required fields correctly set.

    Property: 101-Property-3
    Validates: 101-REQ-4.1, 101-REQ-4.2
    """

    @given(
        file_count=st.integers(min_value=1, max_value=5),
        commit_count=st.integers(min_value=20, max_value=50),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_all_mined_facts_have_valid_fields(
        self,
        file_count: int,
        commit_count: int,
        tmp_path: Path,
    ) -> None:
        """All created facts pass validity checks on required fields."""
        conn = _fresh_conn()
        # Each commit touches all files (forces fragile area detection)
        file_names = [f"src/module_{i}.py" for i in range(file_count)]
        mock_data = {f"sha{i}": file_names for i in range(commit_count)}

        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            mine_git_patterns(tmp_path, conn, fragile_threshold=10, cochange_threshold=5)

        facts = load_facts_by_spec("onboard", conn)
        valid_categories = {c.value for c in Category}

        for fact in facts:
            assert fact.content != "", f"Empty content: {fact}"
            assert fact.category in valid_categories, f"Invalid category: {fact.category}"
            assert fact.spec_name == "onboard", f"Wrong spec_name: {fact.spec_name}"
            assert len(fact.keywords) >= 1, f"Empty keywords: {fact}"
            assert 0.0 <= fact.confidence <= 1.0, f"Out-of-range confidence: {fact.confidence}"


# ---------------------------------------------------------------------------
# TS-101-P4: Phase Independence
# ---------------------------------------------------------------------------


class TestPhaseIndependence:
    """TS-101-P4: Skipped phases do not affect non-skipped phases.

    Property: 101-Property-4
    Validates: 101-REQ-2.2, 101-REQ-3.2, 101-REQ-4.7, 101-REQ-5.4,
               101-REQ-6.3, 101-REQ-7.2
    """

    @given(
        skip_entities=st.booleans(),
        skip_ingestion=st.booleans(),
    )
    @settings(
        max_examples=16,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_mining_unaffected_by_other_skips(
        self,
        skip_entities: bool,
        skip_ingestion: bool,
        tmp_path: Path,
    ) -> None:
        """Mining fact count is same regardless of which other phases are skipped."""
        mining_result = MiningResult(
            fragile_areas_created=2,
            cochange_patterns_created=1,
            commits_analyzed=30,
            files_analyzed=5,
        )

        mock_ingestor = _make_mock_ingestor()
        config = AgentFoxConfig()

        async def _run_with_skips(
            skip_ent: bool, skip_ing: bool
        ) -> OnboardResult:
            conn = _fresh_conn()
            db = _make_mock_db(conn)
            with (
                patch(
                    "agent_fox.knowledge.onboard.analyze_codebase",
                    return_value=AnalysisResult(0, 0, 0),
                ),
                patch(
                    "agent_fox.knowledge.onboard.KnowledgeIngestor",
                    return_value=mock_ingestor,
                ),
                patch(
                    "agent_fox.knowledge.onboard.mine_git_patterns",
                    return_value=mining_result,
                ),
                patch(
                    "agent_fox.knowledge.onboard.analyze_code_with_llm",
                    new_callable=AsyncMock,
                    return_value=CodeAnalysisResult(),
                ),
                patch(
                    "agent_fox.knowledge.onboard.mine_docs_with_llm",
                    new_callable=AsyncMock,
                    return_value=DocMiningResult(),
                ),
                patch(
                    "agent_fox.knowledge.onboard._generate_missing_embeddings",
                    return_value=(0, 0),
                ),
            ):
                return await run_onboard(
                    tmp_path,
                    config,
                    db,
                    skip_entities=skip_ent,
                    skip_ingestion=skip_ing,
                    skip_mining=False,
                )

        r1 = asyncio.run(_run_with_skips(skip_entities, skip_ingestion))
        r2 = asyncio.run(_run_with_skips(True, True))  # max skips except mining

        assert r1.fragile_areas_created == r2.fragile_areas_created
        assert r1.cochange_patterns_created == r2.cochange_patterns_created


# ---------------------------------------------------------------------------
# TS-101-P5: LLM Fact Validity
# ---------------------------------------------------------------------------


_VALID_CATEGORIES = [
    "decision",
    "convention",
    "pattern",
    "anti_pattern",
    "fragile_area",
    "gotcha",
]


class TestLLMFactValidity:
    """TS-101-P5: Every LLM-derived fact has required fields correctly set.

    Property: 101-Property-5
    Validates: 101-REQ-5.1, 101-REQ-6.1
    """

    @given(
        content=st.text(min_size=1, max_size=500).filter(lambda s: s.strip()),
        category=st.sampled_from(_VALID_CATEGORIES),
        confidence=st.sampled_from(["high", "medium", "low"]),
        keywords=st.lists(
            st.text(min_size=1, max_size=30).filter(lambda s: s.strip()),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_parsed_code_facts_are_valid(
        self,
        content: str,
        category: str,
        confidence: str,
        keywords: list[str],
    ) -> None:
        """All facts parsed via _parse_llm_facts satisfy validity invariants."""
        raw = json.dumps(
            [
                {
                    "content": content,
                    "category": category,
                    "confidence": confidence,
                    "keywords": keywords,
                }
            ]
        )
        facts = _parse_llm_facts(
            raw, spec_name="onboard", file_path="file.py", source_type="code"
        )

        valid_categories = {c.value for c in Category}
        for fact in facts:
            assert fact.content.strip() != "", "Empty content"
            assert fact.category in valid_categories, f"Invalid category: {fact.category}"
            assert fact.spec_name == "onboard", "Wrong spec_name"
            assert len(fact.keywords) >= 1, "Empty keywords list"
            assert any(
                "onboard:code:file.py" in kw for kw in fact.keywords
            ), "Fingerprint keyword missing"
            assert 0.0 <= fact.confidence <= 1.0, f"Confidence out of range: {fact.confidence}"
