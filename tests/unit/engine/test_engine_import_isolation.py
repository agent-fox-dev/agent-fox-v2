"""Import isolation, module deletion, config cleanup, and CLI tests.

Verifies that engine modules do not import deleted knowledge internals,
that deleted files/directories are gone, that config classes are cleaned up,
and that CLI commands are updated.

Test Spec: TS-114-10, TS-114-13, TS-114-14, TS-114-15,
           TS-114-17 through TS-114-20, TS-114-20b,
           TS-114-21 through TS-114-25,
           TS-114-26 through TS-114-34, TS-114-38,
           TS-114-E5 through TS-114-E8
Requirements: 114-REQ-3.2, 114-REQ-4.2, 114-REQ-4.3, 114-REQ-5.1,
              114-REQ-6.1 through 114-REQ-6.5,
              114-REQ-7.1 through 114-REQ-7.5,
              114-REQ-8.1 through 114-REQ-8.5,
              114-REQ-9.1 through 114-REQ-9.4,
              114-REQ-10.4
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Repository root for file existence checks
_REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# TS-114-10: Engine Does Not Import Deleted Retrieval Modules
# ---------------------------------------------------------------------------


class TestNoRetrievalImports:
    """Verify engine modules do not import banned retrieval names.

    Requirements: 114-REQ-3.2
    """

    BANNED = {"AdaptiveRetriever", "EmbeddingGenerator", "VectorSearch", "RetrievalConfig"}

    def test_engine_files_clean(self) -> None:
        """No engine module imports banned retrieval names."""
        engine_dir = _REPO_ROOT / "agent_fox" / "engine"
        for py_file in sorted(engine_dir.glob("*.py")):
            source = py_file.read_text(encoding="utf-8")
            for name in self.BANNED:
                assert name not in source, (
                    f"Banned name {name!r} found in {py_file.name}"
                )


# ---------------------------------------------------------------------------
# TS-114-13: Engine Does Not Import Deleted Extraction Modules
# ---------------------------------------------------------------------------


class TestNoExtractionImports:
    """Verify engine modules do not import banned extraction/harvest names.

    Requirements: 114-REQ-4.2

    Note: The banned set includes extract_and_store_knowledge and
    run_background_ingestion per the design doc Property 4, addressing
    the major finding that REQ-4.2's list was incomplete.
    """

    BANNED = {
        "extract_session_facts",
        "extract_tool_calls",
        "store_causal_links",
        "dedup_new_facts",
        "detect_contradictions",
        "extract_and_store_knowledge",
        "run_background_ingestion",
        "extract_facts",
        "load_all_facts",
    }

    def test_engine_files_clean(self) -> None:
        """No engine module imports banned extraction names."""
        engine_dir = _REPO_ROOT / "agent_fox" / "engine"
        for py_file in sorted(engine_dir.glob("*.py")):
            source = py_file.read_text(encoding="utf-8")
            for name in self.BANNED:
                assert name not in source, (
                    f"Banned name {name!r} found in {py_file.name}"
                )


# ---------------------------------------------------------------------------
# TS-114-14 / TS-114-24: knowledge_harvest.py Deleted
# ---------------------------------------------------------------------------


class TestHarvestDeleted:
    """Verify knowledge_harvest.py no longer exists.

    Requirements: 114-REQ-4.3, 114-REQ-7.4
    """

    def test_file_does_not_exist(self) -> None:
        assert not (_REPO_ROOT / "agent_fox" / "engine" / "knowledge_harvest.py").exists()


# ---------------------------------------------------------------------------
# TS-114-15: Barrier Does Not Import Removed Components
# ---------------------------------------------------------------------------


class TestBarrierNoRemovedImports:
    """Verify barrier.py does not import or call removed components.

    Requirements: 114-REQ-5.1
    """

    BANNED = {
        "run_consolidation",
        "compact",
        "SleepComputer",
        "SleepContext",
        "BundleBuilder",
        "ContextRewriter",
        "run_cleanup",
        "render_summary",
    }

    def test_barrier_source_clean(self) -> None:
        """barrier.py source does not contain banned names."""
        barrier_path = _REPO_ROOT / "agent_fox" / "engine" / "barrier.py"
        source = barrier_path.read_text(encoding="utf-8")
        for name in self.BANNED:
            assert name not in source, (
                f"Banned name {name!r} found in barrier.py"
            )


# ---------------------------------------------------------------------------
# TS-114-17: Nightshift No EmbeddingGenerator Import
# ---------------------------------------------------------------------------


class TestNightshiftNoEmbeddings:
    """Verify nightshift modules do not import EmbeddingGenerator.

    Requirements: 114-REQ-6.1
    """

    def test_no_embedding_generator_in_nightshift(self) -> None:
        nightshift_dir = _REPO_ROOT / "agent_fox" / "nightshift"
        for py_file in sorted(nightshift_dir.glob("*.py")):
            source = py_file.read_text(encoding="utf-8")
            # Allow TYPE_CHECKING-only imports
            lines = source.split("\n")
            in_type_checking = False
            for line in lines:
                stripped = line.strip()
                if stripped == "if TYPE_CHECKING:":
                    in_type_checking = True
                    continue
                if in_type_checking and not stripped.startswith(("from ", "import ", "#", "")):
                    in_type_checking = False
                if in_type_checking:
                    continue
                assert "EmbeddingGenerator" not in line, (
                    f"Runtime EmbeddingGenerator reference in {py_file.name}"
                )


# ---------------------------------------------------------------------------
# TS-114-18: Nightshift No Sleep Compute Imports
# ---------------------------------------------------------------------------


class TestNightshiftNoSleepImports:
    """Verify nightshift modules do not import sleep compute classes.

    Requirements: 114-REQ-6.2
    """

    BANNED = {"SleepComputer", "SleepContext", "BundleBuilder", "ContextRewriter"}

    def test_no_sleep_compute_in_nightshift(self) -> None:
        nightshift_dir = _REPO_ROOT / "agent_fox" / "nightshift"
        for py_file in sorted(nightshift_dir.glob("*.py")):
            source = py_file.read_text(encoding="utf-8")
            for name in self.BANNED:
                assert name not in source, (
                    f"Banned name {name!r} found in nightshift/{py_file.name}"
                )


# ---------------------------------------------------------------------------
# TS-114-19: Nightshift No Sleep Compute Stream
# ---------------------------------------------------------------------------


class TestNightshiftNoSleepStream:
    """Verify streams.py does not contain a sleep compute work stream.

    Requirements: 114-REQ-6.3
    """

    def test_no_sleep_compute_stream(self) -> None:
        streams_path = _REPO_ROOT / "agent_fox" / "nightshift" / "streams.py"
        source = streams_path.read_text(encoding="utf-8")
        assert "SleepComputeStream" not in source
        assert "sleep_compute" not in source
        assert "sleep-compute" not in source


# ---------------------------------------------------------------------------
# TS-114-20: Nightshift Ingest/Dedup/Filter No Removed Imports
# ---------------------------------------------------------------------------


class TestNightshiftDedupFilter:
    """Verify dedup.py and ignore_filter.py do not import
    from removed knowledge modules.

    Requirements: 114-REQ-6.4
    """

    BANNED_MODULES = {"knowledge.facts", "knowledge.store", "knowledge.extraction",
                      "knowledge.embeddings", "knowledge.git_mining"}

    def test_no_removed_imports(self) -> None:
        nightshift_dir = _REPO_ROOT / "agent_fox" / "nightshift"
        for filename in ["dedup.py", "ignore_filter.py"]:
            filepath = nightshift_dir / filename
            if not filepath.exists():
                continue
            source = filepath.read_text(encoding="utf-8")
            lines = source.split("\n")
            in_type_checking = False
            for line in lines:
                stripped = line.strip()
                if stripped == "if TYPE_CHECKING:":
                    in_type_checking = True
                    continue
                if in_type_checking and not stripped.startswith(("from ", "import ", "#", "")):
                    in_type_checking = False
                if in_type_checking:
                    continue
                for mod in self.BANNED_MODULES:
                    assert mod not in line, (
                        f"Banned module {mod!r} found in {filename}: {line.strip()}"
                    )


# ---------------------------------------------------------------------------
# TS-114-21: Knowledge Module Files Deleted
# ---------------------------------------------------------------------------


class TestKnowledgeFilesDeleted:
    """Verify all listed knowledge module files are deleted.

    Requirements: 114-REQ-7.1
    """

    DELETED = [
        "extraction.py", "embeddings.py", "search.py", "retrieval.py",
        "causal.py", "lifecycle.py", "contradiction.py", "consolidation.py",
        "compaction.py", "entity_linker.py", "entity_query.py", "entity_store.py",
        "entities.py", "static_analysis.py", "git_mining.py", "doc_mining.py",
        "sleep_compute.py", "code_analysis.py", "onboard.py", "project_model.py",
        "query_oracle.py", "query_patterns.py", "query_temporal.py",
        "rendering.py", "store.py", "ingest.py", "facts.py",
    ]

    def test_files_do_not_exist(self) -> None:
        knowledge_dir = _REPO_ROOT / "agent_fox" / "knowledge"
        for name in self.DELETED:
            assert not (knowledge_dir / name).exists(), (
                f"Expected {name} to be deleted from agent_fox/knowledge/"
            )


# ---------------------------------------------------------------------------
# TS-114-22: Lang Directory Deleted
# ---------------------------------------------------------------------------


class TestLangDirDeleted:
    """Verify agent_fox/knowledge/lang/ directory is deleted.

    Requirements: 114-REQ-7.2
    """

    def test_lang_directory_gone(self) -> None:
        assert not (_REPO_ROOT / "agent_fox" / "knowledge" / "lang").exists()


# ---------------------------------------------------------------------------
# TS-114-23: Sleep Tasks Directory Deleted
# ---------------------------------------------------------------------------


class TestSleepTasksDirDeleted:
    """Verify agent_fox/knowledge/sleep_tasks/ directory is deleted.

    Requirements: 114-REQ-7.3
    """

    def test_sleep_tasks_directory_gone(self) -> None:
        assert not (_REPO_ROOT / "agent_fox" / "knowledge" / "sleep_tasks").exists()


# ---------------------------------------------------------------------------
# TS-114-25: Import Health After Deletions
# ---------------------------------------------------------------------------


class TestImportHealth:
    """Verify import agent_fox succeeds with zero import errors.

    Requirements: 114-REQ-7.5
    """

    def test_import_succeeds(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "import agent_fox"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"import agent_fox failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# TS-114-26: KnowledgeConfig Fields Removed
# ---------------------------------------------------------------------------


class TestConfigFieldsRemoved:
    """Verify removed fields are no longer present on KnowledgeConfig.

    Requirements: 114-REQ-8.1
    """

    REMOVED = {
        "embedding_model", "embedding_dimensions", "ask_top_k",
        "ask_synthesis_model", "dedup_similarity_threshold",
        "contradiction_similarity_threshold", "contradiction_model",
        "decay_half_life_days", "decay_floor", "cleanup_fact_threshold",
        "cleanup_enabled", "confidence_threshold", "fact_cache_enabled",
    }

    def test_fields_not_present(self) -> None:
        from agent_fox.core.config import KnowledgeConfig

        for field_name in self.REMOVED:
            assert field_name not in KnowledgeConfig.model_fields, (
                f"Removed field {field_name!r} still present on KnowledgeConfig"
            )


# ---------------------------------------------------------------------------
# TS-114-27: RetrievalConfig Deleted
# ---------------------------------------------------------------------------


class TestRetrievalConfigDeleted:
    """Verify RetrievalConfig no longer exists in config module.

    Requirements: 114-REQ-8.2
    """

    def test_no_retrieval_config(self) -> None:
        import agent_fox.core.config as cfg

        assert not hasattr(cfg, "RetrievalConfig")


# ---------------------------------------------------------------------------
# TS-114-28: SleepConfig Deleted
# ---------------------------------------------------------------------------


class TestSleepConfigDeleted:
    """Verify SleepConfig no longer exists in config module.

    Requirements: 114-REQ-8.3
    """

    def test_no_sleep_config(self) -> None:
        import agent_fox.core.config as cfg

        assert not hasattr(cfg, "SleepConfig")


# ---------------------------------------------------------------------------
# TS-114-29: KnowledgeConfig Retains store_path
# ---------------------------------------------------------------------------


class TestStorePathRetained:
    """Verify store_path field is still present on KnowledgeConfig.

    Requirements: 114-REQ-8.4
    """

    def test_store_path_exists(self) -> None:
        from agent_fox.core.config import KnowledgeConfig

        assert "store_path" in KnowledgeConfig.model_fields
        kc = KnowledgeConfig()
        assert kc.store_path == ".agent-fox/knowledge.duckdb"


# ---------------------------------------------------------------------------
# TS-114-30: Old Config Fields Ignored
# ---------------------------------------------------------------------------


class TestOldConfigIgnored:
    """Verify constructing KnowledgeConfig with old fields does not raise.

    Requirements: 114-REQ-8.5
    """

    def test_old_fields_silently_ignored(self) -> None:
        from agent_fox.core.config import KnowledgeConfig

        kc = KnowledgeConfig(embedding_model="foo", decay_half_life_days=30)  # type: ignore[call-arg]
        assert kc.store_path == ".agent-fox/knowledge.duckdb"
        assert not hasattr(kc, "embedding_model") or "embedding_model" not in kc.model_fields_set


# ---------------------------------------------------------------------------
# TS-114-31: Onboard CLI Removed
# ---------------------------------------------------------------------------


class TestOnboardRemoved:
    """Verify cli/onboard.py is deleted and unregistered from cli/app.py.

    Requirements: 114-REQ-9.1

    Note: Both the file deletion and the app.py import/registration removal
    are required, per the major finding about cli/app.py.
    """

    def test_onboard_file_deleted(self) -> None:
        assert not (_REPO_ROOT / "agent_fox" / "cli" / "onboard.py").exists()

    def test_onboard_not_in_app(self) -> None:
        app_path = _REPO_ROOT / "agent_fox" / "cli" / "app.py"
        source = app_path.read_text(encoding="utf-8")
        assert "onboard_cmd" not in source


# ---------------------------------------------------------------------------
# TS-114-32: CLI nightshift.py No EmbeddingGenerator
# ---------------------------------------------------------------------------


class TestCliNightshiftNoEmbeddings:
    """Verify cli/nightshift.py does not import EmbeddingGenerator.

    Requirements: 114-REQ-9.2
    """

    def test_no_embedding_generator(self) -> None:
        path = _REPO_ROOT / "agent_fox" / "cli" / "nightshift.py"
        source = path.read_text(encoding="utf-8")
        assert "EmbeddingGenerator" not in source


# ---------------------------------------------------------------------------
# TS-114-33: CLI status.py No Removed Imports
# ---------------------------------------------------------------------------


class TestCliStatusNoRemoved:
    """Verify cli/status.py does not import from project_model or knowledge.store.

    Requirements: 114-REQ-9.3
    """

    def test_no_project_model(self) -> None:
        path = _REPO_ROOT / "agent_fox" / "cli" / "status.py"
        source = path.read_text(encoding="utf-8")
        assert "project_model" not in source

    def test_no_knowledge_store(self) -> None:
        path = _REPO_ROOT / "agent_fox" / "cli" / "status.py"
        source = path.read_text(encoding="utf-8")
        assert "knowledge.store" not in source


# ---------------------------------------------------------------------------
# TS-114-34: CLI plan.py Still Functional
# ---------------------------------------------------------------------------


class TestCliPlanFunctional:
    """Verify cli/plan.py uses open_knowledge_store without removed modules.

    Requirements: 114-REQ-9.4
    """

    BANNED = {"knowledge.retrieval", "knowledge.extraction", "knowledge.embeddings",
              "knowledge.store", "knowledge.facts"}

    def test_has_open_knowledge_store(self) -> None:
        path = _REPO_ROOT / "agent_fox" / "cli" / "plan.py"
        source = path.read_text(encoding="utf-8")
        assert "open_knowledge_store" in source

    def test_no_banned_imports(self) -> None:
        path = _REPO_ROOT / "agent_fox" / "cli" / "plan.py"
        source = path.read_text(encoding="utf-8")
        for mod in self.BANNED:
            assert mod not in source, (
                f"Banned module {mod!r} found in cli/plan.py"
            )


# ---------------------------------------------------------------------------
# TS-114-38: Dead Test Files Deleted
# ---------------------------------------------------------------------------


class TestDeadTestsDeleted:
    """Verify test files that exclusively test removed functionality are deleted.

    Requirements: 114-REQ-10.4
    """

    DELETED_TESTS = [
        "tests/unit/knowledge/test_extraction.py",
        "tests/unit/knowledge/test_embeddings.py",
        "tests/unit/knowledge/test_adaptive_retrieval.py",
        "tests/unit/knowledge/test_consolidation.py",
        "tests/unit/knowledge/test_compaction.py",
        "tests/unit/knowledge/test_sleep_compute.py",
        "tests/unit/knowledge/test_entity_linker.py",
        "tests/unit/knowledge/test_entity_query.py",
        "tests/unit/knowledge/test_entity_store.py",
        "tests/unit/knowledge/test_contradiction.py",
        "tests/unit/knowledge/test_lifecycle.py",
        "tests/unit/engine/test_knowledge_harvest.py",
    ]

    def test_dead_tests_removed(self) -> None:
        for path_str in self.DELETED_TESTS:
            full_path = _REPO_ROOT / path_str
            assert not full_path.exists(), (
                f"Dead test file {path_str} should be deleted"
            )


# ---------------------------------------------------------------------------
# TS-114-E5: Barrier With Old Knowledge Tables
# ---------------------------------------------------------------------------


class TestBarrierOldTables:
    """Verify barrier runs without accessing old knowledge tables.

    Requirements: 114-REQ-5.E1
    """

    def test_barrier_does_not_reference_old_tables(self) -> None:
        """Barrier source does not query memory_facts, entity_graph, etc."""
        barrier_path = _REPO_ROOT / "agent_fox" / "engine" / "barrier.py"
        source = barrier_path.read_text(encoding="utf-8")
        old_tables = ["memory_facts", "entity_graph", "sleep_artifacts"]
        for table in old_tables:
            assert table not in source, (
                f"Old table {table!r} referenced in barrier.py"
            )


# ---------------------------------------------------------------------------
# TS-114-E6: Nightshift With Old Sleep Artifacts
# ---------------------------------------------------------------------------


class TestNightshiftOldArtifacts:
    """Verify nightshift streams don't reference sleep-compute.

    Requirements: 114-REQ-6.E1
    """

    def test_no_sleep_compute_stream_in_registry(self) -> None:
        """No sleep-compute stream is created by build_streams."""
        streams_path = _REPO_ROOT / "agent_fox" / "nightshift" / "streams.py"
        source = streams_path.read_text(encoding="utf-8")
        assert "sleep-compute" not in source
        assert "sleep_artifacts" not in source


# ---------------------------------------------------------------------------
# TS-114-E7: Test Files for Removed Modules Updated
# ---------------------------------------------------------------------------


class TestNoTestImportsDeleted:
    """Verify no remaining test file imports a deleted module.

    Requirements: 114-REQ-7.E1
    """

    DELETED_MODULES = [
        "agent_fox.knowledge.extraction",
        "agent_fox.knowledge.embeddings",
        "agent_fox.knowledge.search",
        "agent_fox.knowledge.retrieval",
        "agent_fox.knowledge.causal",
        "agent_fox.knowledge.lifecycle",
        "agent_fox.knowledge.contradiction",
        "agent_fox.knowledge.consolidation",
        "agent_fox.knowledge.compaction",
        "agent_fox.knowledge.entity_linker",
        "agent_fox.knowledge.entity_query",
        "agent_fox.knowledge.entity_store",
        "agent_fox.knowledge.entities",
        "agent_fox.knowledge.static_analysis",
        "agent_fox.knowledge.sleep_compute",
        "agent_fox.knowledge.rendering",
        "agent_fox.knowledge.store",
        "agent_fox.knowledge.facts",
        "agent_fox.knowledge.ingest",
        "agent_fox.knowledge.onboard",
        "agent_fox.engine.knowledge_harvest",
    ]

    def test_no_deleted_module_imports_in_tests(self) -> None:
        tests_dir = _REPO_ROOT / "tests"
        # Exclude this file (it contains the module names as test data)
        this_file = Path(__file__).resolve()
        for py_file in sorted(tests_dir.rglob("*.py")):
            if py_file.resolve() == this_file:
                continue
            source = py_file.read_text(encoding="utf-8")
            rel = py_file.relative_to(_REPO_ROOT)
            for mod in self.DELETED_MODULES:
                assert mod not in source, (
                    f"Deleted module {mod!r} imported in {rel}"
                )


# ---------------------------------------------------------------------------
# TS-114-E8: Removed CLI Command Feedback
# ---------------------------------------------------------------------------


class TestRemovedCliFeedback:
    """Verify invoking a removed CLI command produces a clear error.

    Requirements: 114-REQ-9.E1
    """

    def test_onboard_command_not_found(self) -> None:
        """The onboard command is no longer registered."""
        from click.testing import CliRunner

        from agent_fox.cli.app import main

        runner = CliRunner()
        result = runner.invoke(main, ["onboard"])
        assert result.exit_code != 0
        # Click reports "No such command" for unregistered commands
        assert "no such command" in result.output.lower()
