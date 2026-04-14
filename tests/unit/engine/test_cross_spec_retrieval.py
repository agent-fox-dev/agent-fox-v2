"""Unit tests for cross-spec vector retrieval.

Tests: TS-94-1 through TS-94-10, TS-94-E1 through TS-94-E7
Requirements: 94-REQ-1.1, 94-REQ-1.2, 94-REQ-1.E1, 94-REQ-1.E2,
              94-REQ-2.1, 94-REQ-2.2, 94-REQ-2.E1, 94-REQ-2.E2,
              94-REQ-3.1, 94-REQ-3.2, 94-REQ-3.E1, 94-REQ-4.1, 94-REQ-4.2,
              94-REQ-5.1, 94-REQ-6.1, 94-REQ-6.2
"""

from __future__ import annotations

import pytest

pytest.skip("Legacy cross-spec retrieval removed per spec 104-REQ-6", allow_module_level=True)

from pathlib import Path  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

from agent_fox.core.config import AgentFoxConfig, KnowledgeConfig  # noqa: E402
from agent_fox.engine import session_lifecycle  # noqa: E402
from agent_fox.engine.session_lifecycle import NodeSessionRunner  # noqa: E402
from agent_fox.knowledge.db import KnowledgeDB  # noqa: E402
from agent_fox.knowledge.embeddings import EmbeddingGenerator  # noqa: E402
from agent_fox.knowledge.facts import Fact  # noqa: E402
from agent_fox.knowledge.search import SearchResult  # noqa: E402

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_MOCK_KB = MagicMock(spec=KnowledgeDB)

# tasks.md with two subtasks that have non-metadata bullets
TASKS_MD_CONTENT = """\
- [ ] 2. Add config field and subtask description extraction

  - [ ] 2.1 Add `cross_spec_top_k` to `KnowledgeConfig`
    - Add `push_fix_branch` field
    - _Requirements: 94-REQ-4.1_

  - [ ] 2.2 Update naming
    - Modify branch naming function
"""

# tasks.md where the first bullet is a metadata annotation
TASKS_MD_WITH_METADATA_FIRST = """\
- [ ] 1. Some group

  - [ ] 1.1 Create the config dataclass
    - _Requirements: 93-REQ-1.1_
    - Create the config dataclass
"""

# tasks.md where ALL bullets are metadata annotations
TASKS_MD_ALL_METADATA = """\
- [ ] 3. Metadata only group

  - [ ] 3.1 Some subtask
    - _Requirements: 94-REQ-1.1_
    - _Test Spec: TS-94-1_
"""


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_fact(id: str, spec_name: str = "test_spec") -> Fact:
    """Create a minimal Fact for testing."""
    return Fact(
        id=id,
        content=f"Fact content {id}",
        category="pattern",
        spec_name=spec_name,
        keywords=[],
        confidence=0.9,
        created_at="2026-01-01T00:00:00Z",
    )


def _make_search_result(fact_id: str, spec_name: str = "other_spec") -> SearchResult:
    """Create a minimal SearchResult for testing."""
    return SearchResult(
        fact_id=fact_id,
        content=f"Search result content {fact_id}",
        category="pattern",
        spec_name=spec_name,
        session_id=None,
        commit_sha=None,
        similarity=0.85,
    )


def _make_runner(
    embedder: EmbeddingGenerator | None = None,
    config: AgentFoxConfig | None = None,
) -> NodeSessionRunner:
    """Create a NodeSessionRunner with optional embedder (fails until group 3 impl)."""
    cfg = config or AgentFoxConfig()
    return NodeSessionRunner(
        "12_rate_limiting:2",
        cfg,
        knowledge_db=_MOCK_KB,
        embedder=embedder,
    )


# ---------------------------------------------------------------------------
# TS-94-1: Extract subtask descriptions from task group
# Requirements: 94-REQ-1.1
# ---------------------------------------------------------------------------


def test_extract_subtask_descriptions(tmp_path: Path) -> None:
    """TS-94-1: First non-metadata bullet extracted from each subtask."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_CONTENT)

    result = session_lifecycle.extract_subtask_descriptions(spec_dir, 2)

    assert result == ["Add `push_fix_branch` field", "Modify branch naming function"]


# ---------------------------------------------------------------------------
# TS-94-2: Skip metadata bullets during extraction
# Requirements: 94-REQ-1.2
# ---------------------------------------------------------------------------


def test_skip_metadata_bullets(tmp_path: Path) -> None:
    """TS-94-2: Bullets starting with '_' are skipped; next non-metadata captured."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_WITH_METADATA_FIRST)

    result = session_lifecycle.extract_subtask_descriptions(spec_dir, 1)

    assert result == ["Create the config dataclass"]


# ---------------------------------------------------------------------------
# TS-94-3: Concatenate descriptions and embed
# Requirements: 94-REQ-2.1
# ---------------------------------------------------------------------------


def test_concatenate_and_embed(tmp_path: Path) -> None:
    """TS-94-3: Descriptions joined with newlines before embedding."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_CONTENT)

    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.embed_text.return_value = [0.1, 0.2, 0.3]

    runner = _make_runner(embedder=mock_embedder)

    with patch("agent_fox.engine.session_lifecycle.VectorSearch") as vs_cls:
        mock_vs = MagicMock()
        mock_vs.search.return_value = []
        vs_cls.return_value = mock_vs
        runner._retrieve_cross_spec_facts(spec_dir, [])

    mock_embedder.embed_text.assert_called_once_with("Add `push_fix_branch` field\nModify branch naming function")


# ---------------------------------------------------------------------------
# TS-94-4: Vector search uses configured top_k
# Requirements: 94-REQ-2.2
# ---------------------------------------------------------------------------


def test_vector_search_uses_configured_top_k(tmp_path: Path) -> None:
    """TS-94-4: VectorSearch.search called with top_k=10 and exclude_superseded=True."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_CONTENT)

    knowledge_config = KnowledgeConfig(cross_spec_top_k=10)
    config = AgentFoxConfig(knowledge=knowledge_config)

    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.embed_text.return_value = [0.1, 0.2, 0.3]

    runner = NodeSessionRunner(
        "12_rate_limiting:2",
        config,
        knowledge_db=_MOCK_KB,
        embedder=mock_embedder,
    )

    with patch("agent_fox.engine.session_lifecycle.VectorSearch") as vs_cls:
        mock_vs = MagicMock()
        mock_vs.search.return_value = []
        vs_cls.return_value = mock_vs
        runner._retrieve_cross_spec_facts(spec_dir, [])

    mock_vs.search.assert_called_once()
    call_args = mock_vs.search.call_args
    assert call_args.kwargs.get("top_k") == 10
    assert call_args.kwargs.get("exclude_superseded") is True


# ---------------------------------------------------------------------------
# TS-94-5: Merge cross-spec facts with spec-specific facts
# Requirements: 94-REQ-3.1
# ---------------------------------------------------------------------------


def test_merge_deduplicates() -> None:
    """TS-94-5: Cross-spec results merged; duplicate IDs kept from spec-specific set."""
    spec_facts = [_make_fact("aaa"), _make_fact("bbb")]
    cross_results = [
        _make_search_result("bbb"),
        _make_search_result("ccc"),
    ]

    merged = session_lifecycle.merge_cross_spec_facts(spec_facts, cross_results)

    assert len(merged) == 3
    assert [f.id for f in merged] == ["aaa", "bbb", "ccc"]


# ---------------------------------------------------------------------------
# TS-94-6: Merge happens before causal enhancement
# Requirements: 94-REQ-3.2
# ---------------------------------------------------------------------------


def test_merge_before_causal(tmp_path: Path) -> None:
    """TS-94-6: _enhance_with_causal receives both spec-specific and cross-spec facts."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_CONTENT)

    fact_aaa = _make_fact("aaa", spec_name="12_rate_limiting")
    fact_ccc = _make_fact("ccc", spec_name="03_auth")

    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.embed_text.return_value = [0.1, 0.2, 0.3]

    runner = _make_runner(embedder=mock_embedder)

    causal_input: list[Fact] = []

    def capture_causal(facts: list[Fact]) -> list[str]:
        causal_input.extend(facts)
        return [f.content for f in facts]

    with (
        patch.object(runner, "_load_relevant_facts", return_value=[fact_aaa]),
        patch.object(
            runner,
            "_retrieve_cross_spec_facts",
            return_value=[fact_aaa, fact_ccc],
            create=True,
        ),
        patch.object(runner, "_enhance_with_causal", side_effect=capture_causal),
        patch("agent_fox.session.prompt.assemble_context", return_value="context"),
        patch("agent_fox.session.prompt.build_system_prompt", return_value="sys"),
        patch("agent_fox.session.prompt.build_task_prompt", return_value="task"),
    ):
        runner._build_prompts(tmp_path, attempt=1, previous_error=None)

    assert {f.id for f in causal_input} == {"aaa", "ccc"}


# ---------------------------------------------------------------------------
# TS-94-7: Config field cross_spec_top_k default value
# Requirements: 94-REQ-4.1
# ---------------------------------------------------------------------------


def test_config_default() -> None:
    """TS-94-7: KnowledgeConfig.cross_spec_top_k defaults to 15."""
    config = KnowledgeConfig()
    assert config.cross_spec_top_k == 15


# ---------------------------------------------------------------------------
# TS-94-8: cross_spec_top_k zero disables retrieval
# Requirements: 94-REQ-4.2
# ---------------------------------------------------------------------------


def test_top_k_zero_disables(tmp_path: Path) -> None:
    """TS-94-8: cross_spec_top_k=0 skips cross-spec retrieval entirely."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_CONTENT)

    knowledge_config = KnowledgeConfig(cross_spec_top_k=0)
    config = AgentFoxConfig(knowledge=knowledge_config)
    mock_embedder = MagicMock(spec=EmbeddingGenerator)

    runner = NodeSessionRunner(
        "12_rate_limiting:2",
        config,
        knowledge_db=_MOCK_KB,
        embedder=mock_embedder,
    )

    spec_facts = [_make_fact("aaa")]
    result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)

    assert result == spec_facts
    mock_embedder.embed_text.assert_not_called()


# ---------------------------------------------------------------------------
# TS-94-9: Embedder passed through factory
# Requirements: 94-REQ-6.1
# ---------------------------------------------------------------------------


def test_factory_passes_embedder() -> None:
    """TS-94-9: session_runner_factory creates EmbeddingGenerator and passes it."""
    from agent_fox.engine.run import _setup_infrastructure

    config = AgentFoxConfig()
    mock_kb = MagicMock(spec=KnowledgeDB)
    mock_kb.connection = MagicMock()
    mock_embedder_instance = MagicMock(spec=EmbeddingGenerator)

    with (
        patch("agent_fox.engine.run.open_knowledge_store", return_value=mock_kb),
        patch("agent_fox.engine.run.DuckDBSink"),
        patch("agent_fox.engine.run.run_background_ingestion"),
        patch(
            "agent_fox.knowledge.embeddings.EmbeddingGenerator",
            return_value=mock_embedder_instance,
        ),
    ):
        infra = _setup_infrastructure(config)
        factory = infra["session_runner_factory"]
        runner = factory("12_rate_limiting:2", archetype="coder")

    assert runner._embedder is not None


# ---------------------------------------------------------------------------
# TS-94-10: No embedder skips retrieval
# Requirements: 94-REQ-6.2
# ---------------------------------------------------------------------------


def test_no_embedder_skips(tmp_path: Path) -> None:
    """TS-94-10: NodeSessionRunner with embedder=None skips cross-spec retrieval."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_CONTENT)

    runner = NodeSessionRunner(
        "12_rate_limiting:2",
        AgentFoxConfig(),
        knowledge_db=_MOCK_KB,
        embedder=None,
    )

    spec_facts = [_make_fact("aaa")]
    result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)

    assert result == spec_facts


# ---------------------------------------------------------------------------
# TS-94-E1: tasks.md does not exist
# Requirements: 94-REQ-1.E1
# ---------------------------------------------------------------------------


def test_missing_tasks_md(tmp_path: Path) -> None:
    """TS-94-E1: Missing tasks.md → empty list, cross-spec retrieval skipped."""
    spec_dir = tmp_path / "empty_spec"
    spec_dir.mkdir()

    result = session_lifecycle.extract_subtask_descriptions(spec_dir, 2)

    assert result == []


# ---------------------------------------------------------------------------
# TS-94-E2: Task group not found in tasks.md
# Requirements: 94-REQ-1.E2
# ---------------------------------------------------------------------------


def test_group_not_found(tmp_path: Path) -> None:
    """TS-94-E2: Group 5 not in tasks.md (only 1 and 2) → empty list."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_CONTENT)

    result = session_lifecycle.extract_subtask_descriptions(spec_dir, 5)

    assert result == []


# ---------------------------------------------------------------------------
# TS-94-E3: Subtasks with only metadata bullets
# Requirements: 94-REQ-1.E2
# ---------------------------------------------------------------------------


def test_metadata_only_bullets(tmp_path: Path) -> None:
    """TS-94-E3: All subtask bullets are metadata annotations → empty list."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_ALL_METADATA)

    result = session_lifecycle.extract_subtask_descriptions(spec_dir, 3)

    assert result == []


# ---------------------------------------------------------------------------
# TS-94-E4: embed_text returns None
# Requirements: 94-REQ-2.E1
# ---------------------------------------------------------------------------


def test_embed_returns_none(tmp_path: Path) -> None:
    """TS-94-E4: embed_text returns None → spec-specific facts returned unchanged."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_CONTENT)

    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.embed_text.return_value = None

    runner = _make_runner(embedder=mock_embedder)
    spec_facts = [_make_fact("aaa")]
    result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)

    assert result == spec_facts


# ---------------------------------------------------------------------------
# TS-94-E5: All search results are duplicates
# Requirements: 94-REQ-3.E1
# ---------------------------------------------------------------------------


def test_all_results_duplicates() -> None:
    """TS-94-E5: All cross-spec results are already in spec set → unchanged."""
    spec_facts = [_make_fact("aaa"), _make_fact("bbb")]
    cross_results = [
        _make_search_result("aaa"),
        _make_search_result("bbb"),
    ]

    merged = session_lifecycle.merge_cross_spec_facts(spec_facts, cross_results)

    assert len(merged) == 2
    assert merged == spec_facts


# ---------------------------------------------------------------------------
# TS-94-E6: Vector search returns empty list
# Requirements: 94-REQ-2.E2
# ---------------------------------------------------------------------------


def test_search_returns_empty(tmp_path: Path) -> None:
    """TS-94-E6: Empty vector search results → spec-specific facts unchanged."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_CONTENT)

    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.embed_text.return_value = [0.1, 0.2, 0.3]

    runner = _make_runner(embedder=mock_embedder)
    spec_facts = [_make_fact("aaa")]

    with patch("agent_fox.engine.session_lifecycle.VectorSearch") as vs_cls:
        mock_vs = MagicMock()
        mock_vs.search.return_value = []
        vs_cls.return_value = mock_vs
        result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)

    assert result == spec_facts


# ---------------------------------------------------------------------------
# TS-94-E7: Exception during retrieval
# Requirements: 94-REQ-5.1
# ---------------------------------------------------------------------------


def test_exception_graceful_degradation(tmp_path: Path) -> None:
    """TS-94-E7: Exception in pipeline → spec-specific facts returned, no propagation."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "tasks.md").write_text(TASKS_MD_CONTENT)

    mock_embedder = MagicMock(spec=EmbeddingGenerator)
    mock_embedder.embed_text.side_effect = RuntimeError("model load failed")

    runner = _make_runner(embedder=mock_embedder)
    spec_facts = [_make_fact("aaa")]
    result = runner._retrieve_cross_spec_facts(spec_dir, spec_facts)

    assert result == spec_facts
