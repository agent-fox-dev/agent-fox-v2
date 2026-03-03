# Spec Audit Report

**Generated:** 2026-03-03
**Branch:** feature/issue-72-remaining-knowledge-wiring
**Specs analyzed:** 18

## Summary

| Category | Count |
|----------|-------|
| Compliant | 161 |
| Drifted | 28 |
| Unimplemented | 5 |
| Superseded | 0 |
| In-progress (expected gaps) | 10 |

## Compliant Requirements

| Requirement | Spec | Description |
|-------------|------|-------------|
| 01-REQ-1.1 | 01_core_foundation | CLI entry point with `--version` and `--help` |
| 01-REQ-1.2 | 01_core_foundation | Extensible subcommand registration |
| 01-REQ-1.4 | 01_core_foundation | `agent-fox` entry point in pyproject.toml |
| 01-REQ-1.E1 | 01_core_foundation | Unknown subcommand handling (exit 2) |
| 01-REQ-2.1 | 01_core_foundation | TOML config loading with pydantic validation |
| 01-REQ-2.2 | 01_core_foundation | Validation errors re-raised as ConfigError |
| 01-REQ-2.3 | 01_core_foundation | Default values for all config fields |
| 01-REQ-2.4 | 01_core_foundation | Config exposes all sections (orchestrator, models, hooks, etc.) |
| 01-REQ-2.6 | 01_core_foundation | Unknown top-level keys logged as warnings |
| 01-REQ-2.E1 | 01_core_foundation | Missing config returns defaults |
| 01-REQ-2.E2 | 01_core_foundation | TOML parse errors re-raised as ConfigError |
| 01-REQ-2.E3 | 01_core_foundation | Numeric fields clamped to valid bounds |
| 01-REQ-3.1 | 01_core_foundation | `init` creates .agent-fox directory structure |
| 01-REQ-3.2 | 01_core_foundation | Ensures develop branch exists |
| 01-REQ-3.3 | 01_core_foundation | Preserves existing config on re-init |
| 01-REQ-3.4 | 01_core_foundation | Updates .gitignore with .agent-fox patterns |
| 01-REQ-3.5 | 01_core_foundation | Validates git repo before init |
| 01-REQ-3.E1 | 01_core_foundation | Idempotent init with missing config.toml |
| 01-REQ-3.E2 | 01_core_foundation | Reports existing develop branch |
| 01-REQ-4.1 | 01_core_foundation | AgentFoxError base exception |
| 01-REQ-4.2 | 01_core_foundation | Full exception hierarchy defined |
| 01-REQ-4.3 | 01_core_foundation | Error context via kwargs |
| 01-REQ-4.E1 | 01_core_foundation | Top-level error handler in CLI |
| 01-REQ-5.1 | 01_core_foundation | ModelTier enum (SIMPLE, STANDARD, ADVANCED) |
| 01-REQ-5.2 | 01_core_foundation | ModelEntry with pricing fields |
| 01-REQ-5.3 | 01_core_foundation | resolve_model accepts tiers and IDs |
| 01-REQ-5.4 | 01_core_foundation | calculate_cost from tokens and pricing |
| 01-REQ-5.E1 | 01_core_foundation | ConfigError for unknown model |
| 01-REQ-6.1 | 01_core_foundation | Structured log format |
| 01-REQ-6.2 | 01_core_foundation | Default WARNING, --verbose switches to DEBUG |
| 01-REQ-6.3 | 01_core_foundation | Named loggers per module |
| 01-REQ-6.E1 | 01_core_foundation | Verbose wins when both verbose and quiet set |
| 01-REQ-7.1 | 01_core_foundation | Theme with color roles |
| 01-REQ-7.2 | 01_core_foundation | create_theme from ThemeConfig |
| 01-REQ-7.3 | 01_core_foundation | Playful fox-themed messages |
| 01-REQ-7.4 | 01_core_foundation | Neutral messages when playful disabled |
| 01-REQ-7.E1 | 01_core_foundation | Style parse error fallback |
| 02-REQ-1.1 | 02_planning_engine | Spec discovery with numeric prefix pattern |
| 02-REQ-1.2 | 02_planning_engine | filter_spec parameter |
| 02-REQ-1.3 | 02_planning_engine | Warning for specs without tasks |
| 02-REQ-1.E1 | 02_planning_engine | PlanError when .specs/ missing |
| 02-REQ-1.E2 | 02_planning_engine | PlanError listing available specs |
| 02-REQ-2.1 | 02_planning_engine | Task group regex parsing |
| 02-REQ-2.2 | 02_planning_engine | Subtask parsing |
| 02-REQ-2.3 | 02_planning_engine | Optional marker detection |
| 02-REQ-2.4 | 02_planning_engine | Title and body extraction |
| 02-REQ-2.E1 | 02_planning_engine | Warning for empty groups |
| 02-REQ-2.E2 | 02_planning_engine | Non-contiguous group numbers accepted |
| 02-REQ-3.1 | 02_planning_engine | Sequential intra-spec edges |
| 02-REQ-3.2 | 02_planning_engine | Cross-spec dependency edges |
| 02-REQ-3.3 | 02_planning_engine | Node ID format spec:group |
| 02-REQ-3.4 | 02_planning_engine | All nodes initialized PENDING |
| 02-REQ-3.E1 | 02_planning_engine | PlanError for missing dependency target |
| 02-REQ-3.E2 | 02_planning_engine | Cycle detection |
| 02-REQ-4.1 | 02_planning_engine | Kahn's algorithm topological sort |
| 02-REQ-4.2 | 02_planning_engine | Deterministic tie-breaking |
| 02-REQ-4.E1 | 02_planning_engine | Empty graph returns empty order |
| 02-REQ-5.1 | 02_planning_engine | Fast mode skips optional nodes |
| 02-REQ-5.2 | 02_planning_engine | Edge rewiring for skipped nodes |
| 02-REQ-5.3 | 02_planning_engine | fast_mode flag in metadata |
| 02-REQ-6.1 | 02_planning_engine | Plan serialization to JSON |
| 02-REQ-6.2 | 02_planning_engine | Plan metadata (timestamps, flags) |
| 02-REQ-6.3 | 02_planning_engine | Cached plan reuse |
| 02-REQ-6.4 | 02_planning_engine | --reanalyze forces rebuild |
| 02-REQ-6.E1 | 02_planning_engine | Corrupt plan triggers rebuild |
| 02-REQ-7.1 | 02_planning_engine | plan CLI command registered |
| 02-REQ-7.2 | 02_planning_engine | --fast flag |
| 02-REQ-7.3 | 02_planning_engine | --spec filter |
| 02-REQ-7.4 | 02_planning_engine | --reanalyze flag |
| 02-REQ-7.5 | 02_planning_engine | --verify placeholder |
| 03-REQ-1.1 | 03_session_and_workspace | Worktree creation at spec/group path |
| 03-REQ-1.2 | 03_session_and_workspace | Feature branch naming convention |
| 03-REQ-1.3 | 03_session_and_workspace | WorkspaceInfo return value |
| 03-REQ-1.E1 | 03_session_and_workspace | Existing worktree removed before recreation |
| 03-REQ-1.E2 | 03_session_and_workspace | Stale branch deleted before creation |
| 03-REQ-1.E3 | 03_session_and_workspace | WorkspaceError on worktree add failure |
| 03-REQ-2.1 | 03_session_and_workspace | Worktree and branch cleanup |
| 03-REQ-2.2 | 03_session_and_workspace | Empty spec directory removed |
| 03-REQ-2.E1 | 03_session_and_workspace | No-op when workspace path missing |
| 03-REQ-2.E2 | 03_session_and_workspace | Warning when branch doesn't exist |
| 03-REQ-3.1 | 03_session_and_workspace | SDK query with options |
| 03-REQ-3.2 | 03_session_and_workspace | Async iterator result collection |
| 03-REQ-3.E1 | 03_session_and_workspace | Exception caught and error captured |
| 03-REQ-3.E2 | 03_session_and_workspace | is_error result handling |
| 03-REQ-4.2 | 03_session_and_workspace | Memory facts included in context |
| 03-REQ-4.3 | 03_session_and_workspace | Single string with section headers |
| 03-REQ-4.E1 | 03_session_and_workspace | Missing files skipped with warning |
| 03-REQ-5.2 | 03_session_and_workspace | Task prompt with group and instructions |
| 03-REQ-6.2 | 03_session_and_workspace | TimeoutError status handling |
| 03-REQ-6.E1 | 03_session_and_workspace | Partial metrics preserved on timeout |
| 03-REQ-7.1 | 03_session_and_workspace | Fast-forward merge attempted |
| 03-REQ-7.3 | 03_session_and_workspace | Changed files returned after merge |
| 03-REQ-7.E1 | 03_session_and_workspace | Rebase abort on failure |
| 03-REQ-7.E2 | 03_session_and_workspace | No-op on no new commits |
| 03-REQ-8.E1 | 03_session_and_workspace | Empty command blocked |
| 03-REQ-9.1 | 03_session_and_workspace | Git operations module |
| 03-REQ-9.2 | 03_session_and_workspace | Git errors raise typed exceptions |
| 04-REQ-1.1 | 04_orchestrator | Plan loading and ready task identification |
| 04-REQ-1.2 | 04_orchestrator | Serial and parallel dispatch modes |
| 04-REQ-1.3 | 04_orchestrator | Post-session state update and re-evaluation |
| 04-REQ-1.4 | 04_orchestrator | Stall detection and warning |
| 04-REQ-1.E1 | 04_orchestrator | PlanError on missing/corrupt plan file |
| 04-REQ-1.E2 | 04_orchestrator | Empty plan returns immediately |
| 04-REQ-2.1 | 04_orchestrator | Retry on failure within max_retries |
| 04-REQ-2.2 | 04_orchestrator | Previous error passed on retry |
| 04-REQ-2.3 | 04_orchestrator | Block task after exhausting retries |
| 04-REQ-2.E1 | 04_orchestrator | max_retries=0 means no retry |
| 04-REQ-3.1 | 04_orchestrator | BFS cascade blocking |
| 04-REQ-3.E1 | 04_orchestrator | Transitive cascade covers all paths |
| 04-REQ-4.1 | 04_orchestrator | JSONL state persistence after each session |
| 04-REQ-4.2 | 04_orchestrator | ExecutionState includes all fields |
| 04-REQ-4.3 | 04_orchestrator | State resume and plan hash verification |
| 04-REQ-4.E2 | 04_orchestrator | Corrupt state triggers fresh init |
| 04-REQ-5.1 | 04_orchestrator | Cost limit enforcement |
| 04-REQ-5.2 | 04_orchestrator | Prevents new launches, doesn't cancel running |
| 04-REQ-5.3 | 04_orchestrator | Session limit enforcement |
| 04-REQ-5.E1 | 04_orchestrator | In-flight tasks not cancelled |
| 04-REQ-6.1 | 04_orchestrator | Parallel execution via asyncio |
| 04-REQ-6.2 | 04_orchestrator | Parallelism clamped to 1-8 |
| 04-REQ-6.E1 | 04_orchestrator | Only launches as many as ready |
| 04-REQ-7.1 | 04_orchestrator | Exactly-once dispatch via status tracking |
| 04-REQ-7.2 | 04_orchestrator | Completed tasks preserved on resume |
| 04-REQ-7.E1 | 04_orchestrator | In-progress tasks reset to pending on resume |
| 04-REQ-8.1 | 04_orchestrator | SIGINT saves state |
| 04-REQ-8.2 | 04_orchestrator | Cancel in-flight tasks on interrupt |
| 04-REQ-8.3 | 04_orchestrator | Log resume command on interrupt |
| 04-REQ-8.E1 | 04_orchestrator | Second SIGINT hard exits |
| 04-REQ-9.1 | 04_orchestrator | Inter-session delay with asyncio.sleep |
| 04-REQ-9.E1 | 04_orchestrator | Delay skipped when value is 0 |
| 04-REQ-10.1 | 04_orchestrator | mark_completed triggers re-evaluation |
| 04-REQ-10.2 | 04_orchestrator | mark_blocked cascades transitively |
| 04-REQ-10.E1 | 04_orchestrator | Stall detection and RunStatus.STALLED |
| 05-REQ-1.1 | 05_structured_memory | LLM extraction with anthropic SDK |
| 05-REQ-1.2 | 05_structured_memory | Structured prompt for content/category/confidence |
| 05-REQ-1.3 | 05_structured_memory | UUID and timestamp generation |
| 05-REQ-1.E1 | 05_structured_memory | Invalid JSON returns empty list |
| 05-REQ-1.E2 | 05_structured_memory | Empty extraction logged |
| 05-REQ-2.1 | 05_structured_memory | Six-value Category enum |
| 05-REQ-2.2 | 05_structured_memory | Invalid category defaults to gotcha |
| 05-REQ-3.1 | 05_structured_memory | JSONL storage at .agent-fox/memory.jsonl |
| 05-REQ-3.2 | 05_structured_memory | Full fact serialization/deserialization |
| 05-REQ-3.3 | 05_structured_memory | Append mode writing |
| 05-REQ-3.E1 | 05_structured_memory | Parent directory auto-creation |
| 05-REQ-3.E2 | 05_structured_memory | OSError caught and logged |
| 05-REQ-4.1 | 05_structured_memory | Keyword and spec_name matching |
| 05-REQ-4.2 | 05_structured_memory | Relevance scoring with recency bonus |
| 05-REQ-4.3 | 05_structured_memory | Budget-limited results |
| 05-REQ-4.E1 | 05_structured_memory | Empty results on no matches |
| 05-REQ-4.E2 | 05_structured_memory | Empty results when no facts exist |
| 05-REQ-5.1 | 05_structured_memory | SHA-256 content deduplication |
| 05-REQ-5.2 | 05_structured_memory | Supersession chain resolution |
| 05-REQ-5.3 | 05_structured_memory | File overwrite on compaction |
| 05-REQ-5.E1 | 05_structured_memory | No-op on empty store |
| 05-REQ-5.E2 | 05_structured_memory | Idempotent compaction |
| 05-REQ-6.1 | 05_structured_memory | Markdown summary by category |
| 05-REQ-6.2 | 05_structured_memory | Fact format with provenance |
| 05-REQ-6.3 | 05_structured_memory | Summary rendered at sync barriers |
| 05-REQ-6.E1 | 05_structured_memory | Auto-creates docs directory |
| 05-REQ-6.E2 | 05_structured_memory | Empty summary message |
| 06-REQ-1.1 | 06_hooks_sync_security | Pre-session hooks execution |
| 06-REQ-1.2 | 06_hooks_sync_security | Post-session hooks execution |
| 06-REQ-1.E1 | 06_hooks_sync_security | Empty scripts list returns empty |
| 06-REQ-2.1 | 06_hooks_sync_security | Abort mode raises HookError |
| 06-REQ-2.2 | 06_hooks_sync_security | Warn mode logs and continues |
| 06-REQ-2.3 | 06_hooks_sync_security | Per-hook mode configuration |
| 06-REQ-2.E1 | 06_hooks_sync_security | FileNotFoundError and OSError handling |
| 06-REQ-3.1 | 06_hooks_sync_security | Hook timeout via subprocess |
| 06-REQ-3.2 | 06_hooks_sync_security | TimeoutExpired handling |
| 06-REQ-4.1 | 06_hooks_sync_security | AF_ environment variables |
| 06-REQ-4.2 | 06_hooks_sync_security | Sync barrier context |
| 06-REQ-5.1 | 06_hooks_sync_security | Hook bypass flag |
| 06-REQ-6.1 | 06_hooks_sync_security | Sync barrier trigger formula |
| 06-REQ-6.2 | 06_hooks_sync_security | Summary regeneration at barriers |
| 06-REQ-6.3 | 06_hooks_sync_security | Hot-load at sync barriers |
| 06-REQ-6.E1 | 06_hooks_sync_security | No barrier when sync_interval=0 |
| 06-REQ-7.1 | 06_hooks_sync_security | Hot-load spec discovery and parsing |
| 06-REQ-7.2 | 06_hooks_sync_security | Cross-spec dependency resolution |
| 06-REQ-7.3 | 06_hooks_sync_security | Topological re-ordering |
| 06-REQ-7.E1 | 06_hooks_sync_security | Invalid dependency warning and skip |
| 06-REQ-7.E2 | 06_hooks_sync_security | No-op when no new specs |
| 06-REQ-8.1 | 06_hooks_sync_security | Command extraction from Bash tool |
| 06-REQ-8.2 | 06_hooks_sync_security | Blocked command with alternatives |
| 06-REQ-8.3 | 06_hooks_sync_security | 46-command default allowlist |
| 06-REQ-8.E1 | 06_hooks_sync_security | SecurityError for empty commands |
| 06-REQ-8.E2 | 06_hooks_sync_security | Non-Bash tools allowed |
| 06-REQ-9.1 | 06_hooks_sync_security | Custom allowlist replaces defaults |
| 06-REQ-9.2 | 06_hooks_sync_security | Extend allowlist adds to defaults |
| 06-REQ-9.E1 | 06_hooks_sync_security | Both set: allowlist wins with warning |
| 07-REQ-1.1 | 07_operational_commands | Status report from state and plan |
| 07-REQ-1.2 | 07_operational_commands | Token and cost reporting |
| 07-REQ-1.3 | 07_operational_commands | Problem task identification |
| 07-REQ-1.E1 | 07_operational_commands | Zero state with no state file |
| 07-REQ-1.E2 | 07_operational_commands | Error on missing plan file |
| 07-REQ-2.1 | 07_operational_commands | Standup with window filtering |
| 07-REQ-2.4 | 07_operational_commands | Queue summary with task counts |
| 07-REQ-2.E1 | 07_operational_commands | Empty session window handling |
| 07-REQ-2.E2 | 07_operational_commands | Git log failure returns empty |
| 07-REQ-3.1 | 07_operational_commands | --format table/json/yaml |
| 07-REQ-3.2 | 07_operational_commands | JSON output with indent |
| 07-REQ-3.3 | 07_operational_commands | YAML output |
| 07-REQ-3.4 | 07_operational_commands | --output file writing |
| 07-REQ-3.E1 | 07_operational_commands | File write error handling |
| 07-REQ-4.1 | 07_operational_commands | Reset failed/blocked/in-progress to pending |
| 07-REQ-4.2 | 07_operational_commands | Worktree and branch cleanup |
| 07-REQ-4.3 | 07_operational_commands | Confirmation prompt before reset |
| 07-REQ-4.4 | 07_operational_commands | --yes flag skips confirmation |
| 07-REQ-4.E1 | 07_operational_commands | Nothing to reset message |
| 07-REQ-4.E2 | 07_operational_commands | Error on missing state file |
| 07-REQ-5.1 | 07_operational_commands | Single-task reset to pending |
| 07-REQ-5.2 | 07_operational_commands | Sole-blocker dependent cascade |
| 07-REQ-5.3 | 07_operational_commands | No confirmation for single-task |
| 07-REQ-5.E1 | 07_operational_commands | Error on invalid task ID |
| 07-REQ-5.E2 | 07_operational_commands | Completed tasks cannot be reset |
| 08-REQ-1.1 | 08_error_autofix | Quality check detection from config files |
| 08-REQ-1.2 | 08_error_autofix | All seven detection rules match spec |
| 08-REQ-1.3 | 08_error_autofix | CheckDescriptor and CheckCategory types |
| 08-REQ-1.E1 | 08_error_autofix | Empty checks error and exit 1 |
| 08-REQ-1.E2 | 08_error_autofix | Parse error returns empty list |
| 08-REQ-2.1 | 08_error_autofix | subprocess.run with capture |
| 08-REQ-2.2 | 08_error_autofix | FailureRecord from non-zero exit |
| 08-REQ-2.3 | 08_error_autofix | Passed checks collected separately |
| 08-REQ-2.E1 | 08_error_autofix | Timeout handling |
| 08-REQ-3.1 | 08_error_autofix | AI clustering with Anthropic SDK |
| 08-REQ-3.2 | 08_error_autofix | FailureCluster with label and approach |
| 08-REQ-3.3 | 08_error_autofix | Fallback clustering by check name |
| 08-REQ-4.1 | 08_error_autofix | Fix spec generation (requirements/design/tasks) |
| 08-REQ-6.1 | 08_error_autofix | Fix report rendering |
| 08-REQ-6.2 | 08_error_autofix | TerminationReason enum with labels |
| 08-REQ-7.1 | 08_error_autofix | fix CLI command registered |
| 08-REQ-7.2 | 08_error_autofix | --max-passes option |
| 08-REQ-7.E1 | 08_error_autofix | max_passes clamped to >= 1 |
| 09-REQ-1.1 | 09_spec_validation | lint_spec uses spec discovery |
| 09-REQ-1.2 | 09_spec_validation | All rules run against each spec |
| 09-REQ-1.3 | 09_spec_validation | Findings sorted by spec/file/severity |
| 09-REQ-1.E1 | 09_spec_validation | No specs found error |
| 09-REQ-2.1 | 09_spec_validation | Five expected files checked |
| 09-REQ-2.2 | 09_spec_validation | Error finding per missing file |
| 09-REQ-3.1 | 09_spec_validation | Subtask count excluding verification |
| 09-REQ-3.2 | 09_spec_validation | Warning for oversized groups |
| 09-REQ-4.1 | 09_spec_validation | Verification step detection |
| 09-REQ-4.2 | 09_spec_validation | Warning for missing verification |
| 09-REQ-5.1 | 09_spec_validation | Acceptance criteria scanning |
| 09-REQ-5.2 | 09_spec_validation | Error for missing criteria |
| 09-REQ-6.1 | 09_spec_validation | Dependency table parsing |
| 09-REQ-6.2 | 09_spec_validation | Error for unknown dependency spec |
| 09-REQ-6.3 | 09_spec_validation | Group number cross-reference |
| 09-REQ-7.1 | 09_spec_validation | Requirement ID collection |
| 09-REQ-7.2 | 09_spec_validation | Warning for untraced requirements |
| 09-REQ-8.1 | 09_spec_validation | --ai flag triggers AI validation |
| 09-REQ-8.2 | 09_spec_validation | Vague criterion detection |
| 09-REQ-8.3 | 09_spec_validation | Implementation leak detection |
| 09-REQ-8.E1 | 09_spec_validation | AI failure returns empty list |
| 09-REQ-9.1 | 09_spec_validation | --format table/json/yaml |
| 09-REQ-9.3 | 09_spec_validation | JSON and YAML serialization |
| 09-REQ-9.4 | 09_spec_validation | Exit 1 on error-severity findings |
| 09-REQ-9.5 | 09_spec_validation | Exit 0 with no errors |
| 10-REQ-1.1 | 10_platform_integration | Platform protocol definition |
| 10-REQ-1.2 | 10_platform_integration | create_pr signature |
| 10-REQ-1.3 | 10_platform_integration | wait_for_ci signature |
| 10-REQ-1.4 | 10_platform_integration | wait_for_review signature |
| 10-REQ-1.5 | 10_platform_integration | merge_pr signature |
| 10-REQ-2.1 | 10_platform_integration | NullPlatform satisfies protocol |
| 10-REQ-2.2 | 10_platform_integration | NullPlatform create_pr merges directly |
| 10-REQ-2.3 | 10_platform_integration | NullPlatform wait_for_ci returns True |
| 10-REQ-2.4 | 10_platform_integration | NullPlatform wait_for_review returns True |
| 10-REQ-2.5 | 10_platform_integration | NullPlatform merge_pr is no-op |
| 10-REQ-3.1 | 10_platform_integration | GitHubPlatform satisfies protocol |
| 10-REQ-3.2 | 10_platform_integration | gh pr create execution |
| 10-REQ-3.3 | 10_platform_integration | gh pr checks polling |
| 10-REQ-3.4 | 10_platform_integration | gh pr view review polling |
| 10-REQ-3.5 | 10_platform_integration | gh pr merge execution |
| 10-REQ-3.E1 | 10_platform_integration | gh availability verification |
| 10-REQ-3.E2 | 10_platform_integration | IntegrationError on create failure |
| 10-REQ-3.E3 | 10_platform_integration | CI check failure detection |
| 10-REQ-3.E4 | 10_platform_integration | CI timeout returns False |
| 10-REQ-3.E5 | 10_platform_integration | Review rejection returns False |
| 10-REQ-3.E6 | 10_platform_integration | IntegrationError on merge failure |
| 10-REQ-5.1 | 10_platform_integration | create_platform factory function |
| 10-REQ-5.2 | 10_platform_integration | "none" returns NullPlatform |
| 10-REQ-5.3 | 10_platform_integration | "github" returns GitHubPlatform |
| 10-REQ-5.E1 | 10_platform_integration | ConfigError for unknown platform type |
| 11-REQ-1.1 | 11_duckdb_knowledge_store | DuckDB connection at store_path |
| 11-REQ-1.2 | 11_duckdb_knowledge_store | VSS extension loading |
| 11-REQ-1.3 | 11_duckdb_knowledge_store | Connection close |
| 11-REQ-1.E1 | 11_duckdb_knowledge_store | Parent directory auto-creation |
| 11-REQ-1.E2 | 11_duckdb_knowledge_store | Open error wrapped in KnowledgeStoreError |
| 11-REQ-2.1 | 11_duckdb_knowledge_store | Seven tables with CREATE IF NOT EXISTS |
| 11-REQ-2.2 | 11_duckdb_knowledge_store | Version 1 initial schema |
| 11-REQ-2.3 | 11_duckdb_knowledge_store | Configurable embedding dimensions |
| 11-REQ-3.1 | 11_duckdb_knowledge_store | Migration application |
| 11-REQ-3.2 | 11_duckdb_knowledge_store | Migration dataclass with version/apply |
| 11-REQ-3.3 | 11_duckdb_knowledge_store | Version recording after migration |
| 11-REQ-3.E1 | 11_duckdb_knowledge_store | Migration failure raises KnowledgeStoreError |
| 11-REQ-4.1 | 11_duckdb_knowledge_store | SessionSink protocol with runtime_checkable |
| 11-REQ-4.2 | 11_duckdb_knowledge_store | SinkDispatcher multi-sink dispatch |
| 11-REQ-4.3 | 11_duckdb_knowledge_store | Fault isolation between sinks |
| 11-REQ-5.1 | 11_duckdb_knowledge_store | DuckDBSink implements all methods |
| 11-REQ-5.2 | 11_duckdb_knowledge_store | session_outcomes always written |
| 11-REQ-5.3 | 11_duckdb_knowledge_store | tool_calls debug-gated |
| 11-REQ-5.4 | 11_duckdb_knowledge_store | Debug disabled skips tool writes |
| 11-REQ-5.E1 | 11_duckdb_knowledge_store | Write failures non-fatal |
| 11-REQ-6.1 | 11_duckdb_knowledge_store | JsonlSink implements all methods |
| 11-REQ-6.2 | 11_duckdb_knowledge_store | JSON line writing |
| 11-REQ-6.3 | 11_duckdb_knowledge_store | Debug gating at orchestrator level |
| 11-REQ-7.1 | 11_duckdb_knowledge_store | open_knowledge_store returns None on failure |
| 11-REQ-7.2 | 11_duckdb_knowledge_store | DuckDB sink swallows write failures |
| 11-REQ-7.3 | 11_duckdb_knowledge_store | Graceful operation without DuckDB |
| 12-REQ-1.1 | 12_fox_ball | Dual-write to JSONL and DuckDB |
| 12-REQ-1.2 | 12_fox_ball | JSONL written first, DuckDB best-effort |
| 12-REQ-1.E1 | 12_fox_ball | DuckDB failure non-fatal |
| 12-REQ-2.1 | 12_fox_ball | Embedding generation via API |
| 12-REQ-2.2 | 12_fox_ball | Batch embedding in single API call |
| 12-REQ-2.E1 | 12_fox_ball | Embedding failure non-fatal |
| 12-REQ-2.E2 | 12_fox_ball | Query embedding failure reported to user |
| 12-REQ-3.1 | 12_fox_ball | Cosine similarity search |
| 12-REQ-3.2 | 12_fox_ball | top_k results with SearchResult fields |
| 12-REQ-3.3 | 12_fox_ball | Inner join excludes unembedded facts |
| 12-REQ-3.E1 | 12_fox_ball | Empty results on error or no matches |
| 12-REQ-4.1 | 12_fox_ball | ADR ingestion |
| 12-REQ-4.2 | 12_fox_ball | Git commit ingestion |
| 12-REQ-4.3 | 12_fox_ball | Facts stored with embeddings |
| 12-REQ-5.1 | 12_fox_ball | Full RAG pipeline in ask command |
| 12-REQ-5.2 | 12_fox_ball | Provenance and source citations |
| 12-REQ-5.3 | 12_fox_ball | Single API call synthesis |
| 12-REQ-5.E1 | 12_fox_ball | Empty store message |
| 12-REQ-5.E2 | 12_fox_ball | Unavailable store error |
| 12-REQ-6.1 | 12_fox_ball | Contradiction detection and display |
| 12-REQ-7.1 | 12_fox_ball | mark_superseded updates DuckDB |
| 12-REQ-7.2 | 12_fox_ball | Superseded facts excluded from search |
| 12-REQ-8.1 | 12_fox_ball | Confidence scoring (high/medium/low) |
| 13-REQ-1.2 | 13_time_vision | NULL allowed for provenance fields |
| 13-REQ-2.1 | 13_time_vision | Causal extraction addendum in prompt |
| 13-REQ-2.2 | 13_time_vision | Causal link parsing and storage |
| 13-REQ-2.E1 | 13_time_vision | Parse failure returns empty list |
| 13-REQ-3.4 | 13_time_vision | BFS causal chain traversal |
| 13-REQ-3.E1 | 13_time_vision | Idempotent INSERT OR IGNORE |
| 13-REQ-5.2 | 13_time_vision | Pattern with trigger/effect/confidence |
| 13-REQ-5.3 | 13_time_vision | patterns CLI command |
| 13-REQ-5.E1 | 13_time_vision | No patterns message |
| 13-REQ-7.1 | 13_time_vision | Causal context enhancement |
| 13-REQ-7.2 | 13_time_vision | Budget-limited causal facts |
| 14-REQ-1.1 | 14_cli_banner | FOX_ART constant with ASCII art |
| 14-REQ-1.2 | 14_cli_banner | Header color role applied |
| 14-REQ-1.E1 | 14_cli_banner | Default header style fallback |
| 14-REQ-2.1 | 14_cli_banner | Version and model display format |
| 14-REQ-2.2 | 14_cli_banner | Model resolution via resolve_model |
| 14-REQ-2.3 | 14_cli_banner | Version/model with header style |
| 14-REQ-3.1 | 14_cli_banner | Working directory on own line |
| 14-REQ-3.2 | 14_cli_banner | Muted style for working directory |
| 14-REQ-3.E1 | 14_cli_banner | OSError fallback to "(unknown)" |
| 14-REQ-4.1 | 14_cli_banner | Banner on every invocation |
| 14-REQ-4.2 | 14_cli_banner | --quiet suppresses banner |
| 14-REQ-4.E1 | 14_cli_banner | --version exits before banner |
| 15-REQ-1.1 | 15_session_prompt | test_spec.md in context assembly |
| 15-REQ-1.2 | 15_session_prompt | test_spec.md ordering after design.md |
| 15-REQ-1.E1 | 15_session_prompt | Missing test_spec.md logged and skipped |
| 15-REQ-2.1 | 15_session_prompt | Package-relative template resolution |
| 15-REQ-2.2 | 15_session_prompt | Coding role loads coding.md + git-flow.md |
| 15-REQ-2.3 | 15_session_prompt | Coordinator role loads coordinator.md |
| 15-REQ-2.4 | 15_session_prompt | role parameter with default "coding" |
| 15-REQ-2.5 | 15_session_prompt | Context appended after template |
| 15-REQ-2.E1 | 15_session_prompt | ConfigError for missing template |
| 15-REQ-2.E2 | 15_session_prompt | ValueError for unknown role |
| 15-REQ-3.1 | 15_session_prompt | Placeholder interpolation |
| 15-REQ-3.2 | 15_session_prompt | Unrecognized placeholders preserved |
| 15-REQ-3.E1 | 15_session_prompt | Literal braces preserved |
| 15-REQ-4.1 | 15_session_prompt | Frontmatter stripping |
| 15-REQ-4.2 | 15_session_prompt | No frontmatter returns unchanged |
| 15-REQ-5.1 | 15_session_prompt | Task prompt with spec/group/tasks |
| 15-REQ-5.2 | 15_session_prompt | Checkbox and commit instructions |
| 15-REQ-5.3 | 15_session_prompt | Test and linter reminders |
| 15-REQ-5.E1 | 15_session_prompt | ValueError for task_group < 1 |
| 15-REQ-1.1 | 15_standup_formatting | Header with em dash and hours |
| 15-REQ-1.2 | 15_standup_formatting | Generated timestamp |
| 15-REQ-1.3 | 15_standup_formatting | Blank line after header |
| 15-REQ-1.E1 | 15_standup_formatting | Singular hour format works |
| 15-REQ-2.1 | 15_standup_formatting | Agent Activity section |
| 15-REQ-2.2 | 15_standup_formatting | Per-task line format with tokens |
| 15-REQ-2.3 | 15_standup_formatting | TaskActivity dataclass with all fields |
| 15-REQ-2.E1 | 15_standup_formatting | Empty activity message |
| 15-REQ-3.1 | 15_standup_formatting | Human Commits section format |
| 15-REQ-3.E1 | 15_standup_formatting | No human commits message |
| 15-REQ-4.1 | 15_standup_formatting | Queue Status summary line |
| 15-REQ-4.2 | 15_standup_formatting | Ready tasks display |
| 15-REQ-4.3 | 15_standup_formatting | QueueSummary dataclass |
| 15-REQ-4.E1 | 15_standup_formatting | Ready line omitted when empty |
| 15-REQ-5.1 | 15_standup_formatting | File Overlaps section format |
| 15-REQ-5.E1 | 15_standup_formatting | Section omitted when no overlaps |
| 15-REQ-6.1 | 15_standup_formatting | Total Cost display |
| 15-REQ-6.2 | 15_standup_formatting | total_cost field on StandupReport |
| 15-REQ-6.E1 | 15_standup_formatting | Default 0.0 when no state |
| 15-REQ-8.1 | 15_standup_formatting | Node ID colon-to-slash replacement |
| 15-REQ-8.2 | 15_standup_formatting | All task IDs use display format |
| 16-REQ-1.1 | 16_code_command | code CLI command registered |
| 16-REQ-1.2 | 16_code_command | Config loaded from Click context |
| 16-REQ-1.3 | 16_code_command | Orchestrator construction |
| 16-REQ-1.4 | 16_code_command | asyncio.run(orchestrator.run()) |
| 16-REQ-1.E1 | 16_code_command | Missing plan error with exit 1 |
| 16-REQ-1.E2 | 16_code_command | Exception handling with exit 1 |
| 16-REQ-2.1 | 16_code_command | --parallel option |
| 16-REQ-2.2 | 16_code_command | --no-hooks flag |
| 16-REQ-2.3 | 16_code_command | --max-cost option |
| 16-REQ-2.4 | 16_code_command | --max-sessions option |
| 16-REQ-2.5 | 16_code_command | CLI overrides applied without persisting |
| 16-REQ-2.E1 | 16_code_command | Clamping delegated to OrchestratorConfig |
| 16-REQ-3.1 | 16_code_command | Summary with tokens, cost, status |
| 16-REQ-3.E1 | 16_code_command | No tasks message |
| 16-REQ-4.1 | 16_code_command | Exit 0 for completed |
| 16-REQ-4.2 | 16_code_command | Exit 1 for unrecognized status |
| 16-REQ-4.3 | 16_code_command | Exit 2 for stalled |
| 16-REQ-4.4 | 16_code_command | Exit 3 for cost/session limit |
| 16-REQ-4.5 | 16_code_command | Exit 130 for interrupted |
| 16-REQ-4.E1 | 16_code_command | Default exit 1 for unknown status |
| 16-REQ-5.1 | 16_code_command | Full session runner with config |
| 16-REQ-5.2 | 16_code_command | session_runner_factory injection |
| 16-REQ-5.E1 | 16_code_command | Session failure returns failed record |

## Drifted Requirements

### 01-REQ-1.3: Banner display scope

**Spec says:** "display a themed banner with the project name and version when invoked without a subcommand"
**Code does:** Banner renders on *every* CLI invocation (before subcommand dispatch), not only when no subcommand is given.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The code's behavior (always showing the banner) is a reasonable UX choice and likely intentional. The spec should be updated to reflect the actual intended behavior, which was confirmed as correct in spec 14 (14-REQ-4.1: "banner renders on every CLI invocation").

---

### 01-REQ-2.5: CLI overrides for config values

**Spec says:** "WHERE a command-line option overrides a configuration value, THE system SHALL prefer the command-line value."
**Code does:** The `load_config()` function only accepts a path, not CLI overrides. However, spec 16's `_apply_overrides()` in `code.py` does apply CLI options (--parallel, --max-cost, etc.) to the config object at command level.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The override mechanism exists but is implemented at the command level (spec 16) rather than in the core config loader (spec 01). The functional requirement is met; only the architectural location differs. Update the spec to clarify that CLI overrides are applied per-command, not in `load_config()`.

---

### 03-REQ-3.3: SessionOutcome files_touched

**Spec says:** SessionOutcome should capture `files_touched` from the session.
**Code does:** `files_touched` field exists on `SessionOutcome` with `default_factory=list` but is never populated by `run_session()` -- always an empty list.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** The field exists structurally but is never populated. This causes downstream impact: standup file overlap detection (07-REQ-2.3) is functionally disabled because it receives empty agent file lists. A corrective spec should wire touched file detection into the session runner.

---

### 03-REQ-3.4 / 03-REQ-8.1 / 03-REQ-8.2: Allowlist hook not wired

**Spec says:** The session runner SHALL register the allowlist hook with the SDK to enforce command restrictions.
**Code does:** `build_allowlist_hook()` exists and correctly implements the hook callback, but `run_session()` never passes it to `ClaudeCodeOptions`. The hook is defined but disconnected.
**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** high
**Rationale:** This is a security-relevant gap. The allowlist enforcement mechanism is correctly implemented but not wired into the session execution path. This may be intentional (relying on the SDK's own permission model with `bypassPermissions`) or an omission. Needs human decision on whether the allowlist should be enforced alongside SDK permissions.

---

### 03-REQ-4.1: Context assembly file list

**Spec says:** Read `requirements.md`, `design.md`, and `tasks.md` for context.
**Code does:** Reads four files: `requirements.md`, `design.md`, `test_spec.md`, and `tasks.md` (extra file).
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Including `test_spec.md` is an enhancement added by spec 15. The original spec 03 should be updated to reflect the current file list, or noted as superseded by spec 15 on this point.

---

### 03-REQ-5.1: System prompt construction

**Spec says:** System prompt includes role, context, task group, and instructions via inline construction.
**Code does:** Uses template-based loading from `_templates/prompts/` with interpolation. Adds a `role` parameter.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Template-based prompt construction is a clear improvement over inline strings, implemented by spec 15. The spec should be updated to reflect the template approach.

---

### 03-REQ-6.1: Timeout module location

**Spec says:** `session/timeout.py` as a separate module.
**Code does:** `with_timeout()` is defined inline in `session/runner.py`.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Inlining a single function is simpler. The spec should reflect the actual module structure.

---

### 03-REQ-7.2: Rebase abstraction

**Spec says:** Use the rebase abstraction layer from git.py.
**Code does:** Harvester calls `run_git(["rebase", dev_branch])` directly rather than using `rebase_onto()`.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** low
**Rationale:** Minor consistency issue. The git abstraction layer exists but is bypassed. A get-well should update the harvester to use `rebase_onto()`.

---

### 04-REQ-3.2: Cascade blocking reason

**Spec says:** Record the blocking reason on each cascade-blocked task.
**Code does:** Reason is only logged, not persisted per-node in the state model. No `block_reason` field exists.
**Drift type:** missing-edge-case
**Suggested mitigation:** Needs manual review
**Priority:** medium
**Rationale:** The blocking reason is logged but not queryable. Whether a per-node reason field is needed depends on whether downstream consumers (status reports, reset logic) need to display why a task is blocked.

---

### 04-REQ-4.E1: Plan hash mismatch handling

**Spec says:** Warn the user and offer to start fresh or abort on plan hash mismatch.
**Code does:** Only logs a warning and unconditionally starts fresh -- no interactive choice.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** In an automated agent context, prompting the user interactively may not be practical. The code's behavior (warn and continue) is reasonable for the use case. Update the spec.

---

### 04-REQ-6.3: State lock in parallel execution

**Spec says:** State writes SHALL be serialized using an asyncio lock during parallel execution.
**Code does:** The `_state_lock` exists on `ParallelRunner` but is only used in `execute_batch()` (test path). The runtime streaming pool in `_dispatch_parallel()` processes results sequentially in the event loop -- functionally safe but doesn't use the lock.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Single-threaded asyncio event loop provides sequential processing guarantees. The lock is unnecessary in the runtime path. The spec should be updated to reflect the actual concurrency model.

---

### 04-REQ-9.2: Inter-session delay skip

**Spec says:** Delay SHALL be skipped when no more ready tasks exist.
**Code does:** Delay is applied before dispatch; loop breaks after one task to re-evaluate. Delay may be applied even if no tasks become ready after the next completion.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** low
**Rationale:** Minor inefficiency -- unnecessary delay in some cases. A get-well should check for remaining ready tasks before applying the delay.

---

### 07-REQ-2.2: Human commit filtering

**Spec says:** Filter git log using `--invert-grep --author=<agent_author>` to exclude agent commits.
**Code does:** Fetches ALL commits and partitions in Python using `is_agent_commit()` which classifies by author name AND conventional-commit prefixes AND merge-branch patterns.
**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** medium
**Rationale:** The Python-side heuristic is broader than the spec's git-level author filter. Human commits using conventional commit format could be misclassified as agent commits. This may be intentional (better classification) or a regression.

---

### 07-REQ-2.3: File overlap detection

**Spec says:** Detect file overlaps between agent and human changes.
**Code does:** `_detect_overlaps()` exists but is called with empty `agent_files` dict because `SessionRecord` does not track `touched_paths`. Feature is structurally present but functionally disabled.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Directly caused by 03-REQ-3.3 drift (files_touched never populated). Fixing the upstream issue will enable this feature.

---

### 07-REQ-2.5: Cost breakdown by model tier

**Spec says:** Cost breakdown by model tier in standup report.
**Code does:** Groups all sessions under a single "default" tier because `SessionRecord` lacks the `model` field specified in the design.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** The `SessionRecord` dataclass is missing the `model` field. Adding it and populating it from session execution would enable the per-tier breakdown.

---

### 08-REQ-4.2: Fix spec directory naming

**Spec says:** Write fix specs to `.agent-fox/fix_specs/` with names from cluster labels.
**Code does:** Uses `pass_{pass_number}_{sanitized_label}/` naming (includes pass number prefix).
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Including the pass number is a reasonable enhancement for debugging multi-pass runs. Update the spec.

---

### 08-REQ-5.1: Fix loop session execution

**Spec says:** Fix loop iterates: run checks, cluster, generate specs, run coding sessions for each cluster, re-run.
**Code does:** Loop generates fix specs but does NOT run coding sessions. Comment says "Session runner integration is handled at the CLI level."
**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** high
**Rationale:** This is a significant functional gap. The fix loop generates specs but never applies fixes, making the iterative loop ineffective. This may be intentional (deferring session integration) or an omission. Needs human decision on whether to wire in SessionRunner.

---

### 08-REQ-5.2: COST_LIMIT termination

**Spec says:** Cost limit as a termination condition for the fix loop.
**Code does:** `COST_LIMIT` enum value exists but is never evaluated during the loop. Cost tracking is not implemented.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Linked to 08-REQ-5.1 -- without session execution, there is no cost to track. If sessions are wired in, cost tracking must be added.

---

### 08-REQ-5.3: Fix loop uses SessionRunner

**Spec says:** Use the same SessionRunner machinery as regular coding sessions.
**Code does:** No SessionRunner is invoked from the fix loop.
**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** high
**Rationale:** Same root cause as 08-REQ-5.1. The loop structure is a shell without the session execution core.

---

### 09-REQ-9.2: Table output format

**Spec says:** Rich-formatted table for table output mode.
**Code does:** Plain text formatting with Unicode markers. All required information is present.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The plain text format works well and contains all required data. The spec could be updated to say "formatted table" rather than "Rich-formatted table."

---

### 10-REQ-4.1: PR granularity (session level)

**Spec says:** Platform supports session-level PR granularity.
**Code does:** PR granularity is an orchestrator-level concern, not implemented in the platform module. The platform provides building blocks.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The design doc itself notes this is orchestrator logic. The spec should clarify that the platform module provides primitives and the orchestrator implements granularity policy.

---

### 10-REQ-4.2: PR granularity (spec level)

**Spec says:** Platform supports spec-level PR granularity.
**Code does:** Same as 10-REQ-4.1 -- orchestrator concern, not platform.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Same as 10-REQ-4.1.

---

### 12-REQ-1.3: Fact provenance fields

**Spec says:** Fact persistence includes `session_id` and `commit_sha` provenance fields.
**Code does:** `Fact` dataclass lacks `session_id` and `commit_sha`. `_write_to_duckdb()` uses `getattr(fact, "session_id", None)` which always returns `None`.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Cross-cutting issue affecting specs 12 and 13. The `Fact` type needs these fields added and the extraction pipeline needs to populate them.

---

### 13-REQ-1.1: Fact provenance population

**Spec says:** Provenance fields (`spec_name`, `session_id`, `commit_sha`) populated on every fact write.
**Code does:** `spec_name` is populated, but `session_id` and `commit_sha` are always `NULL` during session extraction. Only git ingestion populates `commit_sha`.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Same root cause as 12-REQ-1.3. Linked to missing fields on `Fact` dataclass.

---

### 13-REQ-2.E2: Causal link referential integrity

**Spec says:** Validate that both fact IDs exist in `memory_facts` before inserting a causal link.
**Code does:** `store_causal_links()` uses `INSERT OR IGNORE` directly without checking fact existence. No foreign key constraints.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Dangling references to non-existent facts can silently enter the causal graph, potentially causing traversal issues.

---

### 13-REQ-3.1: add_causal_link function

**Spec says:** `add_causal_link(conn, cause_id, effect_id)` with referential integrity check.
**Code does:** `store_causal_links(conn, links)` -- different function name/signature, takes a list, no referential integrity check.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Batch insertion is more efficient. The spec should be updated to match the batch interface, but the referential integrity check should be added per 13-REQ-2.E2.

---

### 13-REQ-3.2: get_causes public function

**Spec says:** `get_causes(conn, fact_id)` returning `list[CausalFact]`.
**Code does:** `_get_direct_cause_ids()` (private, returns only IDs, not CausalFact objects).
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** No public API for querying direct causes with full metadata. External callers cannot use this functionality.

---

### 13-REQ-3.3: get_effects public function

**Spec says:** `get_effects(conn, fact_id)` returning `list[CausalFact]`.
**Code does:** `_get_direct_effect_ids()` (private, returns only IDs).
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Same as 13-REQ-3.2. No public API for querying direct effects.

---

### 13-REQ-5.1: Pattern detection with fact_causes

**Spec says:** Cross-reference `session_outcomes` with `fact_causes` for causal chain analysis.
**Code does:** Only queries `session_outcomes` for co-occurrences. Does not cross-reference `fact_causes`.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Pattern detection is less precise without causal chain analysis. The feature works but produces correlative rather than causal patterns.

---

### 14-REQ-2.E1: Exception type in model resolution

**Spec says:** Catch `ConfigError` in `_resolve_coding_model_display()`.
**Code does:** Catches `Exception` (broader). Functionally equivalent but structurally different.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Catching the broader exception type is more defensive. Spec should acknowledge this.

---

### 15-REQ-7.1: Token formatting tiers

**Spec says:** Values >= 1000 use `{value/1000:.1f}k`, values < 1000 are plain integers.
**Code does:** Adds an undocumented tier: values >= 1,000,000 formatted as `{value/1_000_000:.1f}M`.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The M-tier is a reasonable enhancement for large token counts. Spec should be updated.

---

### 16-REQ-3.2: Summary blocked task counting

**Spec says:** Summary displays all task status categories.
**Code does:** Merges `blocked` count into `failed` count and uses conditional display (omitting zero-count categories).
**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** low
**Rationale:** Minor presentation difference. Whether blocked tasks should be merged with failed or shown separately is a UX decision.

## Unimplemented Requirements

| Requirement | Spec | Description |
|-------------|------|-------------|
| 13-REQ-4.1 | 13_time_vision | Temporal query function (vector search + causal graph traversal to timeline) |
| 13-REQ-4.2 | 13_time_vision | Temporal query result with causal timeline and synthesized answer |
| 13-REQ-6.1 | 13_time_vision | Timeline dataclass and render method |
| 13-REQ-6.2 | 13_time_vision | Indentation-by-depth timeline rendering |
| 13-REQ-6.3 | 13_time_vision | Plain-text timeline format with TTY-aware color |

**Note:** The entire `agent_fox/knowledge/temporal.py` module is missing. The temporal query and timeline rendering subsystem specified in spec 13 has not been implemented, despite tasks.md showing all tasks as checked. This constitutes genuine drift (not an in-progress gap), since the spec's completion state does not match the codebase.

## Superseded Requirements

No superseded requirements were found. No `## Supersedes` sections exist in any spec's `prd.md`, and no implicit supersession by module overlap was detected.

## In-Progress Caveats

### 17_init_claude_settings (completion: 0%)

| Requirement | Status | Notes |
|-------------|--------|-------|
| 17-REQ-1.1 | Expected gap | Create .claude/settings.local.json -- no implementation exists |
| 17-REQ-1.2 | Expected gap | Create .claude/ directory -- not implemented |
| 17-REQ-1.3 | Expected gap | CANONICAL_PERMISSIONS constant -- not defined |
| 17-REQ-1.E1 | Expected gap | Idempotency logic -- not implemented |
| 17-REQ-2.1 | Expected gap | Merge missing canonical entries -- not implemented |
| 17-REQ-2.2 | Expected gap | Preserve existing entries -- not implemented |
| 17-REQ-2.3 | Expected gap | Ordering preservation -- not implemented |
| 17-REQ-2.E1 | Expected gap | Invalid JSON handling -- not implemented |
| 17-REQ-2.E2 | Expected gap | Missing permissions structure -- not implemented |
| 17-REQ-2.E3 | Expected gap | Non-list allow handling -- not implemented |

### 09_spec_validation (completion: ~90%)

Task group 5 (final checkpoint) is unchecked. All functional implementation groups (1-4) are complete. The only outstanding item is the final verification checkpoint, which is procedural rather than functional.

## Extra Behavior (Best-Effort)

- **`agent_fox/ui/banner.py`**: Banner module is at `agent_fox/ui/` rather than `agent_fox/cli/` as referenced in some spec discussions. The `ui/` package is not specified by any spec but provides theme and banner infrastructure.

- **`agent_fox/reporting/git_activity.py`**: A dedicated module for git commit classification (`is_agent_commit()`, `partition_commits()`) that is not specified by any individual spec. Provides the commit partitioning logic used by the standup report.

- **`agent_fox/cli/code.py` `_NodeSessionRunner`**: A 375+ line session runner implementation that goes well beyond the spec's scope -- includes worktree management, harvesting, hook execution, knowledge store integration, and sink recording, all orchestrated within a single `execute()` method. This consolidates functionality from specs 03, 06, 11, and 12 into a cohesive runtime path.

- **`agent_fox/reporting/standup.py` "Agent Commits" section**: The `StandupReport` model includes `agent_commits: list[HumanCommit]` and the formatter includes an "Agent Commits" section. Neither is specified in any spec's requirements.

- **`format_tokens()` as public function**: The design doc specifies `_format_tokens()` (private). The code exports it as `format_tokens()` (public) because it is imported by `code.py` for the summary display.

## Mitigation Summary

| Requirement | Mitigation | Priority |
|-------------|-----------|----------|
| 01-REQ-1.3 | Change spec | low |
| 01-REQ-2.5 | Change spec | low |
| 03-REQ-3.3 | Get well spec | medium |
| 03-REQ-3.4 / 03-REQ-8.1 / 03-REQ-8.2 | Needs manual review | high |
| 03-REQ-4.1 | Change spec | low |
| 03-REQ-5.1 | Change spec | low |
| 03-REQ-6.1 | Change spec | low |
| 03-REQ-7.2 | Get well spec | low |
| 04-REQ-3.2 | Needs manual review | medium |
| 04-REQ-4.E1 | Change spec | low |
| 04-REQ-6.3 | Change spec | low |
| 04-REQ-9.2 | Get well spec | low |
| 07-REQ-2.2 | Needs manual review | medium |
| 07-REQ-2.3 | Get well spec | medium |
| 07-REQ-2.5 | Get well spec | medium |
| 08-REQ-4.2 | Change spec | low |
| 08-REQ-5.1 | Needs manual review | high |
| 08-REQ-5.2 | Get well spec | medium |
| 08-REQ-5.3 | Needs manual review | high |
| 09-REQ-9.2 | Change spec | low |
| 10-REQ-4.1 | Change spec | low |
| 10-REQ-4.2 | Change spec | low |
| 12-REQ-1.3 | Get well spec | medium |
| 13-REQ-1.1 | Get well spec | medium |
| 13-REQ-2.E2 | Get well spec | medium |
| 13-REQ-3.1 | Change spec | low |
| 13-REQ-3.2 | Get well spec | medium |
| 13-REQ-3.3 | Get well spec | medium |
| 13-REQ-4.1 | Get well spec | high |
| 13-REQ-4.2 | Get well spec | high |
| 13-REQ-5.1 | Get well spec | medium |
| 13-REQ-6.1 | Get well spec | high |
| 13-REQ-6.2 | Get well spec | high |
| 13-REQ-6.3 | Get well spec | high |
| 14-REQ-2.E1 | Change spec | low |
| 15-REQ-7.1 | Change spec | low |
| 16-REQ-3.2 | Needs manual review | low |
