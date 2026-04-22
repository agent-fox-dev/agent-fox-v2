# Test Specification: Knowledge System Decoupling

## Overview

Tests verify that the knowledge system is cleanly decoupled: the
`KnowledgeProvider` protocol is correctly defined, `NoOpKnowledgeProvider`
satisfies it, engine modules only use the protocol (never deleted internals),
all removed files are gone, configuration ignores old fields, and the full
import tree is healthy.

Test cases map 1:1 to requirements and correctness properties from the
requirements and design documents.

## Test Cases

### TS-114-1: KnowledgeProvider Protocol Definition

**Requirement:** 114-REQ-1.1
**Type:** unit
**Description:** Verify `KnowledgeProvider` is defined in `provider.py` with
both `ingest` and `retrieve` methods having correct signatures.

**Preconditions:**
- `agent_fox.knowledge.provider` module is importable.

**Input:**
- Import `KnowledgeProvider` from `agent_fox.knowledge.provider`.

**Expected:**
- `KnowledgeProvider` has an `ingest` method accepting `(self, session_id: str, spec_name: str, context: dict) -> None`.
- `KnowledgeProvider` has a `retrieve` method accepting `(self, spec_name: str, task_description: str) -> list[str]`.

**Assertion pseudocode:**
```
import inspect
from agent_fox.knowledge.provider import KnowledgeProvider

ingest_sig = inspect.signature(KnowledgeProvider.ingest)
ASSERT list(ingest_sig.parameters.keys()) == ["self", "session_id", "spec_name", "context"]
ASSERT ingest_sig.return_annotation == None

retrieve_sig = inspect.signature(KnowledgeProvider.retrieve)
ASSERT list(retrieve_sig.parameters.keys()) == ["self", "spec_name", "task_description"]
ASSERT retrieve_sig.return_annotation == list[str]
```

### TS-114-2: KnowledgeProvider Is runtime_checkable

**Requirement:** 114-REQ-1.2
**Type:** unit
**Description:** Verify `KnowledgeProvider` is decorated with
`@runtime_checkable`.

**Preconditions:**
- `agent_fox.knowledge.provider` module is importable.

**Input:**
- Import `KnowledgeProvider`.

**Expected:**
- `isinstance()` checks work against `KnowledgeProvider`.

**Assertion pseudocode:**
```
from agent_fox.knowledge.provider import KnowledgeProvider
from typing import runtime_checkable

ASSERT hasattr(KnowledgeProvider, "__protocol_attrs__") OR
       KnowledgeProvider.__protocol_attrs__ is accessible
# Verify runtime_checkable by testing isinstance with a conforming class
class Dummy:
    def ingest(self, session_id, spec_name, context): pass
    def retrieve(self, spec_name, task_description): return []
ASSERT isinstance(Dummy(), KnowledgeProvider) == True
```

### TS-114-3: Retrieve Returns list[str]

**Requirement:** 114-REQ-1.3
**Type:** unit
**Description:** Verify `retrieve()` return type annotation is `list[str]`.

**Preconditions:**
- `agent_fox.knowledge.provider` module is importable.

**Input:**
- Inspect `KnowledgeProvider.retrieve` return annotation.

**Expected:**
- Return annotation is `list[str]`.

**Assertion pseudocode:**
```
import inspect
from agent_fox.knowledge.provider import KnowledgeProvider

sig = inspect.signature(KnowledgeProvider.retrieve)
ASSERT sig.return_annotation == list[str]
```

### TS-114-4: Ingest Accepts Context Dict and Returns None

**Requirement:** 114-REQ-1.4
**Type:** unit
**Description:** Verify `ingest()` accepts a context dict and returns None.

**Preconditions:**
- `agent_fox.knowledge.provider` module is importable.

**Input:**
- Inspect `KnowledgeProvider.ingest` signature.

**Expected:**
- `context` parameter is annotated as `dict`.
- Return annotation is `None`.

**Assertion pseudocode:**
```
import inspect
from agent_fox.knowledge.provider import KnowledgeProvider

sig = inspect.signature(KnowledgeProvider.ingest)
ASSERT sig.parameters["context"].annotation == dict
ASSERT sig.return_annotation == None
```

### TS-114-5: NoOpKnowledgeProvider Satisfies Protocol

**Requirement:** 114-REQ-2.1
**Type:** unit
**Description:** Verify `NoOpKnowledgeProvider` passes `isinstance` check
against `KnowledgeProvider`.

**Preconditions:**
- Both classes importable from `agent_fox.knowledge.provider`.

**Input:**
- Instantiate `NoOpKnowledgeProvider`.

**Expected:**
- `isinstance(noop, KnowledgeProvider)` is True.

**Assertion pseudocode:**
```
from agent_fox.knowledge.provider import KnowledgeProvider, NoOpKnowledgeProvider

noop = NoOpKnowledgeProvider()
ASSERT isinstance(noop, KnowledgeProvider) == True
```

### TS-114-6: NoOp Ingest Is a No-Op

**Requirement:** 114-REQ-2.2
**Type:** unit
**Description:** Verify `NoOpKnowledgeProvider.ingest()` returns None without
side effects.

**Preconditions:**
- `NoOpKnowledgeProvider` is instantiated.

**Input:**
- Call `ingest("session-1", "spec_01", {"touched_files": [], "commit_sha": "", "session_status": "completed"})`.

**Expected:**
- Return value is None.

**Assertion pseudocode:**
```
from agent_fox.knowledge.provider import NoOpKnowledgeProvider

noop = NoOpKnowledgeProvider()
result = noop.ingest("session-1", "spec_01", {"touched_files": [], "commit_sha": "", "session_status": "completed"})
ASSERT result is None
```

### TS-114-7: NoOp Retrieve Returns Empty List

**Requirement:** 114-REQ-2.3
**Type:** unit
**Description:** Verify `NoOpKnowledgeProvider.retrieve()` returns `[]`.

**Preconditions:**
- `NoOpKnowledgeProvider` is instantiated.

**Input:**
- Call `retrieve("spec_01", "implement feature X")`.

**Expected:**
- Return value is `[]`.

**Assertion pseudocode:**
```
from agent_fox.knowledge.provider import NoOpKnowledgeProvider

noop = NoOpKnowledgeProvider()
result = noop.retrieve("spec_01", "implement feature X")
ASSERT result == []
ASSERT isinstance(result, list)
```

### TS-114-8: Engine Uses NoOp as Default Provider

**Requirement:** 114-REQ-2.4
**Type:** integration
**Description:** Verify the engine infrastructure setup creates a
`NoOpKnowledgeProvider` when no other provider is configured.

**Preconditions:**
- Default `AgentFoxConfig` with no custom provider configuration.

**Input:**
- Call `_setup_infrastructure(config)` with default config.

**Expected:**
- The returned infrastructure dict contains a `knowledge_provider` that is
  an instance of `NoOpKnowledgeProvider`.

**Assertion pseudocode:**
```
from agent_fox.knowledge.provider import KnowledgeProvider, NoOpKnowledgeProvider

infra = _setup_infrastructure(default_config)
ASSERT isinstance(infra["knowledge_provider"], KnowledgeProvider)
ASSERT isinstance(infra["knowledge_provider"], NoOpKnowledgeProvider)
```

### TS-114-9: Engine Calls retrieve() Pre-Session

**Requirement:** 114-REQ-3.1
**Type:** unit
**Description:** Verify `_build_prompts` calls `knowledge_provider.retrieve()`
and includes returned strings in session context.

**Preconditions:**
- `NodeSessionRunner` with a mock `KnowledgeProvider` that returns
  `["fact block 1"]`.

**Input:**
- Call `_build_prompts(repo_root, attempt=1, previous_error=None)`.

**Expected:**
- Mock provider's `retrieve()` was called with `(spec_name, task_description)`.
- Returned string appears in the assembled context.

**Assertion pseudocode:**
```
mock_provider = MockKnowledgeProvider(retrieve_returns=["fact block 1"])
runner = NodeSessionRunner(..., knowledge_provider=mock_provider)
system_prompt, task_prompt = runner._build_prompts(repo_root, 1, None)
ASSERT mock_provider.retrieve_called == True
ASSERT mock_provider.retrieve_args == (spec_name, ANY_STRING)
```

### TS-114-10: Engine Does Not Import Deleted Retrieval Modules

**Requirement:** 114-REQ-3.2
**Type:** integration
**Description:** Verify engine modules do not import `AdaptiveRetriever`,
`EmbeddingGenerator`, `VectorSearch`, or `RetrievalConfig`.

**Preconditions:**
- All engine source files are accessible.

**Input:**
- Scan `agent_fox/engine/*.py` for import statements.

**Expected:**
- None of the banned names appear in any import statement.

**Assertion pseudocode:**
```
BANNED = {"AdaptiveRetriever", "EmbeddingGenerator", "VectorSearch", "RetrievalConfig"}
for file in glob("agent_fox/engine/*.py"):
    source = read(file)
    for name in BANNED:
        ASSERT name NOT IN source
```

### TS-114-11: Empty Retrieve Means No Knowledge Context

**Requirement:** 114-REQ-3.3
**Type:** unit
**Description:** Verify engine proceeds without knowledge context when
provider returns empty list.

**Preconditions:**
- `NodeSessionRunner` with `NoOpKnowledgeProvider` (returns `[]`).

**Input:**
- Call `_build_prompts(repo_root, attempt=1, previous_error=None)`.

**Expected:**
- Session context is assembled without `memory_facts`.

**Assertion pseudocode:**
```
runner = NodeSessionRunner(..., knowledge_provider=NoOpKnowledgeProvider())
system_prompt, task_prompt = runner._build_prompts(repo_root, 1, None)
# No crash; prompts are valid strings
ASSERT isinstance(system_prompt, str)
ASSERT len(system_prompt) > 0
```

### TS-114-12: Engine Calls ingest() Post-Session

**Requirement:** 114-REQ-4.1
**Type:** unit
**Description:** Verify `_ingest_knowledge` calls
`knowledge_provider.ingest()` once with correct arguments after session
completion.

**Preconditions:**
- `NodeSessionRunner` with a mock `KnowledgeProvider`.
- Simulated successful session with touched files and commit SHA.

**Input:**
- Call `_ingest_knowledge(node_id, touched_files, commit_sha, "completed")`.

**Expected:**
- Mock provider's `ingest()` called exactly once.
- Call args include `session_id`, `spec_name`, and a context dict containing
  `touched_files`, `commit_sha`, `session_status`.

**Assertion pseudocode:**
```
mock_provider = MockKnowledgeProvider()
runner = NodeSessionRunner(..., knowledge_provider=mock_provider)
runner._ingest_knowledge("spec_01:1", ["src/foo.py"], "abc123", "completed")
ASSERT mock_provider.ingest_call_count == 1
ctx = mock_provider.ingest_last_context
ASSERT "touched_files" in ctx
ASSERT "commit_sha" in ctx
ASSERT "session_status" in ctx
```

### TS-114-13: Engine Does Not Import Deleted Extraction Modules

**Requirement:** 114-REQ-4.2
**Type:** integration
**Description:** Verify engine modules do not import `extract_session_facts`,
`extract_tool_calls`, `store_causal_links`, `dedup_new_facts`, or
`detect_contradictions`.

**Preconditions:**
- All engine source files are accessible.

**Input:**
- Scan `agent_fox/engine/*.py` for banned import names.

**Expected:**
- None of the banned names appear.

**Assertion pseudocode:**
```
BANNED = {"extract_session_facts", "extract_tool_calls", "store_causal_links",
          "dedup_new_facts", "detect_contradictions", "extract_and_store_knowledge",
          "extract_facts", "load_all_facts"}
for file in glob("agent_fox/engine/*.py"):
    source = read(file)
    for name in BANNED:
        ASSERT name NOT IN source
```

### TS-114-14: knowledge_harvest.py Deleted

**Requirement:** 114-REQ-4.3
**Type:** unit
**Description:** Verify `knowledge_harvest.py` no longer exists.

**Preconditions:**
- None.

**Input:**
- Check file existence.

**Expected:**
- `agent_fox/engine/knowledge_harvest.py` does not exist.

**Assertion pseudocode:**
```
ASSERT NOT Path("agent_fox/engine/knowledge_harvest.py").exists()
```

### TS-114-15: Barrier Does Not Import Removed Components

**Requirement:** 114-REQ-5.1
**Type:** integration
**Description:** Verify `barrier.py` does not import or call consolidation,
compaction, sleep compute, or lifecycle cleanup.

**Preconditions:**
- `agent_fox/engine/barrier.py` is accessible.

**Input:**
- Read source of `barrier.py`.

**Expected:**
- No references to `run_consolidation`, `compact`, `SleepComputer`,
  `SleepContext`, `BundleBuilder`, `ContextRewriter`, `run_cleanup`.

**Assertion pseudocode:**
```
source = read("agent_fox/engine/barrier.py")
BANNED = {"run_consolidation", "compact", "SleepComputer", "SleepContext",
          "BundleBuilder", "ContextRewriter", "run_cleanup"}
for name in BANNED:
    ASSERT name NOT IN source
```

### TS-114-16: Barrier Still Runs Retained Steps

**Requirement:** 114-REQ-5.2
**Type:** unit
**Description:** Verify `run_sync_barrier_sequence` still executes worktree
verification, develop sync, hot-load, and barrier callback.

**Preconditions:**
- Mock functions for worktree verification, sync, hot-load, callback.

**Input:**
- Call `run_sync_barrier_sequence(...)` with mock dependencies.

**Expected:**
- All retained steps are called in order.
- No consolidation/compaction/sleep steps are attempted.

**Assertion pseudocode:**
```
mocks = setup_barrier_mocks()
await run_sync_barrier_sequence(**mocks)
ASSERT mocks.verify_worktrees.called
ASSERT mocks.sync_develop.called
ASSERT mocks.hot_load_fn.called
ASSERT mocks.barrier_callback.called
```

### TS-114-17: Nightshift No EmbeddingGenerator Import

**Requirement:** 114-REQ-6.1
**Type:** integration
**Description:** Verify nightshift modules do not import `EmbeddingGenerator`.

**Preconditions:**
- All nightshift source files are accessible.

**Input:**
- Scan `agent_fox/nightshift/*.py` for `EmbeddingGenerator`.

**Expected:**
- No references found.

**Assertion pseudocode:**
```
for file in glob("agent_fox/nightshift/*.py"):
    source = read(file)
    ASSERT "EmbeddingGenerator" NOT IN source
```

### TS-114-18: Nightshift No Sleep Compute Imports

**Requirement:** 114-REQ-6.2
**Type:** integration
**Description:** Verify nightshift modules do not import sleep compute classes.

**Preconditions:**
- All nightshift source files are accessible.

**Input:**
- Scan for `SleepComputer`, `SleepContext`, `BundleBuilder`, `ContextRewriter`.

**Expected:**
- No references found.

**Assertion pseudocode:**
```
BANNED = {"SleepComputer", "SleepContext", "BundleBuilder", "ContextRewriter"}
for file in glob("agent_fox/nightshift/*.py"):
    source = read(file)
    for name in BANNED:
        ASSERT name NOT IN source
```

### TS-114-19: Nightshift No Sleep Compute Stream

**Requirement:** 114-REQ-6.3
**Type:** integration
**Description:** Verify `streams.py` does not contain a sleep compute work stream class.

**Preconditions:**
- `agent_fox/nightshift/streams.py` is accessible.

**Input:**
- Read source of `streams.py`.

**Expected:**
- No class named `SleepComputeStream` or similar.
- No references to sleep compute pipeline.

**Assertion pseudocode:**
```
source = read("agent_fox/nightshift/streams.py")
ASSERT "SleepComputeStream" NOT IN source
ASSERT "sleep_compute" NOT IN source
ASSERT "sleep-compute" NOT IN source
```

### TS-114-20: Nightshift Ingest/Dedup/Filter No Removed Imports

**Requirement:** 114-REQ-6.4
**Type:** integration
**Description:** Verify `ignore_ingest.py`, `dedup.py`, and `ignore_filter.py`
do not import from removed knowledge modules.

**Preconditions:**
- All three files are accessible.

**Input:**
- Scan each file for imports from deleted modules.

**Expected:**
- No imports from `facts`, `store`, `extraction`, `embeddings`, `git_mining`.

**Assertion pseudocode:**
```
BANNED_MODULES = {"facts", "store", "extraction", "embeddings", "git_mining"}
for file in ["ignore_ingest.py", "dedup.py", "ignore_filter.py"]:
    source = read(f"agent_fox/nightshift/{file}")
    for mod in BANNED_MODULES:
        ASSERT f"knowledge.{mod}" NOT IN source
```

### TS-114-21: Knowledge Module Files Deleted

**Requirement:** 114-REQ-7.1
**Type:** unit
**Description:** Verify all listed knowledge module files are deleted.

**Preconditions:**
- None.

**Input:**
- Check existence of each file listed in REQ-7.1.

**Expected:**
- None of the listed files exist.

**Assertion pseudocode:**
```
DELETED = [
    "extraction.py", "embeddings.py", "search.py", "retrieval.py",
    "causal.py", "lifecycle.py", "contradiction.py", "consolidation.py",
    "compaction.py", "entity_linker.py", "entity_query.py", "entity_store.py",
    "entities.py", "static_analysis.py", "git_mining.py", "doc_mining.py",
    "sleep_compute.py", "code_analysis.py", "onboard.py", "project_model.py",
    "query_oracle.py", "query_patterns.py", "query_temporal.py",
    "rendering.py", "store.py", "ingest.py", "facts.py",
]
for name in DELETED:
    ASSERT NOT Path(f"agent_fox/knowledge/{name}").exists()
```

### TS-114-22: Lang Directory Deleted

**Requirement:** 114-REQ-7.2
**Type:** unit
**Description:** Verify `agent_fox/knowledge/lang/` directory is deleted.

**Preconditions:**
- None.

**Input:**
- Check directory existence.

**Expected:**
- Directory does not exist.

**Assertion pseudocode:**
```
ASSERT NOT Path("agent_fox/knowledge/lang").exists()
```

### TS-114-23: Sleep Tasks Directory Deleted

**Requirement:** 114-REQ-7.3
**Type:** unit
**Description:** Verify `agent_fox/knowledge/sleep_tasks/` directory is deleted.

**Preconditions:**
- None.

**Input:**
- Check directory existence.

**Expected:**
- Directory does not exist.

**Assertion pseudocode:**
```
ASSERT NOT Path("agent_fox/knowledge/sleep_tasks").exists()
```

### TS-114-24: knowledge_harvest.py Deleted (Engine)

**Requirement:** 114-REQ-7.4
**Type:** unit
**Description:** Verify `agent_fox/engine/knowledge_harvest.py` is deleted.
(Same check as TS-114-14, included for traceability to REQ-7.4.)

**Preconditions:**
- None.

**Input:**
- Check file existence.

**Expected:**
- File does not exist.

**Assertion pseudocode:**
```
ASSERT NOT Path("agent_fox/engine/knowledge_harvest.py").exists()
```

### TS-114-25: Import Health After Deletions

**Requirement:** 114-REQ-7.5
**Type:** integration
**Description:** Verify `import agent_fox` succeeds with zero import errors.

**Preconditions:**
- All deletions and import cleanups are applied.

**Input:**
- Run `python -c "import agent_fox"`.

**Expected:**
- Exit code 0, no ImportError.

**Assertion pseudocode:**
```
result = subprocess.run(["python", "-c", "import agent_fox"], capture_output=True)
ASSERT result.returncode == 0
```

### TS-114-26: KnowledgeConfig Fields Removed

**Requirement:** 114-REQ-8.1
**Type:** unit
**Description:** Verify removed fields are no longer present on
`KnowledgeConfig`.

**Preconditions:**
- `agent_fox.core.config` is importable.

**Input:**
- Inspect `KnowledgeConfig.model_fields`.

**Expected:**
- None of the removed fields are present.

**Assertion pseudocode:**
```
from agent_fox.core.config import KnowledgeConfig

REMOVED = {
    "embedding_model", "embedding_dimensions", "ask_top_k",
    "ask_synthesis_model", "dedup_similarity_threshold",
    "contradiction_similarity_threshold", "contradiction_model",
    "decay_half_life_days", "decay_floor", "cleanup_fact_threshold",
    "cleanup_enabled", "confidence_threshold", "fact_cache_enabled",
}
for field_name in REMOVED:
    ASSERT field_name NOT IN KnowledgeConfig.model_fields
```

### TS-114-27: RetrievalConfig Deleted

**Requirement:** 114-REQ-8.2
**Type:** unit
**Description:** Verify `RetrievalConfig` class no longer exists in config
module.

**Preconditions:**
- `agent_fox.core.config` is importable.

**Input:**
- Attempt to import `RetrievalConfig`.

**Expected:**
- `ImportError` or `AttributeError`.

**Assertion pseudocode:**
```
import agent_fox.core.config as cfg
ASSERT NOT hasattr(cfg, "RetrievalConfig")
```

### TS-114-28: SleepConfig Deleted

**Requirement:** 114-REQ-8.3
**Type:** unit
**Description:** Verify `SleepConfig` class no longer exists in config module.

**Preconditions:**
- `agent_fox.core.config` is importable.

**Input:**
- Attempt to access `SleepConfig`.

**Expected:**
- `AttributeError`.

**Assertion pseudocode:**
```
import agent_fox.core.config as cfg
ASSERT NOT hasattr(cfg, "SleepConfig")
```

### TS-114-29: KnowledgeConfig Retains store_path

**Requirement:** 114-REQ-8.4
**Type:** unit
**Description:** Verify `store_path` field is still present on
`KnowledgeConfig`.

**Preconditions:**
- `agent_fox.core.config` is importable.

**Input:**
- Inspect `KnowledgeConfig.model_fields`.

**Expected:**
- `store_path` field exists with default value.

**Assertion pseudocode:**
```
from agent_fox.core.config import KnowledgeConfig

ASSERT "store_path" IN KnowledgeConfig.model_fields
kc = KnowledgeConfig()
ASSERT kc.store_path == ".agent-fox/knowledge.duckdb"
```

### TS-114-30: Old Config Fields Ignored

**Requirement:** 114-REQ-8.5
**Type:** unit
**Description:** Verify constructing `KnowledgeConfig` with old fields does not
raise validation errors.

**Preconditions:**
- `KnowledgeConfig` has `extra="ignore"`.

**Input:**
- Construct `KnowledgeConfig(embedding_model="foo", decay_half_life_days=30)`.

**Expected:**
- No `ValidationError` raised.
- Constructed object has `store_path` but not `embedding_model`.

**Assertion pseudocode:**
```
from agent_fox.core.config import KnowledgeConfig

kc = KnowledgeConfig(embedding_model="foo", decay_half_life_days=30)
ASSERT kc.store_path == ".agent-fox/knowledge.duckdb"
ASSERT NOT hasattr(kc, "embedding_model")  # ignored
```

### TS-114-31: Onboard CLI Removed

**Requirement:** 114-REQ-9.1
**Type:** unit
**Description:** Verify the `onboard` CLI command is removed or disabled.

**Preconditions:**
- CLI module is importable.

**Input:**
- Check if `onboard` command is registered.

**Expected:**
- Command not found or module deleted.

**Assertion pseudocode:**
```
ASSERT NOT Path("agent_fox/cli/onboard.py").exists()
OR
# If file exists, verify the command is not registered in the CLI group
```

### TS-114-32: CLI nightshift.py No EmbeddingGenerator

**Requirement:** 114-REQ-9.2
**Type:** integration
**Description:** Verify `cli/nightshift.py` does not import
`EmbeddingGenerator`.

**Preconditions:**
- `agent_fox/cli/nightshift.py` is accessible.

**Input:**
- Read source of `cli/nightshift.py`.

**Expected:**
- No `EmbeddingGenerator` reference.

**Assertion pseudocode:**
```
source = read("agent_fox/cli/nightshift.py")
ASSERT "EmbeddingGenerator" NOT IN source
```

### TS-114-33: CLI status.py No Removed Imports

**Requirement:** 114-REQ-9.3
**Type:** integration
**Description:** Verify `cli/status.py` does not import from `project_model`
or `store`.

**Preconditions:**
- `agent_fox/cli/status.py` is accessible.

**Input:**
- Read source of `cli/status.py`.

**Expected:**
- No references to `project_model` or `knowledge.store`.

**Assertion pseudocode:**
```
source = read("agent_fox/cli/status.py")
ASSERT "project_model" NOT IN source
ASSERT "knowledge.store" NOT IN source
```

### TS-114-34: CLI plan.py Still Functional

**Requirement:** 114-REQ-9.4
**Type:** unit
**Description:** Verify `cli/plan.py` uses `db.open_knowledge_store` without
depending on removed modules.

**Preconditions:**
- `agent_fox/cli/plan.py` is accessible.

**Input:**
- Read source and check imports.

**Expected:**
- Contains `open_knowledge_store` import from `agent_fox.knowledge.db`.
- No imports from deleted knowledge modules.

**Assertion pseudocode:**
```
source = read("agent_fox/cli/plan.py")
ASSERT "open_knowledge_store" IN source
BANNED = {"retrieval", "extraction", "embeddings", "store", "facts"}
for mod in BANNED:
    ASSERT f"knowledge.{mod}" NOT IN source
```

### TS-114-35: Make Check Passes

**Requirement:** 114-REQ-10.1
**Type:** integration
**Description:** Verify full test suite passes after all changes.

**Preconditions:**
- All changes committed.

**Input:**
- Run `make check`.

**Expected:**
- Exit code 0, zero test failures.

**Assertion pseudocode:**
```
result = subprocess.run(["make", "check"], capture_output=True)
ASSERT result.returncode == 0
```

### TS-114-36: Protocol Unit Tests Exist

**Requirement:** 114-REQ-10.2
**Type:** unit
**Description:** Verify unit tests exist for `KnowledgeProvider` protocol and
`NoOpKnowledgeProvider`.

**Preconditions:**
- Test file exists at expected location.

**Input:**
- Check test file exists and contains relevant test functions.

**Expected:**
- Test file contains tests for protocol conformance and NoOp behavior.

**Assertion pseudocode:**
```
test_path = Path("tests/unit/knowledge/test_provider.py")
ASSERT test_path.exists()
source = read(test_path)
ASSERT "NoOpKnowledgeProvider" IN source
ASSERT "KnowledgeProvider" IN source
```

### TS-114-37: Import Isolation Test Exists

**Requirement:** 114-REQ-10.3
**Type:** unit
**Description:** Verify a test exists that checks engine modules do not import
deleted knowledge modules.

**Preconditions:**
- Test file exists.

**Input:**
- Check for a test that scans engine imports.

**Expected:**
- A test function asserts no banned imports exist in engine source files.

**Assertion pseudocode:**
```
# This is verified by TS-114-10, TS-114-13, TS-114-15 being implemented
# as actual test functions in the test suite.
ASSERT any test file contains import isolation assertions
```

### TS-114-38: Dead Test Files Deleted

**Requirement:** 114-REQ-10.4
**Type:** integration
**Description:** Verify test files that exclusively test removed functionality
are deleted.

**Preconditions:**
- None.

**Input:**
- Check existence of test files for removed modules.

**Expected:**
- Test files for extraction, embeddings, retrieval, consolidation, compaction,
  sleep compute, entity graph, etc. are deleted.

**Assertion pseudocode:**
```
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
for path in DELETED_TESTS:
    ASSERT NOT Path(path).exists()
```

## Edge Case Tests

### TS-114-E1: Partial Protocol Implementation Fails isinstance

**Requirement:** 114-REQ-1.E1
**Type:** unit
**Description:** Verify a class with only one protocol method fails isinstance.

**Preconditions:**
- `KnowledgeProvider` is importable.

**Input:**
- A class with only `ingest()`, no `retrieve()`.

**Expected:**
- `isinstance(partial, KnowledgeProvider)` returns False.

**Assertion pseudocode:**
```
from agent_fox.knowledge.provider import KnowledgeProvider

class PartialProvider:
    def ingest(self, session_id, spec_name, context): pass

ASSERT isinstance(PartialProvider(), KnowledgeProvider) == False
```

### TS-114-E2: NoOp Retrieve Accepts Any Arguments

**Requirement:** 114-REQ-2.E1
**Type:** unit
**Description:** Verify `NoOpKnowledgeProvider.retrieve()` returns empty list
for any argument combination.

**Preconditions:**
- `NoOpKnowledgeProvider` is instantiated.

**Input:**
- Call `retrieve()` with various argument combinations.

**Expected:**
- Always returns `[]`, never raises.

**Assertion pseudocode:**
```
from agent_fox.knowledge.provider import NoOpKnowledgeProvider

noop = NoOpKnowledgeProvider()
ASSERT noop.retrieve("", "") == []
ASSERT noop.retrieve("spec_with_unicode_ñ", "very " * 1000) == []
ASSERT noop.retrieve("spec_01", "normal task") == []
```

### TS-114-E3: Retrieve Exception Handled Gracefully

**Requirement:** 114-REQ-3.E1
**Type:** unit
**Description:** Verify engine handles retrieve() exceptions by logging WARNING
and using empty context.

**Preconditions:**
- `NodeSessionRunner` with a provider whose `retrieve()` raises `RuntimeError`.

**Input:**
- Call `_build_prompts()`.

**Expected:**
- No exception propagated. WARNING logged. Prompts built without knowledge.

**Assertion pseudocode:**
```
class FailingProvider:
    def ingest(self, *a, **kw): pass
    def retrieve(self, *a, **kw): raise RuntimeError("broken")

runner = NodeSessionRunner(..., knowledge_provider=FailingProvider())
system_prompt, task_prompt = runner._build_prompts(repo_root, 1, None)
ASSERT isinstance(system_prompt, str)
ASSERT caplog contains WARNING level message about retrieve failure
```

### TS-114-E4: Ingest Exception Handled Gracefully

**Requirement:** 114-REQ-4.E1
**Type:** unit
**Description:** Verify engine handles ingest() exceptions by logging WARNING
and continuing without retry.

**Preconditions:**
- `NodeSessionRunner` with a provider whose `ingest()` raises `RuntimeError`.

**Input:**
- Call `_ingest_knowledge()`.

**Expected:**
- No exception propagated. WARNING logged. No retry attempted.

**Assertion pseudocode:**
```
class FailingProvider:
    def ingest(self, *a, **kw): raise RuntimeError("broken")
    def retrieve(self, *a, **kw): return []

runner = NodeSessionRunner(..., knowledge_provider=FailingProvider())
# Should not raise
runner._ingest_knowledge("node_1", ["f.py"], "sha", "completed")
ASSERT caplog contains WARNING level message about ingest failure
```

### TS-114-E5: Barrier With Old Knowledge Tables

**Requirement:** 114-REQ-5.E1
**Type:** integration
**Description:** Verify barrier runs without attempting to access old knowledge
tables.

**Preconditions:**
- DuckDB database with old tables (`memory_facts`, `entity_graph`, etc.).

**Input:**
- Run `run_sync_barrier_sequence()`.

**Expected:**
- No queries against `memory_facts`, `entity_graph`, `sleep_artifacts`, etc.
- Barrier completes successfully.

**Assertion pseudocode:**
```
# Create DB with old tables present
conn = create_db_with_legacy_tables()
await run_sync_barrier_sequence(..., knowledge_db_conn=conn)
# No errors, barrier completes
```

### TS-114-E6: Nightshift With Old Sleep Artifacts

**Requirement:** 114-REQ-6.E1
**Type:** integration
**Description:** Verify nightshift daemon runs without accessing old
`sleep_artifacts` table.

**Preconditions:**
- DuckDB database with `sleep_artifacts` table.

**Input:**
- Start nightshift daemon streams.

**Expected:**
- No queries against `sleep_artifacts`.

**Assertion pseudocode:**
```
# Verify no sleep-compute stream is created
from agent_fox.nightshift.streams import STREAM_REGISTRY
ASSERT "sleep-compute" NOT IN [s.name for s in STREAM_REGISTRY]
```

### TS-114-E7: Test Files for Removed Modules Updated

**Requirement:** 114-REQ-7.E1
**Type:** integration
**Description:** Verify no remaining test file imports a deleted module.

**Preconditions:**
- All test files accessible.

**Input:**
- Scan `tests/**/*.py` for imports from deleted modules.

**Expected:**
- Zero hits.

**Assertion pseudocode:**
```
DELETED_MODULES = [
    "agent_fox.knowledge.extraction", "agent_fox.knowledge.embeddings",
    "agent_fox.knowledge.search", "agent_fox.knowledge.retrieval",
    "agent_fox.knowledge.causal", "agent_fox.knowledge.lifecycle",
    "agent_fox.knowledge.contradiction", "agent_fox.knowledge.consolidation",
    "agent_fox.knowledge.compaction", "agent_fox.knowledge.entity_linker",
    "agent_fox.knowledge.entity_query", "agent_fox.knowledge.entity_store",
    "agent_fox.knowledge.entities", "agent_fox.knowledge.static_analysis",
    "agent_fox.knowledge.sleep_compute", "agent_fox.knowledge.rendering",
    "agent_fox.knowledge.store", "agent_fox.knowledge.facts",
    "agent_fox.knowledge.ingest", "agent_fox.knowledge.onboard",
    "agent_fox.engine.knowledge_harvest",
]
for test_file in glob("tests/**/*.py"):
    source = read(test_file)
    for mod in DELETED_MODULES:
        ASSERT mod NOT IN source
```

### TS-114-E8: Removed CLI Command Feedback

**Requirement:** 114-REQ-9.E1
**Type:** unit
**Description:** Verify invoking a removed CLI command produces a clear error.

**Preconditions:**
- CLI group is importable.

**Input:**
- Attempt to invoke `onboard` command.

**Expected:**
- Click raises `UsageError` or similar (command not registered).

**Assertion pseudocode:**
```
from click.testing import CliRunner
from agent_fox.cli.main import cli

runner = CliRunner()
result = runner.invoke(cli, ["onboard"])
ASSERT result.exit_code != 0
ASSERT "No such command" IN result.output OR command not found
```

## Property Test Cases

### TS-114-P1: Protocol Structural Conformance

**Property:** Property 1 from design.md
**Validates:** 114-REQ-1.1, 114-REQ-1.2, 114-REQ-2.1
**Type:** property
**Description:** Any class with both protocol methods satisfies isinstance.

**For any:** class generated with both `ingest` and `retrieve` methods having
correct signatures (strategies: method bodies vary — no-op, returns values,
raises exceptions).
**Invariant:** `isinstance(instance, KnowledgeProvider)` is True.

**Assertion pseudocode:**
```
from hypothesis import given, strategies as st
from agent_fox.knowledge.provider import KnowledgeProvider

@given(st.just(True))
def test_protocol_conformance(_):
    class DynProvider:
        def ingest(self, session_id: str, spec_name: str, context: dict) -> None:
            pass
        def retrieve(self, spec_name: str, task_description: str) -> list[str]:
            return []
    ASSERT isinstance(DynProvider(), KnowledgeProvider)
```

### TS-114-P2: NoOp Retrieve Idempotency

**Property:** Property 2 from design.md
**Validates:** 114-REQ-2.3, 114-REQ-2.E1
**Type:** property
**Description:** NoOp retrieve always returns empty list regardless of inputs.

**For any:** `spec_name` drawn from `st.text()`, `task_description` drawn from
`st.text()`.
**Invariant:** `NoOpKnowledgeProvider().retrieve(spec_name, task_description) == []`.

**Assertion pseudocode:**
```
@given(spec_name=st.text(), task_description=st.text())
def test_noop_retrieve_idempotent(spec_name, task_description):
    noop = NoOpKnowledgeProvider()
    result = noop.retrieve(spec_name, task_description)
    ASSERT result == []
    ASSERT isinstance(result, list)
```

### TS-114-P3: NoOp Ingest Safety

**Property:** Property 3 from design.md
**Validates:** 114-REQ-2.2
**Type:** property
**Description:** NoOp ingest never raises regardless of inputs.

**For any:** `session_id` drawn from `st.text()`, `spec_name` drawn from
`st.text()`, `context` drawn from `st.dictionaries(st.text(), st.text())`.
**Invariant:** `NoOpKnowledgeProvider().ingest(...)` returns None without
exception.

**Assertion pseudocode:**
```
@given(
    session_id=st.text(),
    spec_name=st.text(),
    context=st.dictionaries(st.text(), st.text()),
)
def test_noop_ingest_safe(session_id, spec_name, context):
    noop = NoOpKnowledgeProvider()
    result = noop.ingest(session_id, spec_name, context)
    ASSERT result is None
```

### TS-114-P4: Engine Import Isolation

**Property:** Property 4 from design.md
**Validates:** 114-REQ-3.2, 114-REQ-4.2, 114-REQ-5.1
**Type:** property
**Description:** No engine module imports any deleted knowledge name.

**For any:** engine module path in `agent_fox/engine/*.py`.
**Invariant:** Source text does not contain any banned import name from the
deleted module set.

**Assertion pseudocode:**
```
BANNED = {
    "AdaptiveRetriever", "RetrievalConfig", "EmbeddingGenerator",
    "extract_facts", "extract_and_store_knowledge", "store_causal_links",
    "dedup_new_facts", "detect_contradictions", "run_consolidation",
    "compact", "render_summary", "SleepComputer", "SleepContext",
    "BundleBuilder", "ContextRewriter", "run_cleanup", "load_all_facts",
    "Fact",
}
for module_path in glob("agent_fox/engine/*.py"):
    source = read(module_path)
    for name in BANNED:
        ASSERT name NOT IN source
```

### TS-114-P5: Deletion Completeness

**Property:** Property 5 from design.md
**Validates:** 114-REQ-7.1, 114-REQ-7.2, 114-REQ-7.3, 114-REQ-7.4
**Type:** property
**Description:** All files in the deletion manifest do not exist.

**For any:** file path in the deletion manifest.
**Invariant:** `Path(file_path).exists()` is False.

**Assertion pseudocode:**
```
DELETION_MANIFEST = [
    "agent_fox/knowledge/extraction.py",
    "agent_fox/knowledge/embeddings.py",
    # ... all files from REQ-7.1, 7.2, 7.3, 7.4
    "agent_fox/knowledge/lang/",
    "agent_fox/knowledge/sleep_tasks/",
    "agent_fox/engine/knowledge_harvest.py",
]
for path in DELETION_MANIFEST:
    ASSERT NOT Path(path).exists()
```

### TS-114-P6: Import Health

**Property:** Property 6 from design.md
**Validates:** 114-REQ-7.5, 114-REQ-10.1
**Type:** property
**Description:** All agent_fox modules import successfully.

**For any:** module name discovered via `pkgutil.walk_packages` over
`agent_fox`.
**Invariant:** `importlib.import_module(module_name)` does not raise
`ImportError`.

**Assertion pseudocode:**
```
import importlib, pkgutil
import agent_fox

for importer, modname, ispkg in pkgutil.walk_packages(
    agent_fox.__path__, prefix="agent_fox."
):
    importlib.import_module(modname)  # must not raise
```

### TS-114-P7: Configuration Backward Compatibility

**Property:** Property 7 from design.md
**Validates:** 114-REQ-8.1, 114-REQ-8.2, 114-REQ-8.3, 114-REQ-8.5
**Type:** property
**Description:** Old config fields are silently ignored.

**For any:** dictionary containing a subset of the old KnowledgeConfig fields
drawn from `st.fixed_dictionaries`.
**Invariant:** `KnowledgeConfig(**d)` does not raise and has `store_path`.

**Assertion pseudocode:**
```
OLD_FIELDS = {
    "embedding_model": st.text(),
    "embedding_dimensions": st.integers(),
    "dedup_similarity_threshold": st.floats(0, 1),
    "contradiction_model": st.text(),
    "decay_half_life_days": st.floats(min_value=0),
    "cleanup_enabled": st.booleans(),
}

@given(data=st.fixed_dictionaries({}, optional=OLD_FIELDS))
def test_config_backward_compat(data):
    kc = KnowledgeConfig(**data)
    ASSERT hasattr(kc, "store_path")
    for key in data:
        ASSERT key NOT IN kc.model_fields_set  # ignored, not stored
```

### TS-114-P8: Retrieve Failure Resilience

**Property:** Property 8 from design.md
**Validates:** 114-REQ-3.E1
**Type:** property
**Description:** Engine survives arbitrary retrieve() failures.

**For any:** exception type drawn from `[RuntimeError, ValueError, TypeError, OSError]`.
**Invariant:** `_build_prompts` catches the exception and returns valid prompts.

**Assertion pseudocode:**
```
@given(exc_type=st.sampled_from([RuntimeError, ValueError, TypeError, OSError]))
def test_retrieve_failure_resilience(exc_type):
    class FailProvider:
        def ingest(self, *a, **kw): pass
        def retrieve(self, *a, **kw): raise exc_type("test")

    runner = NodeSessionRunner(..., knowledge_provider=FailProvider())
    sys_prompt, task_prompt = runner._build_prompts(repo_root, 1, None)
    ASSERT isinstance(sys_prompt, str)
```

### TS-114-P9: Ingest Failure Resilience

**Property:** Property 9 from design.md
**Validates:** 114-REQ-4.E1
**Type:** property
**Description:** Engine survives arbitrary ingest() failures.

**For any:** exception type drawn from `[RuntimeError, ValueError, TypeError, OSError]`.
**Invariant:** `_ingest_knowledge` catches the exception and does not retry.

**Assertion pseudocode:**
```
@given(exc_type=st.sampled_from([RuntimeError, ValueError, TypeError, OSError]))
def test_ingest_failure_resilience(exc_type):
    class FailProvider:
        ingest_count = 0
        def ingest(self, *a, **kw):
            self.ingest_count += 1
            raise exc_type("test")
        def retrieve(self, *a, **kw): return []

    provider = FailProvider()
    runner = NodeSessionRunner(..., knowledge_provider=provider)
    runner._ingest_knowledge("node", ["f.py"], "sha", "completed")
    ASSERT provider.ingest_count == 1  # called once, no retry
```

## Integration Smoke Tests

### TS-114-SMOKE-1: Pre-Session Retrieval Path

**Execution Path:** Path 1 from design.md
**Description:** Verify `NoOpKnowledgeProvider.retrieve()` is called during
prompt assembly and returns empty context that does not break prompt building.

**Setup:** Mock `assemble_context`, `build_system_prompt`, `build_task_prompt`
to return fixed strings. Real `NoOpKnowledgeProvider`. Real
`NodeSessionRunner`.

**Trigger:** Call `runner._build_prompts(repo_root, 1, None)`.

**Expected side effects:**
- `NoOpKnowledgeProvider.retrieve()` called once.
- `assemble_context` called with `memory_facts=None` or empty.
- Valid prompts returned.

**Must NOT satisfy with:** Mocking `NoOpKnowledgeProvider` — it must be the
real implementation.

**Assertion pseudocode:**
```
provider = NoOpKnowledgeProvider()  # real, not mocked
runner = NodeSessionRunner(
    "spec_01:1", config,
    knowledge_db=mock_db,
    knowledge_provider=provider,  # real provider
    sink_dispatcher=mock_sink,
)
sys_prompt, task_prompt = runner._build_prompts(repo_root, 1, None)
ASSERT isinstance(sys_prompt, str)
ASSERT isinstance(task_prompt, str)
```

### TS-114-SMOKE-2: Post-Session Ingestion Path

**Execution Path:** Path 2 from design.md
**Description:** Verify `NoOpKnowledgeProvider.ingest()` is called after
session completion without errors.

**Setup:** Mock session execution to return successful outcome. Real
`NoOpKnowledgeProvider`. Real ingestion call path.

**Trigger:** Call `runner._ingest_knowledge(...)`.

**Expected side effects:**
- `NoOpKnowledgeProvider.ingest()` called once (no-op).
- No exception raised.

**Must NOT satisfy with:** Mocking `NoOpKnowledgeProvider`.

**Assertion pseudocode:**
```
provider = NoOpKnowledgeProvider()  # real, not mocked
runner = NodeSessionRunner(..., knowledge_provider=provider)
runner._ingest_knowledge("spec_01:1", ["src/f.py"], "abc123", "completed")
# No exception, no side effects
```

### TS-114-SMOKE-3: Simplified Barrier Path

**Execution Path:** Path 3 from design.md
**Description:** Verify barrier runs to completion without consolidation,
compaction, lifecycle cleanup, sleep compute, or rendering.

**Setup:** Mock worktree verification, develop sync, hot-load, barrier
callback. Real `run_sync_barrier_sequence`.

**Trigger:** Call `await run_sync_barrier_sequence(...)`.

**Expected side effects:**
- Barrier completes without error.
- No consolidation/compaction/sleep/cleanup/rendering calls attempted.

**Must NOT satisfy with:** Mocking `run_sync_barrier_sequence` itself.

**Assertion pseudocode:**
```
state = MockState(node_states={"spec_01:1": "completed"})
await run_sync_barrier_sequence(
    state=state,
    sync_interval=1,
    repo_root=tmp_path,
    emit_audit=mock_audit,
    specs_dir=None,
    hot_load_enabled=False,
    hot_load_fn=mock_fn,
    sync_plan_fn=mock_fn,
    barrier_callback=None,
    knowledge_db_conn=None,  # no consolidation/compaction path
)
# Completes without error
```

### TS-114-SMOKE-4: Engine Initialization Path

**Execution Path:** Path 4 from design.md
**Description:** Verify `_setup_infrastructure` creates a
`NoOpKnowledgeProvider` and does not create an `EmbeddingGenerator` or run
background ingestion.

**Setup:** Default config. Mock `open_knowledge_store` to return a test DB.

**Trigger:** Call `_setup_infrastructure(config)`.

**Expected side effects:**
- Returns dict with `knowledge_provider` key.
- `knowledge_provider` is a `NoOpKnowledgeProvider`.
- No `EmbeddingGenerator` instantiation attempted.
- No `run_background_ingestion` call.

**Must NOT satisfy with:** Mocking `_setup_infrastructure` itself.

**Assertion pseudocode:**
```
with patch("agent_fox.engine.run.open_knowledge_store", return_value=mock_db):
    infra = _setup_infrastructure(default_config)
ASSERT "knowledge_provider" IN infra
ASSERT isinstance(infra["knowledge_provider"], NoOpKnowledgeProvider)
```

### TS-114-SMOKE-5: Review Findings Path Unchanged

**Execution Path:** Path 5 from design.md
**Description:** Verify review findings persistence still works end-to-end
after knowledge decoupling.

**Setup:** Mock review_store CRUD. Real `_persist_review_findings` path.

**Trigger:** Call `_extract_knowledge_and_findings(...)` with review archetype.

**Expected side effects:**
- `_persist_review_findings` called.
- No `extract_and_store_knowledge` call (it no longer exists).

**Must NOT satisfy with:** Mocking `_extract_knowledge_and_findings`.

**Assertion pseudocode:**
```
runner = NodeSessionRunner(
    "spec_01:1", config,
    archetype="reviewer",
    knowledge_provider=NoOpKnowledgeProvider(),
    ...
)
await runner._extract_knowledge_and_findings("spec_01:1", 1, workspace)
# Review findings path still works; harvest path is gone
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 114-REQ-1.1 | TS-114-1 | unit |
| 114-REQ-1.2 | TS-114-2 | unit |
| 114-REQ-1.3 | TS-114-3 | unit |
| 114-REQ-1.4 | TS-114-4 | unit |
| 114-REQ-1.E1 | TS-114-E1 | unit |
| 114-REQ-2.1 | TS-114-5 | unit |
| 114-REQ-2.2 | TS-114-6 | unit |
| 114-REQ-2.3 | TS-114-7 | unit |
| 114-REQ-2.4 | TS-114-8 | integration |
| 114-REQ-2.E1 | TS-114-E2 | unit |
| 114-REQ-3.1 | TS-114-9 | unit |
| 114-REQ-3.2 | TS-114-10 | integration |
| 114-REQ-3.3 | TS-114-11 | unit |
| 114-REQ-3.E1 | TS-114-E3 | unit |
| 114-REQ-4.1 | TS-114-12 | unit |
| 114-REQ-4.2 | TS-114-13 | integration |
| 114-REQ-4.3 | TS-114-14 | unit |
| 114-REQ-4.E1 | TS-114-E4 | unit |
| 114-REQ-5.1 | TS-114-15 | integration |
| 114-REQ-5.2 | TS-114-16 | unit |
| 114-REQ-5.E1 | TS-114-E5 | integration |
| 114-REQ-6.1 | TS-114-17 | integration |
| 114-REQ-6.2 | TS-114-18 | integration |
| 114-REQ-6.3 | TS-114-19 | integration |
| 114-REQ-6.4 | TS-114-20 | integration |
| 114-REQ-6.E1 | TS-114-E6 | integration |
| 114-REQ-7.1 | TS-114-21 | unit |
| 114-REQ-7.2 | TS-114-22 | unit |
| 114-REQ-7.3 | TS-114-23 | unit |
| 114-REQ-7.4 | TS-114-24 | unit |
| 114-REQ-7.5 | TS-114-25 | integration |
| 114-REQ-7.E1 | TS-114-E7 | integration |
| 114-REQ-8.1 | TS-114-26 | unit |
| 114-REQ-8.2 | TS-114-27 | unit |
| 114-REQ-8.3 | TS-114-28 | unit |
| 114-REQ-8.4 | TS-114-29 | unit |
| 114-REQ-8.5 | TS-114-30 | unit |
| 114-REQ-9.1 | TS-114-31 | unit |
| 114-REQ-9.2 | TS-114-32 | integration |
| 114-REQ-9.3 | TS-114-33 | integration |
| 114-REQ-9.4 | TS-114-34 | unit |
| 114-REQ-9.E1 | TS-114-E8 | unit |
| 114-REQ-10.1 | TS-114-35 | integration |
| 114-REQ-10.2 | TS-114-36 | unit |
| 114-REQ-10.3 | TS-114-37 | unit |
| 114-REQ-10.4 | TS-114-38 | integration |
| Property 1 | TS-114-P1 | property |
| Property 2 | TS-114-P2 | property |
| Property 3 | TS-114-P3 | property |
| Property 4 | TS-114-P4 | property |
| Property 5 | TS-114-P5 | property |
| Property 6 | TS-114-P6 | property |
| Property 7 | TS-114-P7 | property |
| Property 8 | TS-114-P8 | property |
| Property 9 | TS-114-P9 | property |
| Path 1 | TS-114-SMOKE-1 | integration |
| Path 2 | TS-114-SMOKE-2 | integration |
| Path 3 | TS-114-SMOKE-3 | integration |
| Path 4 | TS-114-SMOKE-4 | integration |
| Path 5 | TS-114-SMOKE-5 | integration |
