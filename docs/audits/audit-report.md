# Spec Audit Report

**Generated:** 2026-03-06
**Branch:** develop
**Specs analyzed:** 24

## Summary

| Category | Count |
|----------|-------|
| Compliant | 128 |
| Drifted | 2 |
| Unimplemented | 0 |
| Superseded | 5 |
| In-progress (expected gaps) | 0 |

## Warnings

- Spec folder `fix_01_ruff_format`: skipped -- name does not match `NN_snake_case` pattern.
- Spec folder `fix_02_unnarrrowed_content_block_union`: skipped -- name does not match `NN_snake_case` pattern.
- Spec folder `fix_03_spec_lint_fixes`: skipped -- name does not match `NN_snake_case` pattern.
- Spec folder `test_spec`: skipped -- name does not match `NN_snake_case` pattern.
- Two specs share numeric prefix `15`: `15_session_prompt` and `15_standup_formatting`. Both audited.

---

## Compliant Requirements

| Requirement | Spec | Description |
|-------------|------|-------------|
| 01-REQ-1.1 | 01_core_foundation | Click-based CLI with subcommand registration |
| 01-REQ-1.2 | 01_core_foundation | `--version` flag via click.version_option |
| 01-REQ-1.3 | 01_core_foundation | Banner rendering on invocation |
| 01-REQ-1.4 | 01_core_foundation | Help displayed when no subcommand |
| 01-REQ-2.1 | 01_core_foundation | TOML config loading from .agent-fox/config.toml |
| 01-REQ-2.2 | 01_core_foundation | Pydantic validation with clear error messages |
| 01-REQ-2.3 | 01_core_foundation | Default values for all config fields |
| 01-REQ-2.4 | 01_core_foundation | CLI overrides for config |
| 01-REQ-2.5 | 01_core_foundation | Hierarchical config sections |
| 01-REQ-2.6 | 01_core_foundation | Unknown sections silently ignored |
| 01-REQ-2.E1 | 01_core_foundation | Missing config file returns defaults |
| 01-REQ-2.E2 | 01_core_foundation | Parse failure raises ConfigError |
| 01-REQ-2.E3 | 01_core_foundation | Out-of-range values clamped via validators |
| 01-REQ-3.* | 01_core_foundation | Project initialization with .agent-fox/ structure |
| 01-REQ-4.1 | 01_core_foundation | Base AgentFoxError with context kwargs |
| 01-REQ-4.2 | 01_core_foundation | 11 specific error subclasses |
| 01-REQ-5.1 | 01_core_foundation | Three-tier model system (SIMPLE/STANDARD/ADVANCED) |
| 01-REQ-5.2 | 01_core_foundation | ModelEntry with pricing |
| 01-REQ-5.3 | 01_core_foundation | TIER_DEFAULTS mapping |
| 01-REQ-5.4 | 01_core_foundation | calculate_cost function |
| 01-REQ-5.E1 | 01_core_foundation | ConfigError on unknown model |
| 01-REQ-6.* | 01_core_foundation | Structured Python logging |
| 01-REQ-7.1 | 01_core_foundation | Rich-based color theme |
| 01-REQ-7.2 | 01_core_foundation | Configurable style roles |
| 01-REQ-7.3 | 01_core_foundation | Playful and neutral message modes |
| 01-REQ-7.4 | 01_core_foundation | Seven default style roles |
| 01-REQ-7.E1 | 01_core_foundation | Invalid style falls back to default |
| 02-REQ-1.* | 02_planning_engine | Spec discovery with NN_name pattern, filtering |
| 02-REQ-2.* | 02_planning_engine | Task parsing from checkbox markdown with optional markers |
| 02-REQ-3.* | 02_planning_engine | Graph construction with intra/cross-spec edges |
| 02-REQ-4.* | 02_planning_engine | Topological sort with deterministic tie-breaking, cycle detection |
| 02-REQ-5.* | 02_planning_engine | Fast-mode filtering with dependency rewiring |
| 02-REQ-6.* | 02_planning_engine | Plan persistence to plan.json with metadata |
| 02-REQ-7.* | 02_planning_engine | Plan CLI command with --fast, --spec, --reanalyze, --verify |
| 03-REQ-1.* | 03_session_and_workspace | Worktree creation at .agent-fox/worktrees/{spec}/{group} |
| 03-REQ-2.* | 03_session_and_workspace | Workspace cleanup with empty dir removal |
| 03-REQ-3.* | 03_session_and_workspace | Session execution via claude-code-sdk |
| 03-REQ-4.* | 03_session_and_workspace | Context assembly with spec docs and memory facts |
| 03-REQ-5.* | 03_session_and_workspace | Prompt building with templates |
| 03-REQ-6.* | 03_session_and_workspace | Session timeout via asyncio.wait_for |
| 03-REQ-7.* | 03_session_and_workspace | Change harvesting with rebase-then-merge |
| 03-REQ-8.* | 03_session_and_workspace | Security enforcement with bash command allowlist |
| 03-REQ-9.* | 03_session_and_workspace | Git operations module |
| 04-REQ-1.* | 04_orchestrator | Execution loop with plan loading and task dispatch |
| 04-REQ-2.* | 04_orchestrator | Retry logic with error context |
| 04-REQ-3.* | 04_orchestrator | Cascade blocking via BFS |
| 04-REQ-4.* | 04_orchestrator | State persistence to state.jsonl with plan hash |
| 04-REQ-5.* | 04_orchestrator | Cost and session limits with soft ceiling |
| 04-REQ-6.* | 04_orchestrator | Parallel execution up to 8 concurrent tasks |
| 04-REQ-7.* | 04_orchestrator | Exactly-once execution guarantee |
| 04-REQ-8.* | 04_orchestrator | Graceful SIGINT handling with state save |
| 04-REQ-9.* | 04_orchestrator | Configurable inter-session delay |
| 04-REQ-10.* | 04_orchestrator | Graph state propagation |
| 05-REQ-1.* | 05_structured_memory | Fact extraction using SIMPLE model |
| 05-REQ-2.* | 05_structured_memory | Six fact categories as StrEnum |
| 05-REQ-3.* | 05_structured_memory | JSONL storage at .agent-fox/memory.jsonl |
| 05-REQ-4.* | 05_structured_memory | Context selection with relevance scoring, 50-fact budget |
| 05-REQ-5.* | 05_structured_memory | Compaction with SHA-256 hash and supersession chains |
| 05-REQ-6.* | 05_structured_memory | Human-readable docs/memory.md generation |
| 06-REQ-1.* | 06_hooks_sync_security | Pre/post-session hooks with HookContext |
| 06-REQ-2.* | 06_hooks_sync_security | Hook failure modes (abort/warn) |
| 06-REQ-3.* | 06_hooks_sync_security | Hook timeout enforcement |
| 06-REQ-4.* | 06_hooks_sync_security | Hook context with environment variables |
| 06-REQ-5.* | 06_hooks_sync_security | Hook bypass via --no-hooks |
| 06-REQ-6.* | 06_hooks_sync_security | Sync barriers with configurable interval |
| 06-REQ-7.* | 06_hooks_sync_security | Hot-loading infrastructure |
| 06-REQ-8.* | 06_hooks_sync_security | Command allowlist (~46 default commands) |
| 06-REQ-9.* | 06_hooks_sync_security | Effective allowlist with extend support |
| 07-REQ-1.* | 07_operational_commands | Status report with task counts, tokens, cost |
| 07-REQ-2.* | 07_operational_commands | Standup report with agent activity, human commits |
| 07-REQ-3.* | 07_operational_commands | Output formatters (TABLE, JSON) |
| 07-REQ-4.* | 07_operational_commands | Reset command with cascade unblocking |
| 07-REQ-5.* | 07_operational_commands | Single-task reset and confirmation prompts |
| 08-REQ-1.* | 08_error_autofix | Quality check detection from config files |
| 08-REQ-2.* | 08_error_autofix | Check execution and failure collection |
| 08-REQ-3.* | 08_error_autofix | AI clustering with fallback |
| 08-REQ-4.* | 08_error_autofix | Ephemeral fix spec generation |
| 08-REQ-5.* | 08_error_autofix | Iterative fix loop with termination conditions |
| 08-REQ-6.* | 08_error_autofix | Fix result reporting |
| 08-REQ-7.* | 08_error_autofix | Fix CLI command with --max-passes and --dry-run |
| 09-REQ-1.* | 09_spec_validation | Spec discovery and orchestration |
| 09-REQ-2.* | 09_spec_validation | Missing files check |
| 09-REQ-3.* | 09_spec_validation | Task group size check (>6 subtasks warning) |
| 09-REQ-4.* | 09_spec_validation | Verification step check |
| 09-REQ-5.* | 09_spec_validation | Acceptance criteria check |
| 09-REQ-6.* | 09_spec_validation | Dependency reference check |
| 09-REQ-7.* | 09_spec_validation | Requirement traceability check |
| 09-REQ-8.* | 09_spec_validation | AI-powered semantic analysis |
| 09-REQ-9.* | 09_spec_validation | Multiple output formats with exit codes |
| 11-REQ-1.* | 11_duckdb_knowledge_store | DuckDB lifecycle with VSS extension |
| 11-REQ-2.* | 11_duckdb_knowledge_store | Schema creation (7 tables) |
| 11-REQ-3.* | 11_duckdb_knowledge_store | Forward-only schema migrations |
| 11-REQ-4.* | 11_duckdb_knowledge_store | SessionSink Protocol with dispatcher |
| 11-REQ-5.* | 11_duckdb_knowledge_store | DuckDB sink (always-on sessions, debug-gated tools) |
| 11-REQ-6.* | 11_duckdb_knowledge_store | JSONL sink for raw audit trail |
| 11-REQ-7.* | 11_duckdb_knowledge_store | Graceful degradation |
| 12-REQ-1.* | 12_fox_ball | Dual-write fact persistence (JSONL + DuckDB) |
| 12-REQ-3.* | 12_fox_ball | Vector similarity search with cosine similarity |
| 12-REQ-4.* | 12_fox_ball | ADR and git commit ingestion |
| 12-REQ-5.* | 12_fox_ball | Ask command with RAG pipeline |
| 12-REQ-6.* | 12_fox_ball | Contradiction detection in synthesis |
| 12-REQ-7.* | 12_fox_ball | Supersession tracking via superseded_by column |
| 12-REQ-8.* | 12_fox_ball | Confidence indicator (high/medium/low) |
| 13-REQ-1.* | 13_time_vision | Fact provenance (spec_name, session_id, commit_sha) |
| 13-REQ-2.* | 13_time_vision | Causal link extraction from sessions |
| 13-REQ-3.* | 13_time_vision | Causal graph storage and BFS traversal |
| 13-REQ-4.* | 13_time_vision | Temporal queries with timeline construction |
| 13-REQ-5.* | 13_time_vision | Predictive pattern detection |
| 13-REQ-6.* | 13_time_vision | Timeline rendering as indented text |
| 13-REQ-7.* | 13_time_vision | Context enhancement with causal data |
| 14-REQ-1.2 | 14_cli_banner | Fox art styled with header color role |
| 14-REQ-1.E1 | 14_cli_banner | Invalid header style falls back to default |
| 14-REQ-2.* | 14_cli_banner | Version + model line with fallback |
| 14-REQ-3.* | 14_cli_banner | Working directory with OSError fallback |
| 14-REQ-4.* | 14_cli_banner | Banner on every invocation, --quiet suppression |
| 15-REQ-1.* | 15_session_prompt | test_spec.md included in context assembly |
| 15-REQ-2.* | 15_session_prompt | Template-based prompt with role composition |
| 15-REQ-3.* | 15_session_prompt | Placeholder interpolation |
| 15-REQ-4.* | 15_session_prompt | Frontmatter stripping |
| 15-REQ-5.* | 15_session_prompt | Enriched task prompt with commit/quality instructions |
| 15-REQ-1.* | 15_standup_formatting | Plain-text header with em dash |
| 15-REQ-2.* | 15_standup_formatting | Per-task agent activity lines |
| 15-REQ-3.* | 15_standup_formatting | Human commits section |
| 15-REQ-4.* | 15_standup_formatting | Queue status with ready task list |
| 15-REQ-5.* | 15_standup_formatting | File overlaps section (conditional) |
| 15-REQ-6.* | 15_standup_formatting | All-time total cost line |
| 15-REQ-7.* | 15_standup_formatting | Human-readable token formatting (12.9k, 345) |
| 15-REQ-8.* | 15_standup_formatting | Display node ID (spec/group) |
| 16-REQ-1.* | 16_code_command | Code command registration and plan validation |
| 16-REQ-2.* | 16_code_command | CLI option overrides (--parallel, --no-hooks, etc.) |
| 16-REQ-3.* | 16_code_command | Completion summary output |
| 16-REQ-4.* | 16_code_command | Exit codes (0/1/2/3/130) |
| 16-REQ-5.* | 16_code_command | Session runner factory wiring |
| 17-REQ-1.* | 17_init_claude_settings | Claude settings creation with canonical permissions |
| 17-REQ-2.* | 17_init_claude_settings | Settings merge preserving user entries |
| 18-REQ-1.* | 18_live_progress | Progress display lifecycle (start/stop) |
| 18-REQ-2.* | 18_live_progress | Activity events from session runner |
| 18-REQ-3.* | 18_live_progress | Spinner line rendering |
| 18-REQ-4.* | 18_live_progress | Permanent lines for task events |
| 18-REQ-5.* | 18_live_progress | Integration with code command |
| 18-REQ-6.* | 18_live_progress | Thread and concurrency safety |
| 19-REQ-1.* | 19_git_and_platform_overhaul | Robust develop branch (ensure_develop) |
| 19-REQ-2.* | 19_git_and_platform_overhaul | Push instructions removed from prompts |
| 19-REQ-3.* | 19_git_and_platform_overhaul | Post-harvest remote integration |
| 19-REQ-4.* | 19_git_and_platform_overhaul | GitHub REST API platform (httpx) |
| 19-REQ-5.* | 19_git_and_platform_overhaul | Simplified PlatformConfig (type + auto_merge only) |
| 19-REQ-6.* | 19_git_and_platform_overhaul | Dead code removed (NullPlatform, factory, wait_*) |
| 20-REQ-1.* | 20_plan_analysis | Parallelism analysis with phase grouping |
| 20-REQ-2.* | 20_plan_analysis | Critical path computation (ES/LS/float) |
| 20-REQ-3.* | 20_plan_analysis | Coarse dependency lint rule |
| 20-REQ-4.* | 20_plan_analysis | Circular dependency lint rule (DFS) |
| 20-REQ-5.* | 20_plan_analysis | af-spec dependency granularity guidance |
| 20-REQ-6.* | 20_plan_analysis | Auto-fix for lint findings |
| 21-REQ-1.* | 21_dependency_interface_validation | Backtick identifier extraction |
| 21-REQ-2.* | 21_dependency_interface_validation | AI validation against upstream design.md |
| 21-REQ-3.* | 21_dependency_interface_validation | Batch by upstream spec |
| 21-REQ-4.* | 21_dependency_interface_validation | Integration with --ai pipeline |
| 21-REQ-5.* | 21_dependency_interface_validation | Auto-fix with AI suggestions |
| 22-REQ-1.* | 22_ai_criteria_fix | AI rewrite invocation with --ai --fix |
| 22-REQ-2.* | 22_ai_criteria_fix | EARS syntax rewriting |
| 22-REQ-3.* | 22_ai_criteria_fix | Batch by spec, STANDARD model, batch-of-20 split |
| 22-REQ-4.* | 22_ai_criteria_fix | Integration with fix summary and re-validation |
| 23-REQ-1.* | 23_global_json_flag | Global --json flag on main group |
| 23-REQ-2.* | 23_global_json_flag | Banner suppression in JSON mode |
| 23-REQ-3.* | 23_global_json_flag | JSON output for batch commands |
| 23-REQ-4.* | 23_global_json_flag | JSON output for side-effect commands |
| 23-REQ-5.* | 23_global_json_flag | JSONL output for streaming commands |
| 23-REQ-6.* | 23_global_json_flag | JSON error envelope with exit code preserved |
| 23-REQ-7.* | 23_global_json_flag | JSON input on stdin |
| 23-REQ-8.* | 23_global_json_flag | --format and YAML support removed |

## Drifted Requirements

### 14-REQ-1.1: Fox ASCII Art Display

**Spec says:** THE banner SHALL display the following fox ASCII art:
```
   /\_/\  _
  / o.o \/ \
 ( > ^ < )  )
  \_^/\_/--'
```
(design.md further specifies `FOX_ART = r"""   /\_/\  _` -- string starts immediately after the triple-quote with no leading newline.)

**Code does:** The `FOX_ART` constant in `agent_fox/ui/banner.py:22-26` differs in three ways:
1. The string starts with a newline after the triple-quote (`r"""\n`), producing a blank first line in `splitlines()`.
2. Line 1 has 3 spaces before `_` instead of 2: `   /\_/\   _` vs `   /\_/\  _`.
3. Lines 2-3 have different fox body geometry: `\/\ \` and `) ) )` vs `\/ \` and `)  )`.

**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** low
**Rationale:** The ASCII art was likely modified intentionally to improve the visual appearance (the spec version may not render correctly as a raw string due to backslash escaping). A human should decide which fox art to canonize, then update whichever side is wrong.

---

### 12-REQ-2.1: Embedding Generation Model

**Spec says:** "THE system SHALL generate a vector embedding using the configured embedding model (default: Anthropic voyage-3, 1024 dimensions)." The design.md specifies `from anthropic import Anthropic` and a class using the "Anthropic voyage-3 API."

**Code does:** `agent_fox/knowledge/embeddings.py` uses `sentence_transformers.SentenceTransformer` with the local model `all-MiniLM-L6-v2` (384 dimensions) instead of the Anthropic voyage-3 API (1024 dimensions). The `KnowledgeConfig` in `agent_fox/core/config.py:156-157` defaults to `embedding_model = "all-MiniLM-L6-v2"` and `embedding_dimensions = 384`.

**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** medium
**Rationale:** The local sentence-transformers model is an intentional improvement: it eliminates API cost, removes the dependency on an Anthropic embedding API key, and works offline. The code is configurable (`KnowledgeConfig.embedding_model`) so a user could still use a different model. The spec should be updated to reflect that the default embedding model is a local sentence-transformers model, with the dimensions updated to 384. The DuckDB schema already reads dimensions from config, so it adapts automatically.

---

## Unimplemented Requirements

None.

## Superseded Requirements

| Requirement | Original Spec | Superseded By | Type |
|-------------|--------------|---------------|------|
| 10-REQ-1.* | 10_platform_integration | 19_git_and_platform_overhaul | explicit |
| 10-REQ-2.* | 10_platform_integration | 19_git_and_platform_overhaul | explicit |
| 10-REQ-3.* | 10_platform_integration | 19_git_and_platform_overhaul | explicit |
| 10-REQ-4.* | 10_platform_integration | 19_git_and_platform_overhaul | explicit |
| 10-REQ-5.* | 10_platform_integration | 19_git_and_platform_overhaul | explicit |

Spec 19's `prd.md` contains `## Supersedes` declaring: "`10_platform_integration` -- fully replaced by this spec." All 5 requirements from spec 10 (Platform Protocol, NullPlatform, GitHubPlatform, PR granularity, Platform factory) are superseded. The code correctly reflects spec 19's design: NullPlatform removed, factory removed, `wait_for_ci`/`wait_for_review`/`merge_pr` removed, GitHub platform uses REST API via httpx.

## In-Progress Caveats

None. All 24 specs have 100% of `tasks.md` items checked as complete.

## Extra Behavior (Best-Effort)

- **`agent_fox/_build_info.py`**: Build-time stamp for git revision, not covered by any spec.
- **`agent_fox/_templates/`**: Prompt template files (coding.md, git-flow.md, coordinator.md) referenced by spec 15 but their exact contents are not specified beyond placeholder keys.
- **`docs/errata/`**: Errata directory exists but is not referenced by any spec.
- **`docs/skills.md`**: Skills documentation not covered by a spec.
- **`agent_fox/knowledge/migrations.py`**: Migration registry is empty (no migrations beyond initial schema). Infrastructure is ready but no forward migrations have been written yet.

## Mitigation Summary

| Requirement | Mitigation | Priority |
|-------------|-----------|----------|
| 14-REQ-1.1 | Needs manual review | low |
| 12-REQ-2.1 | Change spec | medium |
