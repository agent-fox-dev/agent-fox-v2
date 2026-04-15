"""Integration smoke tests for knowledge onboarding — Spec 101.

Tests: TS-101-SMOKE-1, TS-101-SMOKE-2, TS-101-SMOKE-3, TS-101-SMOKE-4
Execution paths: Path 1, Path 3, Path 4, Path 5 from design.md
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest

from agent_fox.core.config import AgentFoxConfig
from agent_fox.knowledge.code_analysis import analyze_code_with_llm
from agent_fox.knowledge.doc_mining import mine_docs_with_llm
from agent_fox.knowledge.git_mining import mine_git_patterns
from agent_fox.knowledge.onboard import run_onboard
from agent_fox.knowledge.store import load_facts_by_spec

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Create a minimal project structure for smoke tests."""
    # Source files (Python + Go)
    (tmp_path / "main.py").write_text("def main():\n    pass\n")
    (tmp_path / "utils.py").write_text("def helper():\n    return True\n")
    (tmp_path / "server.go").write_text("package main\n\nfunc main() {}\n")

    # Documentation
    (tmp_path / "README.md").write_text("# Project\n\nThis project does cool things.\n")
    (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n\nAll PRs require two reviews.\n")

    # ADR directory
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "01-use-duckdb.md").write_text(
        "# ADR 01: Use DuckDB\n\n## Status: Accepted\n\n## Decision\n\nUse DuckDB.\n"
    )

    # Docs
    docs_dir = tmp_path / "docs"
    (docs_dir / "architecture.md").write_text("# Architecture\n\nEvent-driven.\n")

    return tmp_path


@pytest.fixture()
def mock_db(knowledge_conn: duckdb.DuckDBPyConnection) -> MagicMock:
    """Return a MagicMock KnowledgeDB backed by the test knowledge_conn."""
    from agent_fox.knowledge.db import KnowledgeDB

    db = MagicMock(spec=KnowledgeDB)
    db.connection = knowledge_conn
    return db


@pytest.fixture()
def agent_config() -> AgentFoxConfig:
    return AgentFoxConfig()


_CODE_FACT_RESPONSE = json.dumps(
    [
        {
            "content": "Uses clean function separation pattern",
            "category": "pattern",
            "confidence": "high",
            "keywords": ["function", "separation"],
        }
    ]
)

_DOC_FACT_RESPONSE = json.dumps(
    [
        {
            "content": "All PRs require two reviews before merge",
            "category": "convention",
            "confidence": "high",
            "keywords": ["PR", "review"],
        }
    ]
)

_GIT_NUMSTAT_OUTPUT = "\n".join(
    [
        # 25 commits touching hot_file.py (fragile area)
        # 8 commits touching both a.py and b.py (co-change)
        *[f"sha_hot{i}\n10\t5\thot_file.py\n" for i in range(25)],
        *[f"sha_pair{i}\n3\t1\ta.py\n2\t1\tb.py\n" for i in range(8)],
        "",
    ]
)


def _make_git_subprocess_mock(stdout: str = _GIT_NUMSTAT_OUTPUT) -> MagicMock:
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = stdout
    return mock


def _make_mock_ingestor(
    adrs: int = 1,
    errata: int = 0,
    git: int = 10,
) -> MagicMock:
    from agent_fox.knowledge.ingest import IngestResult

    ingestor = MagicMock()
    ingestor.ingest_adrs.return_value = IngestResult("adr", adrs, 0, 0)
    ingestor.ingest_errata.return_value = IngestResult("errata", errata, 0, 0)
    ingestor.ingest_git_commits.return_value = IngestResult("git", git, 0, 0)
    return ingestor


# ---------------------------------------------------------------------------
# TS-101-SMOKE-1: Full onboard pipeline end-to-end
# ---------------------------------------------------------------------------


class TestFullOnboardPipeline:
    """TS-101-SMOKE-1: Full onboarding pipeline end-to-end.

    Execution path: Path 1 from design.md.
    Must NOT be satisfied by mocking run_onboard or phase orchestration.
    """

    @pytest.mark.asyncio
    async def test_full_pipeline(
        self,
        project_root: Path,
        agent_config: AgentFoxConfig,
        mock_db: MagicMock,
    ) -> None:
        """Verify all phases run and produce counts in OnboardResult."""
        mock_ingestor = _make_mock_ingestor(adrs=1, errata=0, git=10)

        with (
            patch(
                "agent_fox.knowledge.onboard.analyze_codebase",
                return_value=__import__("agent_fox.knowledge.entities", fromlist=["AnalysisResult"]).AnalysisResult(
                    5, 3, 0
                ),
            ),
            patch(
                "agent_fox.knowledge.onboard.KnowledgeIngestor",
                return_value=mock_ingestor,
            ),
            patch(
                "agent_fox.knowledge.git_mining.subprocess.run",
                return_value=_make_git_subprocess_mock(),
            ),
            patch(
                "agent_fox.knowledge.code_analysis.ai_call",
                new_callable=AsyncMock,
                return_value=(_CODE_FACT_RESPONSE, None),
            ),
            patch(
                "agent_fox.knowledge.code_analysis._is_mining_fact_exists",
                return_value=False,
            ),
            patch(
                "agent_fox.knowledge.doc_mining.ai_call",
                new_callable=AsyncMock,
                return_value=(_DOC_FACT_RESPONSE, None),
            ),
            patch(
                "agent_fox.knowledge.doc_mining._is_mining_fact_exists",
                return_value=False,
            ),
            patch(
                "agent_fox.knowledge.onboard._generate_missing_embeddings",
                return_value=(10, 0),
            ),
        ):
            # Make project look like a git repo
            (project_root / ".git").mkdir(exist_ok=True)
            result = await run_onboard(project_root, agent_config, mock_db)

        assert result.entities_upserted > 0
        assert result.adrs_ingested > 0
        assert result.git_commits_ingested > 0
        assert result.code_facts_created > 0
        assert result.doc_facts_created > 0
        assert result.elapsed_seconds > 0
        assert result.phases_errored == []


# ---------------------------------------------------------------------------
# TS-101-SMOKE-2: Git mining end-to-end
# ---------------------------------------------------------------------------


class TestGitMiningEndToEnd:
    """TS-101-SMOKE-2: Git mining produces correct facts from realistic data.

    Execution path: Path 3 from design.md.
    Must NOT be satisfied by mocking mine_git_patterns.
    """

    def test_end_to_end_mining(
        self,
        project_root: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Verify fragile area and co-change facts created from git output."""
        # 25 commits touching hot_file.py → fragile area
        # 8 commits touching a.py+b.py → co-change pattern
        numstat_lines = []
        for i in range(25):
            numstat_lines.extend([f"sha_hot{i}", "10\t5\thot_file.py", ""])
        for i in range(8):
            numstat_lines.extend([f"sha_pair{i}", "3\t1\ta.py", "2\t1\tb.py", ""])
        git_output = "\n".join(numstat_lines)

        with patch(
            "agent_fox.knowledge.git_mining.subprocess.run",
            return_value=_make_git_subprocess_mock(git_output),
        ):
            result = mine_git_patterns(
                project_root,
                knowledge_conn,
                fragile_threshold=20,
                cochange_threshold=5,
            )

        assert result.fragile_areas_created == 1
        assert result.cochange_patterns_created == 1

        facts = load_facts_by_spec("onboard", knowledge_conn)
        assert len(facts) == 2

        categories = {f.category for f in facts}
        assert "fragile_area" in categories
        assert "pattern" in categories

        # Verify content correctness
        fragile = next(f for f in facts if f.category == "fragile_area")
        assert "hot_file.py" in fragile.content
        pattern = next(f for f in facts if f.category == "pattern")
        assert "a.py" in pattern.content
        assert "b.py" in pattern.content


# ---------------------------------------------------------------------------
# TS-101-SMOKE-3: Code analysis end-to-end
# ---------------------------------------------------------------------------


class TestCodeAnalysisEndToEnd:
    """TS-101-SMOKE-3: Code analysis produces facts from source files.

    Execution path: Path 4 from design.md.
    Must NOT be satisfied by mocking analyze_code_with_llm.
    """

    @pytest.mark.asyncio
    async def test_end_to_end_code_analysis(
        self,
        project_root: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Verify facts created for each source file via real LLM mock."""
        with (
            patch(
                "agent_fox.knowledge.code_analysis.ai_call",
                new_callable=AsyncMock,
                return_value=(_CODE_FACT_RESPONSE, None),
            ),
            patch(
                "agent_fox.knowledge.code_analysis._is_mining_fact_exists",
                return_value=False,
            ),
        ):
            result = await analyze_code_with_llm(project_root, knowledge_conn, model="STANDARD")

        assert result.facts_created > 0
        assert result.files_analyzed > 0

        facts = load_facts_by_spec("onboard", knowledge_conn)
        assert any("onboard:code:" in kw for f in facts for kw in f.keywords)


# ---------------------------------------------------------------------------
# TS-101-SMOKE-4: Doc mining end-to-end
# ---------------------------------------------------------------------------


class TestDocMiningEndToEnd:
    """TS-101-SMOKE-4: Doc mining produces facts from documentation.

    Execution path: Path 5 from design.md.
    Must NOT be satisfied by mocking mine_docs_with_llm.
    """

    @pytest.mark.asyncio
    async def test_end_to_end_doc_mining(
        self,
        project_root: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Verify facts created for each doc file: README and CONTRIBUTING."""
        with (
            patch(
                "agent_fox.knowledge.doc_mining.ai_call",
                new_callable=AsyncMock,
                return_value=(_DOC_FACT_RESPONSE, None),
            ),
            patch(
                "agent_fox.knowledge.doc_mining._is_mining_fact_exists",
                return_value=False,
            ),
        ):
            result = await mine_docs_with_llm(project_root, knowledge_conn, model="STANDARD")

        # README.md + CONTRIBUTING.md = 2 docs (docs/architecture.md excluded
        # because it's under docs/ but not adr/errata — actually it IS included)
        assert result.facts_created > 0
        assert result.docs_analyzed >= 2

        facts = load_facts_by_spec("onboard", knowledge_conn)
        assert any("onboard:doc:" in kw for f in facts for kw in f.keywords)
