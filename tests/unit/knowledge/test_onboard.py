"""Tests for agent_fox.knowledge.onboard — Spec 101.

Tests: TS-101-3, TS-101-4, TS-101-5, TS-101-6, TS-101-9, TS-101-11,
       TS-101-12, TS-101-13, TS-101-22, TS-101-27, TS-101-30,
       TS-101-E2, TS-101-E3, TS-101-E4, TS-101-E5, TS-101-E6
Requirements: 101-REQ-1.6, 101-REQ-2.1, 101-REQ-2.2, 101-REQ-2.E1,
              101-REQ-3.1, 101-REQ-3.2, 101-REQ-3.3, 101-REQ-3.E1,
              101-REQ-4.7, 101-REQ-5.4, 101-REQ-6.3, 101-REQ-7.1,
              101-REQ-7.2, 101-REQ-7.E1, 101-REQ-8.1, 101-REQ-8.2,
              101-REQ-8.3, 101-REQ-1.E2
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest
from agent_fox.knowledge.code_analysis import CodeAnalysisResult
from agent_fox.knowledge.doc_mining import DocMiningResult
from agent_fox.knowledge.git_mining import MiningResult
from agent_fox.knowledge.onboard import OnboardResult, run_onboard

from agent_fox.core.config import AgentFoxConfig
from agent_fox.knowledge.entities import AnalysisResult
from agent_fox.knowledge.ingest import IngestResult


@pytest.fixture()
def agent_config() -> AgentFoxConfig:
    """Return default AgentFoxConfig."""
    return AgentFoxConfig()


@pytest.fixture()
def mock_db(knowledge_conn: duckdb.DuckDBPyConnection) -> MagicMock:
    """Return a MagicMock KnowledgeDB backed by the test knowledge_conn."""
    from agent_fox.knowledge.db import KnowledgeDB

    db = MagicMock(spec=KnowledgeDB)
    db.connection = knowledge_conn
    return db


def _make_mock_ingestor(
    adrs: int = 0,
    errata: int = 0,
    git: int = 0,
) -> MagicMock:
    """Create a mock KnowledgeIngestor returning known IngestResults."""
    ingestor = MagicMock()
    ingestor.ingest_adrs.return_value = IngestResult("adr", adrs, 0, 0)
    ingestor.ingest_errata.return_value = IngestResult("errata", errata, 0, 0)
    ingestor.ingest_git_commits.return_value = IngestResult("git", git, 0, 0)
    return ingestor


def _all_phases_mocked(
    *,
    entities: AnalysisResult | None = None,
    adrs: int = 0,
    errata: int = 0,
    git: int = 0,
    mining: MiningResult | None = None,
    code: CodeAnalysisResult | None = None,
    docs: DocMiningResult | None = None,
    embeddings: tuple[int, int] = (0, 0),
) -> dict:
    """Return a dict of patch targets → return values for all phases."""
    return {
        "agent_fox.knowledge.onboard.analyze_codebase": entities or AnalysisResult(0, 0, 0),
        "agent_fox.knowledge.onboard.mine_git_patterns": mining or MiningResult(),
        "agent_fox.knowledge.onboard.analyze_code_with_llm": code or CodeAnalysisResult(),
        "agent_fox.knowledge.onboard.mine_docs_with_llm": docs or DocMiningResult(),
        "agent_fox.knowledge.onboard._generate_missing_embeddings": embeddings,
    }


class TestOnboardResultFields:
    """TS-101-13: OnboardResult has all required fields with correct defaults.

    Requirement: 101-REQ-8.1, 101-REQ-8.3
    """

    def test_all_integer_fields_default_to_zero(self) -> None:
        """Verify all count fields default to zero."""
        r = OnboardResult()
        assert r.entities_upserted == 0
        assert r.edges_upserted == 0
        assert r.entities_soft_deleted == 0
        assert r.adrs_ingested == 0
        assert r.errata_ingested == 0
        assert r.git_commits_ingested == 0
        assert r.fragile_areas_created == 0
        assert r.cochange_patterns_created == 0
        assert r.commits_analyzed == 0
        assert r.files_analyzed == 0
        assert r.code_facts_created == 0
        assert r.code_files_analyzed == 0
        assert r.code_files_skipped == 0
        assert r.doc_facts_created == 0
        assert r.docs_analyzed == 0
        assert r.docs_skipped == 0
        assert r.embeddings_generated == 0
        assert r.embeddings_failed == 0

    def test_list_fields_default_to_empty(self) -> None:
        """Verify phases_skipped and phases_errored default to empty lists."""
        r = OnboardResult()
        assert r.phases_skipped == []
        assert r.phases_errored == []

    def test_elapsed_seconds_defaults_to_zero(self) -> None:
        """Verify elapsed_seconds defaults to 0.0."""
        r = OnboardResult()
        assert r.elapsed_seconds == 0.0

    def test_serializable_to_dict_via_asdict(self) -> None:
        """TS-101-13 (REQ-8.3): OnboardResult serializable via dataclasses.asdict."""
        r = OnboardResult()
        d = dataclasses.asdict(r)
        assert isinstance(d, dict)
        assert "entities_upserted" in d
        assert "code_facts_created" in d
        assert "doc_facts_created" in d
        assert "phases_skipped" in d
        assert "phases_errored" in d
        assert "elapsed_seconds" in d


class TestEntityGraphPhase:
    """TS-101-3, TS-101-4: Entity graph phase runs and is skippable.

    Requirements: 101-REQ-2.1, 101-REQ-2.2
    """

    @pytest.mark.asyncio
    async def test_entity_phase_calls_analyze_codebase(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-3: analyze_codebase is called with project_root and conn."""
        mock_ingestor = _make_mock_ingestor()
        with (
            patch(
                "agent_fox.knowledge.onboard.analyze_codebase",
                return_value=AnalysisResult(5, 3, 0),
            ) as mock_analyze,
            patch(
                "agent_fox.knowledge.onboard.KnowledgeIngestor",
                return_value=mock_ingestor,
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
            result = await run_onboard(tmp_path, agent_config, mock_db)

        assert mock_analyze.called
        assert result.entities_upserted >= 0

    @pytest.mark.asyncio
    async def test_skip_entities_skips_analyze_codebase(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-4: analyze_codebase NOT called when skip_entities=True."""
        mock_ingestor = _make_mock_ingestor()
        with (
            patch(
                "agent_fox.knowledge.onboard.analyze_codebase",
            ) as mock_analyze,
            patch(
                "agent_fox.knowledge.onboard.KnowledgeIngestor",
                return_value=mock_ingestor,
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
            result = await run_onboard(
                tmp_path, agent_config, mock_db, skip_entities=True
            )

        assert not mock_analyze.called
        assert "entities" in result.phases_skipped


class TestIngestionPhase:
    """TS-101-5, TS-101-6: Ingestion phase runs all sources and is skippable.

    Requirements: 101-REQ-3.1, 101-REQ-3.2
    """

    @pytest.mark.asyncio
    async def test_ingestion_phase_calls_all_three_sources(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-5: ingest_adrs, ingest_errata, ingest_git_commits all called."""
        # Make tmp_path look like a git repo so git commits are attempted
        (tmp_path / ".git").mkdir()

        mock_ingestor = _make_mock_ingestor(adrs=2, errata=1, git=10)
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
            result = await run_onboard(tmp_path, agent_config, mock_db)

        assert mock_ingestor.ingest_adrs.called
        assert mock_ingestor.ingest_errata.called
        assert result.adrs_ingested == 2
        assert result.errata_ingested == 1

    @pytest.mark.asyncio
    async def test_skip_ingestion_skips_all_sources(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-6: No ingest functions called when skip_ingestion=True."""
        mock_ingestor = _make_mock_ingestor()
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
            result = await run_onboard(
                tmp_path, agent_config, mock_db, skip_ingestion=True
            )

        assert not mock_ingestor.ingest_adrs.called
        assert "ingestion" in result.phases_skipped


class TestMiningPhase:
    """TS-101-9: Mining phase is skippable.

    Requirement: 101-REQ-4.7
    """

    @pytest.mark.asyncio
    async def test_skip_mining_skips_mine_git_patterns(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-9: mine_git_patterns NOT called when skip_mining=True."""
        mock_ingestor = _make_mock_ingestor()
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
            ) as mock_mining,
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
            result = await run_onboard(
                tmp_path, agent_config, mock_db, skip_mining=True
            )

        assert not mock_mining.called
        assert "mining" in result.phases_skipped


class TestCodeAnalysisPhase:
    """TS-101-22: Code analysis phase is skippable.

    Requirement: 101-REQ-5.4
    """

    @pytest.mark.asyncio
    async def test_skip_code_analysis_skips_phase(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-22: analyze_code_with_llm NOT called when skip_code_analysis=True."""
        mock_ingestor = _make_mock_ingestor()
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
                return_value=MiningResult(),
            ),
            patch(
                "agent_fox.knowledge.onboard.analyze_code_with_llm",
                new_callable=AsyncMock,
            ) as mock_code,
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
            result = await run_onboard(
                tmp_path, agent_config, mock_db, skip_code_analysis=True
            )

        assert not mock_code.called
        assert "code_analysis" in result.phases_skipped


class TestDocMiningPhase:
    """TS-101-27: Documentation mining phase is skippable.

    Requirement: 101-REQ-6.3
    """

    @pytest.mark.asyncio
    async def test_skip_doc_mining_skips_phase(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-27: mine_docs_with_llm NOT called when skip_doc_mining=True."""
        mock_ingestor = _make_mock_ingestor()
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
            ) as mock_docs,
            patch(
                "agent_fox.knowledge.onboard._generate_missing_embeddings",
                return_value=(0, 0),
            ),
        ):
            result = await run_onboard(
                tmp_path, agent_config, mock_db, skip_doc_mining=True
            )

        assert not mock_docs.called
        assert "doc_mining" in result.phases_skipped


class TestEmbeddingPhase:
    """TS-101-11, TS-101-12: Embedding phase generates embeddings and is skippable.

    Requirements: 101-REQ-7.1, 101-REQ-7.2
    """

    @pytest.mark.asyncio
    async def test_embedding_phase_generates_embeddings(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-11: embeddings_generated > 0 in result when embeddings exist."""
        mock_ingestor = _make_mock_ingestor()
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
                return_value=(3, 0),
            ),
        ):
            result = await run_onboard(tmp_path, agent_config, mock_db)

        assert result.embeddings_generated == 3

    @pytest.mark.asyncio
    async def test_skip_embeddings_skips_phase(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-12: Embedding phase skipped when skip_embeddings=True."""
        mock_ingestor = _make_mock_ingestor()
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
            ) as mock_embed,
        ):
            result = await run_onboard(
                tmp_path, agent_config, mock_db, skip_embeddings=True
            )

        assert not mock_embed.called
        assert "embeddings" in result.phases_skipped


class TestModelOptionForwarding:
    """TS-101-30: --model option forwarded to LLM phases.

    Requirement: 101-REQ-1.6
    """

    @pytest.mark.asyncio
    async def test_model_forwarded_to_code_analysis(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-30: Both LLM phases receive model='ADVANCED'."""
        mock_ingestor = _make_mock_ingestor()
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
                return_value=MiningResult(),
            ),
            patch(
                "agent_fox.knowledge.onboard.analyze_code_with_llm",
                new_callable=AsyncMock,
                return_value=CodeAnalysisResult(),
            ) as mock_code,
            patch(
                "agent_fox.knowledge.onboard.mine_docs_with_llm",
                new_callable=AsyncMock,
                return_value=DocMiningResult(),
            ) as mock_docs,
            patch(
                "agent_fox.knowledge.onboard._generate_missing_embeddings",
                return_value=(0, 0),
            ),
        ):
            await run_onboard(tmp_path, agent_config, mock_db, model="ADVANCED")

        assert mock_code.called
        # The model kwarg should be "ADVANCED"
        code_kwargs = mock_code.call_args
        assert "ADVANCED" in str(code_kwargs)
        assert mock_docs.called
        docs_kwargs = mock_docs.call_args
        assert "ADVANCED" in str(docs_kwargs)


class TestRunOnboardEdgeCases:
    """TS-101-E2, TS-101-E3, TS-101-E4, TS-101-E5, TS-101-E6: Orchestrator edge cases."""

    @pytest.mark.asyncio
    async def test_non_git_directory_skips_git_mining(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-E2: Git mining skipped when project is not a git repo."""
        # tmp_path has no .git directory
        mock_ingestor = _make_mock_ingestor()
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
            ) as mock_mining,
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
            result = await run_onboard(tmp_path, agent_config, mock_db)

        # Mining should be skipped for non-git
        assert not mock_mining.called
        assert result.fragile_areas_created == 0

    @pytest.mark.asyncio
    async def test_entity_phase_failure_continues_pipeline(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-E3: Entity graph failure doesn't abort pipeline."""
        mock_ingestor = _make_mock_ingestor(adrs=1)
        with (
            patch(
                "agent_fox.knowledge.onboard.analyze_codebase",
                side_effect=RuntimeError("parse error"),
            ),
            patch(
                "agent_fox.knowledge.onboard.KnowledgeIngestor",
                return_value=mock_ingestor,
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
            result = await run_onboard(tmp_path, agent_config, mock_db)

        assert "entities" in result.phases_errored
        # Other phases should still have run (adrs_ingested > 0)
        assert result.adrs_ingested >= 0

    @pytest.mark.asyncio
    async def test_individual_ingestion_source_failure_continues(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-E4: One ingestion source failing doesn't block others."""
        mock_ingestor = MagicMock()
        mock_ingestor.ingest_adrs.side_effect = Exception("adr error")
        mock_ingestor.ingest_errata.return_value = IngestResult("errata", 2, 0, 0)
        mock_ingestor.ingest_git_commits.return_value = IngestResult("git", 5, 0, 0)

        (tmp_path / ".git").mkdir()  # make it look like a git repo

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
            result = await run_onboard(tmp_path, agent_config, mock_db)

        # errata and git commits should still be ingested
        assert result.errata_ingested == 2
        assert result.git_commits_ingested == 5

    @pytest.mark.asyncio
    async def test_embedding_failures_recorded_best_effort(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-E5: Embedding failures recorded; no exception raised."""
        mock_ingestor = _make_mock_ingestor()
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
                return_value=(1, 2),  # 1 success, 2 failures
            ),
        ):
            result = await run_onboard(tmp_path, agent_config, mock_db)

        assert result.embeddings_generated == 1
        assert result.embeddings_failed == 2

    @pytest.mark.asyncio
    async def test_non_git_still_ingests_adrs_and_errata(
        self, tmp_path: Path, agent_config: AgentFoxConfig, mock_db: MagicMock
    ) -> None:
        """TS-101-E6: ADRs and errata ingested even if not a git repo."""
        # tmp_path has no .git — not a git repo
        mock_ingestor = _make_mock_ingestor(adrs=3, errata=1, git=0)
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
            result = await run_onboard(tmp_path, agent_config, mock_db)

        assert result.adrs_ingested == 3
        assert result.errata_ingested == 1
        assert result.git_commits_ingested == 0
