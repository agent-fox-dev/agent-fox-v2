# Spec Audit Report

**Generated:** 2026-04-15
**Branch:** develop
**Specs analyzed:** 20 (19 unique numbers; two specs share number 103)

## Summary

| Category | Count |
|----------|-------|
| Compliant | 395 |
| Drifted | 11 |
| Superseded (by implication) | 9 |
| In-progress (expected gaps) | 70 |
| Execution paths live | 33 |
| Execution paths broken/partial | 1 |
| Execution paths not started | 6 |

## Warnings

- **Duplicate spec number 103:** Two unrelated specs share number 103
  (`103_agent_conversation_trace` and `103_remove_hook_runner`). Both use
  `103-REQ-*` requirement IDs, creating traceability ambiguity. One should
  be renumbered.

---

## Compliant Requirements

### Spec 91: Night-Shift Cost Tracking (23/23 compliant)

| Requirement | Description |
|-------------|-------------|
| 91-REQ-1.1 | SinkDispatcher on NightShiftEngine |
| 91-REQ-1.2 | CLI creates SinkDispatcher+DuckDBSink |
| 91-REQ-1.3 | Graceful degradation without sink |
| 91-REQ-1.E1 | DuckDB unavailable at startup |
| 91-REQ-2.1 | Per-fix run_id generation |
| 91-REQ-2.2 | FixPipeline accepts SinkDispatcher |
| 91-REQ-2.E1 | None sink skips emission |
| 91-REQ-3.1 | session.complete after success |
| 91-REQ-3.2 | session.fail after failure |
| 91-REQ-3.3 | Pass sink+run_id to run_session |
| 91-REQ-3.E1 | Audit write error continues |
| 91-REQ-4.1 | Critic cost tracking |
| 91-REQ-4.2 | Batch triage cost tracking |
| 91-REQ-4.3 | Staleness cost tracking |
| 91-REQ-4.4 | Quality gate cost tracking |
| 91-REQ-4.5 | Auxiliary fail event |
| 91-REQ-4.E1 | No sink skip guard |
| 91-REQ-5.1 | Remove nightshift/audit.py |
| 91-REQ-5.2 | Standard audit helper usage |
| 91-REQ-5.3 | DaemonRunner standard audit |
| 91-REQ-5.E1 | None sink guard in standard helper |
| 91-REQ-6.1 | Status includes nightshift events |
| 91-REQ-6.2 | Grand total includes nightshift |

### Spec 92: Transient Audit Reports (12/12 compliant)

| Requirement | Description |
|-------------|-------------|
| 92-REQ-1.1 | Write to .agent-fox/audit/ |
| 92-REQ-1.2 | Create directory if needed |
| 92-REQ-1.3 | No audit.md in .specs/ |
| 92-REQ-1.E1 | Directory creation failure handling |
| 92-REQ-2.1 | Overwrite existing reports |
| 92-REQ-3.1 | PASS verdict deletes report |
| 92-REQ-3.E1 | No file on PASS, no error |
| 92-REQ-3.E2 | Deletion filesystem error handling |
| 92-REQ-4.1 | Deletion on spec completion |
| 92-REQ-4.2 | cleanup_completed_spec_audits function |
| 92-REQ-4.E1 | No files on cleanup, no error |
| 92-REQ-4.E2 | Partial failure continues |

### Spec 93: Fix Branch Push (13/13 compliant)

| Requirement | Description |
|-------------|-------------|
| 93-REQ-1.1 | push_fix_branch config |
| 93-REQ-1.2 | Defaults to false |
| 93-REQ-1.E1 | Non-boolean rejected |
| 93-REQ-2.1 | Issue number in branch name |
| 93-REQ-2.2 | Branch name format |
| 93-REQ-2.E1 | Empty/special title fallback |
| 93-REQ-3.1 | Push before harvest when enabled |
| 93-REQ-3.2 | Force-push |
| 93-REQ-3.3 | No push when disabled |
| 93-REQ-3.4 | No remote branch delete |
| 93-REQ-3.E1 | Push failure logs warning, continues |
| 93-REQ-3.E2 | Failure reason in log |
| 93-REQ-4.1 | Independent of merge_strategy |

### Spec 94: Cross-Spec Vector Retrieval (7/16 compliant)

| Requirement | Description |
|-------------|-------------|
| 94-REQ-1.1 | Extract subtask descriptions |
| 94-REQ-1.2 | Skip metadata bullets |
| 94-REQ-1.E1 | Missing tasks.md handling |
| 94-REQ-1.E2 | Group not found / no bullets |
| 94-REQ-5.1 | Graceful degradation |
| 94-REQ-6.1 | Embedder passed through factory |
| 94-REQ-6.2 | No embedder skips retrieval |

### Spec 95: Entity Graph (38/38 compliant)

| Requirement | Description |
|-------------|-------------|
| 95-REQ-1.1 through 95-REQ-7.E2 | All 38 requirements compliant |

Note: FK constraints (95-REQ-2.3, 95-REQ-3.2) enforced in application code
instead of DDL due to DuckDB 1.5.x bug. Documented in
`docs/errata/95_entity_graph.md`.

### Spec 96: Knowledge Consolidation (35/35 compliant)

| Requirement | Description |
|-------------|-------------|
| 96-REQ-1.1 through 96-REQ-7.E2 | All 35 requirements compliant |

### Spec 97: Archetype Modes (24/26 compliant)

| Requirement | Description |
|-------------|-------------|
| 97-REQ-1.3 through 97-REQ-1.E2 | resolve_effective_config, mode=None, override semantics, unknown mode |
| 97-REQ-2.1 through 97-REQ-2.E1 | Node.mode field, serialization, string representation |
| 97-REQ-3.1 through 97-REQ-3.E1 | PerArchetypeConfig.modes, TOML parsing, 4-tier resolution |
| 97-REQ-4.1 through 97-REQ-4.E1 | All resolve_* functions accept mode param |
| 97-REQ-5.2 through 97-REQ-5.E1 | Empty allowlist blocks Bash, NodeSessionRunner passes mode |

### Spec 98: Reviewer Consolidation (26/30 compliant)

| Requirement | Description |
|-------------|-------------|
| 98-REQ-1.1 through 98-REQ-1.E1 | Reviewer modes (pre-review, drift-review, audit-review, fix-review) |
| 98-REQ-2.E1 | resolve_effective_config(coder, None) returns base unchanged |
| 98-REQ-3.2 | build_system_prompt loads profile via mode-aware resolution |
| 98-REQ-4.1 through 98-REQ-4.E1 | Graph injection with modes |
| 98-REQ-5.1 through 98-REQ-5.E1 | Convergence dispatch by mode |
| 98-REQ-6.1 through 98-REQ-6.3 | Verifier tier, clamping, retention |
| 98-REQ-7.1, 98-REQ-7.2 | Old archetypes removed from registry |
| 98-REQ-8.1 through 98-REQ-8.E1 | Config model cleanup |

### Spec 99: Archetype Profiles (22/22 compliant)

| Requirement | Description |
|-------------|-------------|
| 99-REQ-1.1 through 99-REQ-5.E1 | All 22 requirements compliant |

### Spec 100: Maintainer Archetype (18/19 compliant)

| Requirement | Description |
|-------------|-------------|
| 100-REQ-1.1 through 100-REQ-1.E1 | Maintainer modes (hunt, extraction) |
| 100-REQ-2.1 through 100-REQ-2.E1 | Triage absorption into maintainer:hunt |
| 100-REQ-3.1 through 100-REQ-3.3 | Maintainer profile content |
| 100-REQ-4.1, 100-REQ-4.2, 100-REQ-4.E1 | ExtractionInput/Result, stub function |
| 100-REQ-5.1 through 100-REQ-5.3 | Runtime resolution wiring |

### Spec 101: Knowledge Onboarding (43/43 compliant)

| Requirement | Description |
|-------------|-------------|
| 101-REQ-1.1 through 101-REQ-8.3 | All 43 requirements compliant |

### Spec 102: Multi-Language Entity Graph (32/32 compliant)

| Requirement | Description |
|-------------|-------------|
| 102-REQ-1.1 through 102-REQ-6.3 | All 32 requirements compliant |

### Spec 103: Agent Conversation Trace (23/23 compliant)

| Requirement | Description |
|-------------|-------------|
| 103-REQ-1.1 through 103-REQ-8.E1 | All 23 requirements compliant |

### Spec 103: Remove Hook Runner (18/18 compliant)

| Requirement | Description |
|-------------|-------------|
| 103-REQ-1.1 through 103-REQ-4.E1 | All 18 requirements compliant |

### Spec 104: Adaptive Retrieval (37/37 compliant)

| Requirement | Description |
|-------------|-------------|
| 104-REQ-1.1 through 104-REQ-7.E1 | All 37 requirements compliant |

### Spec 105: DB-Based Plan State (24/28 compliant)

| Requirement | Description |
|-------------|-------------|
| 105-REQ-1.1 through 105-REQ-1.E2 | Plan DAG persistence, schema, content hash |
| 105-REQ-2.1 through 105-REQ-2.3, 105-REQ-2.E1 | Node status updates, V3 status set, crash recovery |
| 105-REQ-3.1 through 105-REQ-3.2, 105-REQ-3.E1 | Session outcomes extended, all fields |
| 105-REQ-4.1 through 105-REQ-4.E1 | Runs table, run lifecycle |
| 105-REQ-5.1, 105-REQ-5.2, 105-REQ-5.E1 | PLAN_PATH removed, save/load accept conn |
| 105-REQ-6.1 through 105-REQ-6.E1 | Status CLI, concurrent read |

---

## Drifted Requirements

### 97-REQ-1.1: ModeConfig missing `templates` field

**Spec says:** ModeConfig SHALL have 8 optional fields including
`templates: list[str] | None`.
**Code does:** ModeConfig has 7 fields; `templates` is absent. The templates
concept was removed in favor of profile-based resolution (issue #342).
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The `templates` mechanism is fully replaced by the profile
system (spec 99). No code path references templates. The spec should be
updated to reflect the profile-based architecture.

---

### 97-REQ-5.1: `make_pre_tool_use_hook` mode parameter

**Spec says:** `make_pre_tool_use_hook()` SHALL accept an optional
`mode: str | None` parameter.
**Code does:** Function signature is `make_pre_tool_use_hook(config: SecurityConfig)`
with no `mode` parameter. Mode resolution happens upstream in
`resolve_security_config()`.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The implementation is cleaner than what the spec prescribed.
Mode is resolved before hook creation, so the SecurityConfig already
encodes mode-specific allowlists. Adding a mode parameter would be redundant.

---

### 98-REQ-2.1: Coder fix mode `templates` field

**Spec says:** Coder fix mode uses `templates=["fix_coding.md"]` with an
explicit `templates` field on ModeConfig.
**Code does:** ModeConfig has no `templates` field. Profile resolution uses
`load_profile("coder", mode="fix")` which resolves to
`_templates/profiles/coder_fix.md` via naming convention.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Functionally equivalent. The behavioral intent is fully met
through the profile system.

---

### 98-REQ-2.2: ArchetypeEntry `templates` field

**Spec says:** ArchetypeEntry includes `templates: list[str]` field.
**Code does:** `templates` field removed from ArchetypeEntry (issue #342).
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Same as 98-REQ-2.1. Templates replaced by profiles.

---

### 98-REQ-3.1: Reviewer template at `_templates/prompts/`

**Spec says:** `agent_fox/_templates/prompts/reviewer.md` as prompt template.
**Code does:** File is at `agent_fox/_templates/profiles/reviewer.md`. The
`_templates/prompts/` directory no longer exists (removed in issue #342).
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Content is intact and correct. Only the directory changed
as part of the profile migration (spec 99).

---

### 98-REQ-3.3: fix_coding.md template retained

**Spec says:** `fix_coding.md` retained as a separate template file.
**Code does:** File is now `_templates/profiles/coder_fix.md` (renamed and
relocated during profile migration).
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Content is intact. The file was renamed to match the
profile naming convention (`<archetype>_<mode>.md`).

---

### 100-REQ-4.3: `extract_knowledge` parameter naming

**Spec says:** `extract_knowledge(input: ExtractionInput)` with parameter
named `input`.
**Code does:** `extract_knowledge(extraction_input: ExtractionInput)` with
parameter named `extraction_input`.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The parameter name `input` shadows a Python built-in. The
implementation correctly avoids this. Behavioral contract is identical.

---

### 105-REQ-2.4: `_sync_plan_statuses` removal

**Spec says:** `_sync_plan_statuses` method SHALL be removed -- node statuses
are persisted on each transition, not batch-synced at shutdown.
**Code does:** `_sync_plan_statuses` is retained in `engine/engine.py`. It
now also persists to DB via `persist_node_status()`, but still exists as an
end-of-run sync barrier and still writes `plan.json`.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** low
**Rationale:** The method is additive (belt-and-suspenders) and not harmful,
but contradicts the spec's intent to eliminate batch sync.

---

### 105-REQ-3.3: SessionRecord/StateManager removal

**Spec says:** THE system SHALL remove the `SessionRecord` dataclass and
the `StateManager` class.
**Code does:** `StateManager` is retained and actively used in engine.py,
result_handler.py, reset.py, and 25+ test files.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Documented in `docs/errata/105_db_plan_state.md`. Removal
blocked by 25+ dependent test files. Requires a follow-up spec to migrate
tests and remove StateManager.

---

### 105-REQ-5.3: StateManager class removal

**Spec says:** THE system SHALL remove the `StateManager` class and all JSONL
append/load logic.
**Code does:** `StateManager` is retained. Same as 105-REQ-3.3.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Same as 105-REQ-3.3. Tracked in errata.

---

### 105-REQ-5.4: No plan.json or state.jsonl files created

**Spec says:** THE system SHALL NOT create plan.json or state.jsonl files.
**Code does:** `_sync_plan_statuses()` still calls
`save_plan(self._graph, self._plan_path)` which writes plan.json.
`self._state_manager.save(state)` still writes state.jsonl.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Direct contradiction. File-based writes are retained as
fallback paths. Depends on completing StateManager removal (105-REQ-5.3).

---

## Superseded Requirements

| Requirement | Original Spec | Superseded By | Type |
|-------------|--------------|---------------|------|
| 94-REQ-2.1 | 94_cross_spec_vector_retrieval | 104_adaptive_retrieval | implicit |
| 94-REQ-2.2 | 94_cross_spec_vector_retrieval | 104_adaptive_retrieval | implicit |
| 94-REQ-2.E1 | 94_cross_spec_vector_retrieval | 104_adaptive_retrieval | implicit |
| 94-REQ-2.E2 | 94_cross_spec_vector_retrieval | 104_adaptive_retrieval | implicit |
| 94-REQ-3.1 | 94_cross_spec_vector_retrieval | 104_adaptive_retrieval | implicit |
| 94-REQ-3.2 | 94_cross_spec_vector_retrieval | 104_adaptive_retrieval | implicit |
| 94-REQ-3.E1 | 94_cross_spec_vector_retrieval | 104_adaptive_retrieval | implicit |
| 94-REQ-4.1 | 94_cross_spec_vector_retrieval | 104_adaptive_retrieval | implicit |
| 94-REQ-4.2 | 94_cross_spec_vector_retrieval | 104_adaptive_retrieval | implicit |

Spec 104 (`adaptive_retrieval`) replaced the `select_relevant_facts` ->
`_retrieve_cross_spec_facts` -> `_enhance_with_causal` chain with a unified
`AdaptiveRetriever` using multi-signal RRF fusion. The surviving spec 94
capabilities (subtask extraction, embedder factory, graceful degradation)
are now covered by spec 104's implementation. All spec 94 test files were
removed when the old retrieval chain was deleted.

**Note:** `KnowledgeConfig.cross_spec_top_k` (94-REQ-4.1) remains in the
config schema but is dead code -- never read by any production code path.
This field should be removed or aliased to `RetrievalConfig.vector_top_k`.

---

## Execution Path Status

### Live Paths

| Spec | Path | Details |
|------|------|---------|
| 91 | Fix session -> DuckDB | CLI -> Engine -> FixPipeline -> DuckDBSink |
| 91 | Auxiliary AI -> DuckDB | Engine -> critic/triage/staleness -> DuckDBSink |
| 91 | Operational events | Engine -> audit_helpers -> DuckDBSink |
| 92 | Non-PASS report write | review_persistence -> auditor_output -> .agent-fox/audit/ |
| 92 | PASS report cleanup | Same entry -> PASS branch -> delete file |
| 92 | Spec completion cleanup | engine -> completed_spec_names -> cleanup_completed_spec_audits |
| 93 | Push enabled | process_issue -> push_fix_branch_upstream -> push_to_remote(force=True) |
| 93 | Push disabled | Conditional skip -> proceed to harvest |
| 93 | Branch naming | build_in_memory_spec -> sanitise_branch_name |
| 95 | Full codebase analysis | analyze_codebase -> language registry -> upsert_entities/edges |
| 95 | Fact-entity linking | link_facts -> extract_paths_from_diff -> create_fact_entity_links |
| 95 | Graph query | find_related_facts -> traverse_neighbors -> get_facts_for_entities |
| 95 | Garbage collection | gc_stale_entities -> cascade delete edges/links/entities |
| 96 | Consolidation at sync barrier | barrier.py -> run_consolidation() |
| 96 | Consolidation at end-of-run | engine.py finally block -> _run_consolidation() |
| 97 | Archetype resolution with mode | NodeSessionRunner -> resolve_model_tier(mode=) |
| 97 | Security hook with mode | resolve_security_config(mode=) -> make_pre_tool_use_hook |
| 97 | Config resolution with mode | resolve_max_turns(mode=) -> resolve_effective_config |
| 97 | Graph node with mode | Node(mode=) serialization round-trip |
| 98 | Pre-review injection | injection.py -> session_lifecycle -> prompt.py |
| 98 | Drift-review with oracle gating | spec_has_existing_code gating |
| 98 | Audit-review injection | injection.py -> convergence dispatch |
| 98 | Coder fix mode | nightshift -> session -> coder_fix.md profile |
| 99 | Prompt assembly with project profile | session_lifecycle -> build_system_prompt -> load_profile |
| 99 | Prompt assembly with default profile | load_profile -> _templates/profiles/ |
| 99 | Custom archetype session | get_archetype -> has_custom_profile -> _resolve_custom_preset |
| 99 | Init --profiles | init_cmd -> init_profiles() |
| 100 | Nightshift triage via maintainer:hunt | triage.py -> resolve_model_tier("maintainer", mode="hunt") |
| 100 | Knowledge extraction (stubbed) | extract_knowledge() returns stub result |
| 101 | Full onboard pipeline | All 6 phases wired |
| 101 | Partial onboard with skips | Skip flags propagate correctly |
| 102 | Full multi-language analysis | Language registry dispatches to all analyzers |
| 102 | Python backward compat | Python-only analysis path preserved |
| 103 | Debug trace during session | AgentTraceSink registered when debug=True |
| 103 | Security allowlist enforcement | New import path, same behavior |
| 103 | Config hot-reload | ReloadResult dataclass |
| 104 | Unified retrieval | AdaptiveRetriever.retrieve() with RRF fusion |
| 105 | Plan creation/persistence | cli/plan.py -> save_plan(graph, conn) -> DuckDB |
| 105 | Plan load and execution | engine.py:_load_graph() tries DB first |
| 105 | Node status update | result_handler -> persist_node_status, record_session |
| 105 | Status query (concurrent) | cli/status.py opens read_only=True connection |

### Partial Paths

| Spec | Path | Details |
|------|------|---------|
| 105 | Plan change detection on resume | `compute_plan_hash` implemented but resume path still has file-based fallback |

### Not Started (In-Progress Specs)

| Spec | Path | Details |
|------|------|---------|
| 106 | Hunt scan applies ignore filtering | No ignore module exists |
| 106 | Init creates .night-shift file | No init integration |
| 107 | Codebase analysis with new languages | No analyzer classes for C#/Elixir/Kotlin/Dart |
| 107 | Registry handles missing grammar | No _try_register for new analyzers |
| 108 | Spec completes with GitHub source URL | No issue_summary.py module |
| 108 | Comment posting | No post_issue_summaries function |

---

## Test Coverage

### Fully Covered Specs

| Spec | Test Entries | Status |
|------|-------------|--------|
| 91 | 19 | All implemented |
| 92 | 13 | All implemented |
| 93 | 18 | All implemented |
| 95 | 51 | All implemented |
| 96 | 43 | All implemented |
| 97 | 25 | All implemented |
| 98 | 30+ | All implemented (80 tests) |
| 99 | 24 | All implemented (33 tests) |
| 100 | 19 | All implemented (49 tests) |
| 101 | 52 | All implemented |
| 102 | 36 | All implemented |
| 103 (trace) | 19 | All implemented |
| 103 (hooks) | 14 | All implemented |
| 104 | 38 | All implemented |
| 105 | 25 | All implemented |

### Missing Test Coverage

| Spec | Test Entries | Status | Reason |
|------|-------------|--------|--------|
| 94 | ~24 | All missing | Test files removed when spec 104 superseded retrieval chain |
| 106 | 28 | All missing | Implementation not started (0%) |
| 107 | 34 | All missing | Implementation not started (0%) |
| 108 | 21 | All missing | Implementation not started (0%) |

---

## In-Progress Caveats

### 106_nightshift_ignore (completion: 0%)

| Requirement | Status | Notes |
|-------------|--------|-------|
| 106-REQ-1.1 through 106-REQ-6.3 | Expected gap | All 22 requirements unimplemented; 0 of 5 task groups started |

### 107_additional_language_analyzers (completion: 0%)

| Requirement | Status | Notes |
|-------------|--------|-------|
| 107-REQ-1.1 through 107-REQ-6.2 | Expected gap | All 28 requirements unimplemented; 0 of 7 task groups started |

### 108_issue_session_summary (completion: 0%)

| Requirement | Status | Notes |
|-------------|--------|-------|
| 108-REQ-1.1 through 108-REQ-6.E1 | Expected gap | All 20 requirements unimplemented; 0 of 4 task groups started |

---

## Extra Behavior (Best-Effort)

- **Dead config field:** `KnowledgeConfig.cross_spec_top_k` exists in
  `config.py:300` but is never read by any production code. It was made
  obsolete when spec 104's `AdaptiveRetriever` replaced spec 94's retrieval
  chain. The `RetrievalConfig.vector_top_k` (default 50) is used instead.

- **Stale `[-]` markers in spec 101 tasks.md:** Five sub-verification items
  marked `[-]` ("in progress") are cosmetically stale -- the blocking
  modules were implemented in later task groups (all `[x]`).

- **Spec 95 erratum (FK constraints):** FK constraints in entity_graph and
  fact_entities tables are omitted from DDL due to DuckDB 1.5.x bug.
  Enforced in application code. Documented in
  `docs/errata/95_entity_graph.md`.

---

## Mitigation Summary

| Requirement | Mitigation | Priority |
|-------------|-----------|----------|
| 97-REQ-1.1 | Change spec | low |
| 97-REQ-5.1 | Change spec | low |
| 98-REQ-2.1 | Change spec | low |
| 98-REQ-2.2 | Change spec | low |
| 98-REQ-3.1 | Change spec | low |
| 98-REQ-3.3 | Change spec | low |
| 100-REQ-4.3 | Change spec | low |
| 105-REQ-2.4 | Get well spec | low |
| 105-REQ-3.3 | Get well spec | medium |
| 105-REQ-5.3 | Get well spec | medium |
| 105-REQ-5.4 | Get well spec | medium |
| 94-REQ-4.1 (dead config) | Get well spec | medium |
