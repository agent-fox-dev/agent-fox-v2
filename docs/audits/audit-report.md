# Spec Audit Report

**Generated:** 2026-03-02
**Branch:** develop
**Specs analyzed:** 13

## Summary

| Category | Count |
|----------|-------|
| Compliant | 335 |
| Drifted | 42 |
| Unimplemented | 0 |
| Superseded | 0 |
| In-progress (expected gaps) | 0 |

## Compliant Requirements

| Requirement | Spec | Description |
|-------------|------|-------------|
| 01-REQ-1.1 | 01_core_foundation | CLI provides `agent-fox` command group with `--version` and `--help` |
| 01-REQ-1.2 | 01_core_foundation | Subcommand registration via `main.add_command()` |
| 01-REQ-1.3 | 01_core_foundation | Banner and help text shown when invoked without subcommand |
| 01-REQ-1.4 | 01_core_foundation | Console script entry point in pyproject.toml |
| 01-REQ-2.1 | 01_core_foundation | Config loads from TOML, validates with pydantic, merges defaults |
| 01-REQ-2.2 | 01_core_foundation | Invalid config fields produce ConfigError with clear messages |
| 01-REQ-2.3 | 01_core_foundation | Missing fields use documented defaults |
| 01-REQ-2.4 | 01_core_foundation | All PRD Section 6 settings exposed via config models |
| 01-REQ-2.6 | 01_core_foundation | Unknown top-level keys logged as warnings, ignored |
| 01-REQ-2.E1 | 01_core_foundation | Missing config file returns defaults without error |
| 01-REQ-2.E3 | 01_core_foundation | Numeric config values clamped via validators |
| 01-REQ-3.1 | 01_core_foundation | Init creates `.agent-fox/` with config.toml and subdirectories |
| 01-REQ-3.2 | 01_core_foundation | Init creates or verifies develop branch |
| 01-REQ-3.3 | 01_core_foundation | Re-init preserves existing config, reports already initialized |
| 01-REQ-3.4 | 01_core_foundation | Init updates .gitignore with correct entries |
| 01-REQ-3.5 | 01_core_foundation | Init outside git repo exits with error and code 1 |
| 01-REQ-3.E1 | 01_core_foundation | Missing config.toml in existing .agent-fox/ triggers creation |
| 01-REQ-3.E2 | 01_core_foundation | Existing develop branch reported without duplication |
| 01-REQ-4.1 | 01_core_foundation | AgentFoxError defined as base exception |
| 01-REQ-4.2 | 01_core_foundation | Required exception subclasses present (SessionTimeoutError naming matches design) |
| 01-REQ-4.3 | 01_core_foundation | Exceptions carry human-readable message and structured context |
| 01-REQ-5.1 | 01_core_foundation | Three model tiers: SIMPLE, STANDARD, ADVANCED |
| 01-REQ-5.2 | 01_core_foundation | ModelEntry includes model_id, tier, pricing |
| 01-REQ-5.3 | 01_core_foundation | resolve_model() handles tier names and direct model IDs |
| 01-REQ-5.4 | 01_core_foundation | calculate_cost() computes cost from token counts |
| 01-REQ-5.E1 | 01_core_foundation | Unknown model ID raises ConfigError with valid options |
| 01-REQ-6.1 | 01_core_foundation | Logging format matches `[LEVEL] component: message` |
| 01-REQ-6.2 | 01_core_foundation | Default WARNING level; --verbose enables DEBUG |
| 01-REQ-6.3 | 01_core_foundation | Named loggers per module |
| 01-REQ-6.E1 | 01_core_foundation | --verbose wins when both --verbose and --quiet are set |
| 01-REQ-7.1 | 01_core_foundation | Theme defines named color roles |
| 01-REQ-7.2 | 01_core_foundation | Theme overrides from ThemeConfig |
| 01-REQ-7.3 | 01_core_foundation | Playful mode uses fox-themed messages |
| 01-REQ-7.4 | 01_core_foundation | Non-playful mode uses professional messages |
| 01-REQ-7.E1 | 01_core_foundation | Invalid Rich styles fall back to defaults with warning |
| 02-REQ-1.1 | 02_planning_engine | Scans .specs/ for NN_name/ directories sorted by prefix |
| 02-REQ-1.2 | 02_planning_engine | --spec restricts discovery to single spec |
| 02-REQ-1.3 | 02_planning_engine | Warning logged for spec folders missing tasks.md |
| 02-REQ-1.E1 | 02_planning_engine | Missing/empty .specs/ raises PlanError |
| 02-REQ-1.E2 | 02_planning_engine | --spec matching nothing raises PlanError with available names |
| 02-REQ-2.1 | 02_planning_engine | Parser extracts task groups matching checkbox patterns |
| 02-REQ-2.2 | 02_planning_engine | Nested subtasks associated with parent groups |
| 02-REQ-2.3 | 02_planning_engine | Optional marker `*` detected and flagged |
| 02-REQ-2.4 | 02_planning_engine | Task group title and body text extracted |
| 02-REQ-2.E1 | 02_planning_engine | No parseable groups returns empty list with warning |
| 02-REQ-2.E2 | 02_planning_engine | Non-contiguous group numbers accepted as-is |
| 02-REQ-3.1 | 02_planning_engine | Intra-spec sequential dependency edges (N depends on N-1) |
| 02-REQ-3.2 | 02_planning_engine | Cross-spec dependency edges from CrossSpecDep |
| 02-REQ-3.3 | 02_planning_engine | Node IDs use `{spec_name}:{group_number}` format |
| 02-REQ-3.4 | 02_planning_engine | All nodes initialized with NodeStatus.PENDING |
| 02-REQ-3.E1 | 02_planning_engine | Dangling cross-spec references raise PlanError |
| 02-REQ-3.E2 | 02_planning_engine | Cycle detection via Kahn's algorithm |
| 02-REQ-4.1 | 02_planning_engine | Topological ordering via Kahn's algorithm |
| 02-REQ-4.2 | 02_planning_engine | Deterministic tie-breaking by spec prefix then group number |
| 02-REQ-4.E1 | 02_planning_engine | Empty graph produces empty ordering |
| 02-REQ-5.1 | 02_planning_engine | Optional nodes removed and set to SKIPPED in fast mode |
| 02-REQ-5.2 | 02_planning_engine | Dependencies rewired around removed optional nodes |
| 02-REQ-5.3 | 02_planning_engine | Fast-mode flag recorded in plan metadata |
| 02-REQ-6.1 | 02_planning_engine | Task graph serialized as JSON to .agent-fox/plan.json |
| 02-REQ-6.2 | 02_planning_engine | Metadata includes timestamp, fast-mode flag, spec filter, version |
| 02-REQ-6.3 | 02_planning_engine | Existing plan loaded when --reanalyze not set |
| 02-REQ-6.4 | 02_planning_engine | --reanalyze discards and rebuilds plan |
| 02-REQ-6.E1 | 02_planning_engine | Corrupted plan.json logged as warning, rebuilt |
| 02-REQ-7.1 | 02_planning_engine | `agent-fox plan` subcommand triggers planning and prints summary |
| 02-REQ-7.2 | 02_planning_engine | --fast flag enables fast-mode filtering |
| 02-REQ-7.3 | 02_planning_engine | --spec NAME restricts to single spec |
| 02-REQ-7.4 | 02_planning_engine | --reanalyze forces fresh plan |
| 02-REQ-7.5 | 02_planning_engine | --verify prints "not yet implemented" |
| 03-REQ-1.1 | 03_session_and_workspace | Worktrees created at correct path from development branch |
| 03-REQ-1.2 | 03_session_and_workspace | Feature branch created and checked out in worktree |
| 03-REQ-1.3 | 03_session_and_workspace | WorkspaceInfo returned with path, branch, spec, group |
| 03-REQ-1.E1 | 03_session_and_workspace | Existing worktree removed and re-created |
| 03-REQ-1.E2 | 03_session_and_workspace | Existing feature branch deleted before fresh creation |
| 03-REQ-1.E3 | 03_session_and_workspace | Worktree creation failure raises WorkspaceError |
| 03-REQ-2.1 | 03_session_and_workspace | destroy_worktree() removes worktree and feature branch |
| 03-REQ-2.2 | 03_session_and_workspace | Empty spec directories cleaned up |
| 03-REQ-2.E1 | 03_session_and_workspace | Non-existent worktree path is a no-op |
| 03-REQ-2.E2 | 03_session_and_workspace | Branch deletion failure logged as warning |
| 03-REQ-3.1 | 03_session_and_workspace | Session runner invokes claude-code-sdk with prompt, model, cwd |
| 03-REQ-3.2 | 03_session_and_workspace | Runner collects ResultMessage for usage metrics |
| 03-REQ-3.3 | 03_session_and_workspace | SessionOutcome contains all required fields |
| 03-REQ-3.E2 | 03_session_and_workspace | is_error=True captured as failed status |
| 03-REQ-4.1 | 03_session_and_workspace | Context assembler reads requirements.md, design.md, tasks.md |
| 03-REQ-4.2 | 03_session_and_workspace | Memory facts included in assembled context |
| 03-REQ-4.3 | 03_session_and_workspace | Context returned as single string with section headers |
| 03-REQ-4.E1 | 03_session_and_workspace | Missing spec documents skipped with warning |
| 03-REQ-5.1 | 03_session_and_workspace | System prompt includes role, context, task group, instructions |
| 03-REQ-5.2 | 03_session_and_workspace | Task prompt identifies group and instructs to commit |
| 03-REQ-6.1 | 03_session_and_workspace | SDK query wrapped with timeout using asyncio.wait_for |
| 03-REQ-6.2 | 03_session_and_workspace | Timeout returns SessionOutcome with status timeout |
| 03-REQ-7.1 | 03_session_and_workspace | Harvester attempts fast-forward merge |
| 03-REQ-7.2 | 03_session_and_workspace | Rebase and retry on fast-forward failure |
| 03-REQ-7.3 | 03_session_and_workspace | Successful merge returns list of changed files |
| 03-REQ-7.E1 | 03_session_and_workspace | Failed rebase is aborted, IntegrationError raised |
| 03-REQ-7.E2 | 03_session_and_workspace | No new commits returns empty file list |
| 03-REQ-9.1 | 03_session_and_workspace | Git module provides all required operations |
| 03-REQ-9.2 | 03_session_and_workspace | Git operations raise appropriate errors wrapping stderr |
| 04-REQ-1.1 | 04_orchestrator | Loads task graph and identifies ready tasks |
| 04-REQ-1.2 | 04_orchestrator | Serial/parallel dispatch based on config |
| 04-REQ-1.3 | 04_orchestrator | After each session: update graph, persist, re-evaluate |
| 04-REQ-1.4 | 04_orchestrator | Stall detection with warning and summary |
| 04-REQ-1.E1 | 04_orchestrator | Missing/corrupted plan raises PlanError |
| 04-REQ-2.1 | 04_orchestrator | Retry failed tasks up to max_retries |
| 04-REQ-2.2 | 04_orchestrator | Previous error passed on retry |
| 04-REQ-2.3 | 04_orchestrator | All retries exhausted: status blocked, final error recorded |
| 04-REQ-2.E1 | 04_orchestrator | max_retries=0 blocks on first failure |
| 04-REQ-3.1 | 04_orchestrator | Cascade-block all transitively dependent tasks |
| 04-REQ-3.E1 | 04_orchestrator | Multiple upstream paths: still blocked if any path is blocked |
| 04-REQ-4.1 | 04_orchestrator | ExecutionState persisted to state.jsonl after every session |
| 04-REQ-4.2 | 04_orchestrator | State includes plan hash, statuses, history, cumulative totals |
| 04-REQ-4.3 | 04_orchestrator | Resume: load state, verify plan hash, continue from ready tasks |
| 04-REQ-4.E2 | 04_orchestrator | Corrupted state: log warning, start fresh |
| 04-REQ-5.1 | 04_orchestrator | Stop launching when cost >= max_cost |
| 04-REQ-5.2 | 04_orchestrator | In-flight allowed to complete on cost limit |
| 04-REQ-5.3 | 04_orchestrator | Stop after max_sessions reached |
| 04-REQ-5.E1 | 04_orchestrator | No preemptive cancellation of in-flight sessions |
| 04-REQ-6.1 | 04_orchestrator | Parallel execution via asyncio with semaphore |
| 04-REQ-6.2 | 04_orchestrator | Max parallelism capped at 8 with warning |
| 04-REQ-6.3 | 04_orchestrator | State writes serialized with asyncio lock |
| 04-REQ-6.E1 | 04_orchestrator | Fewer ready tasks than parallelism: execute available only |
| 04-REQ-7.1 | 04_orchestrator | Pending to in_progress transition at most once per run/retry |
| 04-REQ-7.2 | 04_orchestrator | Completed tasks not re-executed on resume |
| 04-REQ-7.E1 | 04_orchestrator | Interrupted in_progress tasks reset to pending on resume |
| 04-REQ-8.1 | 04_orchestrator | SIGINT saves state to state.jsonl |
| 04-REQ-8.2 | 04_orchestrator | Cancel in-flight parallel tasks and wait |
| 04-REQ-8.3 | 04_orchestrator | Print completion count and resume command |
| 04-REQ-8.E1 | 04_orchestrator | Double SIGINT exits immediately |
| 04-REQ-9.1 | 04_orchestrator | Inter-session delay (default 3s) |
| 04-REQ-9.2 | 04_orchestrator | Delay skipped when no more ready tasks |
| 04-REQ-9.E1 | 04_orchestrator | delay=0 means no pause |
| 04-REQ-10.1 | 04_orchestrator | Success: mark completed, re-evaluate |
| 04-REQ-10.2 | 04_orchestrator | Blocked: cascade-block dependents |
| 05-REQ-1.1 | 05_structured_memory | Transcript sent to SIMPLE model with extraction prompt |
| 05-REQ-1.2 | 05_structured_memory | Extraction requests content, category, confidence, keywords |
| 05-REQ-1.3 | 05_structured_memory | UUID, spec_name, ISO 8601 timestamp assigned |
| 05-REQ-1.E1 | 05_structured_memory | Invalid JSON from model: log warning, skip |
| 05-REQ-1.E2 | 05_structured_memory | Zero facts: log debug, continue |
| 05-REQ-2.1 | 05_structured_memory | Six defined categories |
| 05-REQ-2.2 | 05_structured_memory | Unknown category defaults to gotcha with warning |
| 05-REQ-3.1 | 05_structured_memory | Facts stored in .agent-fox/memory.jsonl, one per line |
| 05-REQ-3.2 | 05_structured_memory | Each fact contains all Fact model fields |
| 05-REQ-3.3 | 05_structured_memory | Append-only, existing lines preserved |
| 05-REQ-3.E1 | 05_structured_memory | File created if it doesn't exist |
| 05-REQ-3.E2 | 05_structured_memory | Write failure: log error, continue |
| 05-REQ-4.1 | 05_structured_memory | Selection by spec_name and keyword overlap |
| 05-REQ-4.2 | 05_structured_memory | Ranking by keyword match count + recency bonus |
| 05-REQ-4.3 | 05_structured_memory | Context budget of 50 facts |
| 05-REQ-4.E1 | 05_structured_memory | No matching facts: return empty list |
| 05-REQ-4.E2 | 05_structured_memory | Missing/empty memory file: return empty list |
| 05-REQ-5.1 | 05_structured_memory | Deduplicate by SHA-256 content hash |
| 05-REQ-5.2 | 05_structured_memory | Resolve supersession chains |
| 05-REQ-5.3 | 05_structured_memory | Rewrite JSONL in place after compaction |
| 05-REQ-5.E1 | 05_structured_memory | Empty/missing memory: no compaction needed |
| 05-REQ-5.E2 | 05_structured_memory | Compaction is idempotent |
| 05-REQ-6.1 | 05_structured_memory | Markdown summary at docs/memory.md by category |
| 05-REQ-6.2 | 05_structured_memory | Each entry includes content, spec name, confidence |
| 05-REQ-6.E1 | 05_structured_memory | Create docs/ if missing |
| 05-REQ-6.E2 | 05_structured_memory | Empty knowledge base: generate "no facts" summary |
| 06-REQ-1.1 | 06_hooks_sync_security | Pre-session hooks executed in order in workspace dir |
| 06-REQ-1.2 | 06_hooks_sync_security | Post-session hooks executed in order after session |
| 06-REQ-1.E1 | 06_hooks_sync_security | No hooks configured: proceed without error |
| 06-REQ-2.1 | 06_hooks_sync_security | Non-zero exit + abort mode: raise HookError |
| 06-REQ-2.2 | 06_hooks_sync_security | Non-zero exit + warn mode: log warning, continue |
| 06-REQ-2.3 | 06_hooks_sync_security | Default mode is abort |
| 06-REQ-2.E1 | 06_hooks_sync_security | Script not found: treat as failure with configured mode |
| 06-REQ-3.1 | 06_hooks_sync_security | Configurable timeout (default 300s) |
| 06-REQ-3.2 | 06_hooks_sync_security | Timeout terminates subprocess, treated as failure |
| 06-REQ-4.1 | 06_hooks_sync_security | Hook env vars: AF_SPEC_NAME, AF_TASK_GROUP, AF_WORKSPACE, AF_BRANCH |
| 06-REQ-4.2 | 06_hooks_sync_security | Sync barrier hooks use __sync_barrier__ spec name |
| 06-REQ-5.1 | 06_hooks_sync_security | --no-hooks skips all hooks |
| 06-REQ-6.E1 | 06_hooks_sync_security | sync_interval=0 disables barriers |
| 06-REQ-7.1 | 06_hooks_sync_security | Hot-load parses new spec tasks and adds nodes |
| 06-REQ-7.2 | 06_hooks_sync_security | Hot-load resolves cross-spec dependencies and adds edges |
| 06-REQ-7.E1 | 06_hooks_sync_security | Non-existent spec dependency: warn and skip |
| 06-REQ-7.E2 | 06_hooks_sync_security | No new specs: continue without modification |
| 06-REQ-8.1 | 06_hooks_sync_security | PreToolUse hook extracts command name (first token, basename) |
| 06-REQ-8.2 | 06_hooks_sync_security | Block command not on allowlist with message |
| 06-REQ-8.3 | 06_hooks_sync_security | Default allowlist contains ~46 standard commands |
| 06-REQ-8.E1 | 06_hooks_sync_security | Empty command: block with descriptive error |
| 06-REQ-8.E2 | 06_hooks_sync_security | Non-Bash tools pass through without inspection |
| 06-REQ-9.1 | 06_hooks_sync_security | bash_allowlist replaces default entirely |
| 06-REQ-9.2 | 06_hooks_sync_security | bash_allowlist_extend adds to defaults |
| 06-REQ-9.E1 | 06_hooks_sync_security | Both set: bash_allowlist wins with warning |
| 07-REQ-1.1 | 07_operational_commands | Status report from state.jsonl and plan.json |
| 07-REQ-1.2 | 07_operational_commands | Token counts and estimated cost in status |
| 07-REQ-1.3 | 07_operational_commands | Problem tasks listed with ID, title, status, reason |
| 07-REQ-1.E1 | 07_operational_commands | No state file: default to all pending |
| 07-REQ-1.E2 | 07_operational_commands | No plan file: error with exit code 1 |
| 07-REQ-2.1 | 07_operational_commands | Standup report with configurable time window |
| 07-REQ-2.4 | 07_operational_commands | Queue summary with ready, pending, blocked, failed counts |
| 07-REQ-2.E1 | 07_operational_commands | No sessions in window: zero counts for agent activity |
| 07-REQ-2.E2 | 07_operational_commands | Git log errors: empty list, no exception |
| 07-REQ-3.1 | 07_operational_commands | --format with table, json, yaml choices |
| 07-REQ-3.2 | 07_operational_commands | JSON output via json.dumps |
| 07-REQ-3.3 | 07_operational_commands | YAML output via yaml.dump |
| 07-REQ-3.4 | 07_operational_commands | --output for file output |
| 07-REQ-3.E1 | 07_operational_commands | File write error raises AgentFoxError |
| 07-REQ-4.1 | 07_operational_commands | Full reset resets failed/blocked/in_progress to pending |
| 07-REQ-4.2 | 07_operational_commands | Reset cleans worktrees and branches |
| 07-REQ-4.3 | 07_operational_commands | Confirmation prompt before full reset |
| 07-REQ-4.4 | 07_operational_commands | --yes skips confirmation |
| 07-REQ-4.E1 | 07_operational_commands | No resettable tasks: report and exit 0 |
| 07-REQ-4.E2 | 07_operational_commands | No execution state: error with exit code 1 |
| 07-REQ-5.1 | 07_operational_commands | Single-task reset to pending with cleanup |
| 07-REQ-5.2 | 07_operational_commands | Cascade-reset sole-blocker dependents |
| 07-REQ-5.3 | 07_operational_commands | Single-task reset has no confirmation prompt |
| 07-REQ-5.E1 | 07_operational_commands | Unknown task ID: error with valid IDs listed |
| 08-REQ-1.1 | 08_error_autofix | detect_checks() inspects pyproject.toml, package.json, Makefile, Cargo.toml |
| 08-REQ-1.2 | 08_error_autofix | All seven detection rules implemented |
| 08-REQ-1.3 | 08_error_autofix | CheckDescriptor with name, command, category |
| 08-REQ-1.E1 | 08_error_autofix | No checks detected: error with exit code 1 |
| 08-REQ-1.E2 | 08_error_autofix | Corrupt config files: log warning, return empty |
| 08-REQ-2.1 | 08_error_autofix | Checks run via subprocess with capture |
| 08-REQ-2.2 | 08_error_autofix | Non-zero exit creates FailureRecord |
| 08-REQ-2.3 | 08_error_autofix | All passing: empty failures list |
| 08-REQ-2.E1 | 08_error_autofix | Timeout: FailureRecord with timeout message |
| 08-REQ-3.1 | 08_error_autofix | AI clustering via Anthropic API |
| 08-REQ-3.2 | 08_error_autofix | FailureCluster with label, failures, suggested_approach |
| 08-REQ-3.3 | 08_error_autofix | AI failure: fallback to per-check grouping |
| 08-REQ-4.1 | 08_error_autofix | Fix spec generation: requirements.md, design.md, tasks.md |
| 08-REQ-4.2 | 08_error_autofix | Output to .agent-fox/fix_specs/pass_N_label/ |
| 08-REQ-6.1 | 08_error_autofix | Fix report with passes, clusters, sessions, termination |
| 08-REQ-6.2 | 08_error_autofix | TerminationReason enum with human-readable labels |
| 08-REQ-7.1 | 08_error_autofix | `agent-fox fix` CLI command |
| 08-REQ-7.2 | 08_error_autofix | --max-passes option with default 3 |
| 08-REQ-7.E1 | 08_error_autofix | max_passes < 1 clamped to 1 with warning |
| 09-REQ-1.1 | 09_spec_validation | lint-spec discovers specs via discover_specs() |
| 09-REQ-1.2 | 09_spec_validation | validate_specs() runs all rules and collects findings |
| 09-REQ-1.3 | 09_spec_validation | Findings sorted by spec, file, severity |
| 09-REQ-1.E1 | 09_spec_validation | No specs: Error finding, exit code 1 |
| 09-REQ-2.1 | 09_spec_validation | Checks for all five expected files |
| 09-REQ-2.2 | 09_spec_validation | Error-severity finding per missing file |
| 09-REQ-3.2 | 09_spec_validation | Warning-severity for oversized groups (>6 subtasks) |
| 09-REQ-4.2 | 09_spec_validation | Warning-severity for missing verification |
| 09-REQ-5.1 | 09_spec_validation | Checks for acceptance criteria patterns in requirements.md |
| 09-REQ-5.2 | 09_spec_validation | Error-severity for missing acceptance criteria |
| 09-REQ-6.1 | 09_spec_validation | Parses dependency table from prd.md |
| 09-REQ-6.2 | 09_spec_validation | Error finding for broken dependency references |
| 09-REQ-6.3 | 09_spec_validation | Validates group number references exist |
| 09-REQ-7.1 | 09_spec_validation | Collects requirement IDs and checks presence in test_spec.md |
| 09-REQ-7.2 | 09_spec_validation | Warning-severity for untraced requirements |
| 09-REQ-8.1 | 09_spec_validation | AI validation via Anthropic API with --ai flag |
| 09-REQ-8.2 | 09_spec_validation | AI detects vague/unmeasurable criteria (Hint) |
| 09-REQ-8.3 | 09_spec_validation | AI detects implementation-leaking criteria (Hint) |
| 09-REQ-8.E1 | 09_spec_validation | AI failure: log warning, return empty findings |
| 09-REQ-9.1 | 09_spec_validation | --format with table, json, yaml |
| 09-REQ-9.2 | 09_spec_validation | Table output grouped by spec with columns |
| 09-REQ-9.3 | 09_spec_validation | JSON and YAML serialization |
| 09-REQ-9.4 | 09_spec_validation | Exit code 1 if any Error-severity findings |
| 09-REQ-9.5 | 09_spec_validation | Exit code 0 when no Error-severity findings |
| 10-REQ-1.1 | 10_platform_integration | Platform defined as typing.Protocol with four async methods |
| 10-REQ-1.2 | 10_platform_integration | create_pr signature matches spec |
| 10-REQ-1.3 | 10_platform_integration | wait_for_ci signature matches spec |
| 10-REQ-1.4 | 10_platform_integration | wait_for_review signature matches spec |
| 10-REQ-1.5 | 10_platform_integration | merge_pr signature matches spec |
| 10-REQ-2.1 | 10_platform_integration | NullPlatform satisfies Platform protocol |
| 10-REQ-2.2 | 10_platform_integration | NullPlatform.create_pr does direct merge |
| 10-REQ-2.3 | 10_platform_integration | NullPlatform.wait_for_ci returns True immediately |
| 10-REQ-2.4 | 10_platform_integration | NullPlatform.wait_for_review returns True immediately |
| 10-REQ-2.5 | 10_platform_integration | NullPlatform.merge_pr is a no-op |
| 10-REQ-3.1 | 10_platform_integration | GitHubPlatform satisfies Platform protocol |
| 10-REQ-3.2 | 10_platform_integration | create_pr uses `gh pr create` with proper flags |
| 10-REQ-3.3 | 10_platform_integration | wait_for_ci polls `gh pr checks` with interval |
| 10-REQ-3.4 | 10_platform_integration | wait_for_review polls `gh pr view` for review decision |
| 10-REQ-3.5 | 10_platform_integration | merge_pr uses `gh pr merge --merge` |
| 10-REQ-3.E1 | 10_platform_integration | Verifies gh CLI installation and auth |
| 10-REQ-3.E2 | 10_platform_integration | gh pr create failure raises IntegrationError |
| 10-REQ-3.E3 | 10_platform_integration | Non-success CI checks return False |
| 10-REQ-3.E4 | 10_platform_integration | CI timeout returns False |
| 10-REQ-3.E5 | 10_platform_integration | CHANGES_REQUESTED returns False |
| 10-REQ-3.E6 | 10_platform_integration | gh pr merge failure raises IntegrationError |
| 10-REQ-5.1 | 10_platform_integration | create_platform factory function defined |
| 10-REQ-5.2 | 10_platform_integration | type=none returns NullPlatform |
| 10-REQ-5.E1 | 10_platform_integration | Unrecognized type raises ConfigError |
| 11-REQ-1.1 | 11_duckdb_knowledge_store | KnowledgeDB.open() creates DuckDB at config.store_path |
| 11-REQ-1.2 | 11_duckdb_knowledge_store | VSS extension loaded (with install fallback) |
| 11-REQ-1.3 | 11_duckdb_knowledge_store | close() releases file locks |
| 11-REQ-1.E1 | 11_duckdb_knowledge_store | Parent directory created if missing |
| 11-REQ-1.E2 | 11_duckdb_knowledge_store | Open errors wrapped as KnowledgeStoreError |
| 11-REQ-2.1 | 11_duckdb_knowledge_store | All seven tables created with IF NOT EXISTS |
| 11-REQ-2.2 | 11_duckdb_knowledge_store | Initial version 1 recorded in schema_version |
| 11-REQ-2.3 | 11_duckdb_knowledge_store | memory_embeddings uses configurable FLOAT dimensions |
| 11-REQ-3.1 | 11_duckdb_knowledge_store | apply_pending_migrations applies versions > current |
| 11-REQ-3.2 | 11_duckdb_knowledge_store | Migration as frozen dataclass with apply callable |
| 11-REQ-3.3 | 11_duckdb_knowledge_store | Version recorded after each migration |
| 11-REQ-3.E1 | 11_duckdb_knowledge_store | Migration failure wrapped as KnowledgeStoreError |
| 11-REQ-4.1 | 11_duckdb_knowledge_store | SessionSink as runtime_checkable Protocol |
| 11-REQ-4.2 | 11_duckdb_knowledge_store | SinkDispatcher as single dispatch point |
| 11-REQ-4.3 | 11_duckdb_knowledge_store | Per-sink failures caught without stopping dispatch |
| 11-REQ-5.1 | 11_duckdb_knowledge_store | DuckDBSink implements all SessionSink methods |
| 11-REQ-5.2 | 11_duckdb_knowledge_store | record_session_outcome always writes |
| 11-REQ-5.3 | 11_duckdb_knowledge_store | tool_calls/errors only written in debug mode |
| 11-REQ-5.4 | 11_duckdb_knowledge_store | Non-debug: tool recording is no-op |
| 11-REQ-5.E1 | 11_duckdb_knowledge_store | Write failures logged as warnings |
| 11-REQ-6.1 | 11_duckdb_knowledge_store | JsonlSink implements all SessionSink methods |
| 11-REQ-6.2 | 11_duckdb_knowledge_store | All events written as JSON lines |
| 11-REQ-7.1 | 11_duckdb_knowledge_store | open_knowledge_store returns None on failure |
| 11-REQ-7.2 | 11_duckdb_knowledge_store | Mid-run DuckDB write failures don't block execution |
| 12-REQ-1.1 | 12_fox_ball | Dual-write: JSONL then DuckDB then embedding |
| 12-REQ-1.2 | 12_fox_ball | JSONL always written first (source of truth) |
| 12-REQ-1.E1 | 12_fox_ball | DuckDB failure: warning logged, JSONL still written |
| 12-REQ-2.1 | 12_fox_ball | Embedding generation via Anthropic embeddings API |
| 12-REQ-2.2 | 12_fox_ball | Batch embedding via single API call |
| 12-REQ-2.E1 | 12_fox_ball | Embedding failure: return None, continue |
| 12-REQ-2.E2 | 12_fox_ball | Oracle ask with no embedding: raise KnowledgeStoreError |
| 12-REQ-3.1 | 12_fox_ball | Vector search via cosine similarity |
| 12-REQ-3.2 | 12_fox_ball | Top-k results with SearchResult including provenance |
| 12-REQ-3.3 | 12_fox_ball | Facts without embeddings excluded from results |
| 12-REQ-3.E1 | 12_fox_ball | No embeddings: empty result set |
| 12-REQ-4.1 | 12_fox_ball | ADR ingestion from docs/adr/ |
| 12-REQ-4.2 | 12_fox_ball | Git commit ingestion via git log |
| 12-REQ-4.3 | 12_fox_ball | Ingested sources get embeddings |
| 12-REQ-5.1 | 12_fox_ball | Oracle.ask() RAG pipeline: embed, search, synthesize |
| 12-REQ-5.2 | 12_fox_ball | Sources with provenance included in response |
| 12-REQ-5.3 | 12_fox_ball | Synthesis via configured model (STANDARD) |
| 12-REQ-5.E1 | 12_fox_ball | No knowledge: informational message |
| 12-REQ-5.E2 | 12_fox_ball | Knowledge store unavailable: error with exit code 1 |
| 12-REQ-6.1 | 12_fox_ball | Contradiction detection via CONTRADICTION markers |
| 12-REQ-7.1 | 12_fox_ball | mark_superseded updates superseded_by column |
| 12-REQ-7.2 | 12_fox_ball | Superseded facts excluded from search by default |
| 12-REQ-8.1 | 12_fox_ball | Confidence indicator: high/medium/low based on similarity |
| 13-REQ-1.2 | 13_time_vision | NULL values stored for missing provenance |
| 13-REQ-2.E2 | 13_time_vision | Non-existent fact references: skip with warning |
| 13-REQ-3.1 | 13_time_vision | add_causal_link enforces referential integrity |
| 13-REQ-3.2 | 13_time_vision | get_causes queries direct causes |
| 13-REQ-3.3 | 13_time_vision | get_effects queries direct effects |
| 13-REQ-3.4 | 13_time_vision | traverse_causal_chain BFS with depth bound (default 10) |
| 13-REQ-3.E1 | 13_time_vision | Duplicate causal links silently ignored |
| 13-REQ-5.2 | 13_time_vision | Pattern includes all five fields with correct thresholds |
| 13-REQ-5.3 | 13_time_vision | `agent-fox patterns` CLI command registered |
| 13-REQ-5.E1 | 13_time_vision | No patterns: informational message, exit 0 |
| 13-REQ-6.1 | 13_time_vision | Timeline renders content, timestamp, spec, session, commit, relationship |
| 13-REQ-6.2 | 13_time_vision | Indentation proportional to causal depth |
| 13-REQ-6.3 | 13_time_vision | No ANSI codes emitted (plain text) |
| 13-REQ-7.2 | 13_time_vision | Causal facts additive within 50-fact budget (at function level) |

## Drifted Requirements

### 01-REQ-1.E1: Unknown subcommand error listing

**Spec says:** "IF the CLI is invoked with an unknown subcommand, THEN THE CLI SHALL print an error listing available commands and exit with code 2."
**Code does:** Uses standard `click.Group` rather than custom `BannerGroup` from design.md. Click's default says "No such command 'foo'" but does not list available commands. Exit code 2 is correct.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Default Click behavior is industry standard. The spec's custom BannerGroup is an enhancement the code reasonably omitted. Users can run `--help` to see commands.

---

### 01-REQ-2.5: CLI-to-config override mechanism

**Spec says:** "WHERE a command-line option overrides a configuration value, THE system SHALL prefer the command-line value."
**Code does:** No CLI-to-config override mechanism exists. The `--verbose`/`--quiet` flags affect logging but are not config overrides. No general mechanism for CLI flags to override TOML config values.
**Drift type:** missing-edge-case
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The current CLI design does not expose config values as CLI flags beyond logging level. This appears to be an intentional simplification rather than an omission.

---

### 01-REQ-2.E2: Config file not loaded via CLI

**Spec says:** "IF the configuration file is not valid TOML, THEN THE system SHALL exit with a clear parse error and exit code 1."
**Code does:** `load_config()` in app.py is called without a path argument, so the CLI never actually reads `.agent-fox/config.toml`. Config is always default values when invoked via CLI.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** The CLI never reads the config file, meaning all user customization in `.agent-fox/config.toml` is silently ignored at runtime. This is a functional regression -- the config system is fully implemented but the CLI entry point doesn't use it.

---

### 01-REQ-4.E1: Top-level exception handler

**Spec says:** "IF an unexpected exception reaches the CLI top level, THEN THE CLI SHALL catch it, log the traceback at DEBUG, print a user-friendly message, and exit with code 1."
**Code does:** The `main()` function only catches `AgentFoxError` during config loading. Non-AgentFoxError exceptions from subcommands produce raw Python tracebacks.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Raw tracebacks are poor UX. A top-level catch-all would improve the user experience for unexpected errors.

---

### 03-REQ-3.4: Security allowlist hook not wired

**Spec says:** "THE session runner SHALL set `permission_mode` to `bypassPermissions` and register a PreToolUse hook that enforces the configured command allowlist."
**Code does:** `permission_mode` is set correctly. `build_allowlist_hook()` is fully implemented but is NOT passed to `ClaudeCodeOptions` in `_execute_query()`. The hook is defined but never registered.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** The security allowlist is a critical safety feature. The hook logic is correct but not wired in, meaning the coding agent can execute any shell command without restriction.

---

### 03-REQ-3.E1: Exception handling specificity

**Spec says:** "IF the claude-code-sdk raises a ClaudeSDKError, THEN wrap in SessionError and return failed outcome."
**Code does:** Catches generic `Exception` rather than `ClaudeSDKError`. Does not wrap in `SessionError` -- sets failed status directly on outcome.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Catching broadly is arguably more robust. The outcome is functionally correct (failed status with error message). The missing `SessionError` wrapping is a minor type-safety gap.

---

### 03-REQ-6.E1: Partial metrics on timeout

**Spec says:** "WHEN a timeout occurs, THE system SHALL preserve partial metrics from messages received before the timeout."
**Code does:** When timeout fires, the query coroutine is cancelled entirely and its local variables (tokens, duration) are discarded. The SessionOutcome always shows 0 tokens and 0 duration on timeout.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Losing partial metrics on timeout means cost tracking underreports when sessions time out. This affects billing accuracy.

---

### 03-REQ-8.1: Security hook not registered

**Spec says:** "THE session runner SHALL register a PreToolUse hook that intercepts Bash tool invocations."
**Code does:** `build_allowlist_hook()` is implemented but never registered with the SDK query call.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** Same root cause as 03-REQ-3.4. The allowlist hook exists but is not wired into the execution path.

---

### 03-REQ-8.2: Command blocking not active

**Spec says:** "IF the command is not on the effective allowlist, THEN THE hook SHALL block the tool invocation."
**Code does:** Blocking logic is correct inside the hook function, but since the hook is never registered, commands are never actually blocked.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** See 03-REQ-8.1. The code is correct but inactive.

---

### 03-REQ-8.E1: Empty command blocking not active

**Spec says:** "IF the command string is empty or cannot be parsed, THEN THE hook SHALL block the invocation."
**Code does:** Hook correctly blocks empty commands, but is never registered.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** See 03-REQ-8.1. The code is correct but inactive.

---

### 04-REQ-1.E2: Empty plan message

**Spec says:** "THE orchestrator SHALL print a message indicating there is nothing to execute and exit successfully."
**Code does:** Returns a state with `RunStatus.COMPLETED` but does not print/log a user-visible message about the empty plan.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** low
**Rationale:** Minor UX gap. The orchestrator correctly exits but silently.

---

### 04-REQ-3.2: Cascade-block reason not persisted

**Spec says:** "THE orchestrator SHALL record the blocking reason on each cascade-blocked task, identifying the upstream task."
**Code does:** The blocking reason is only logged, not persisted. `ExecutionState.node_states` stores only the status string with no field for per-node reasons.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Without persisted blocking reasons, it's hard to diagnose why a cascade-blocked task is stuck when reviewing state.jsonl.

---

### 04-REQ-4.E1: Plan hash mismatch auto-starts fresh

**Spec says:** "THE orchestrator SHALL warn the user and offer to start fresh or abort."
**Code does:** Logs a warning and automatically starts fresh without offering the user a choice.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** In an automated context, offering a choice would require interactive prompting, which complicates the orchestration loop. Auto-starting fresh after a plan change is a reasonable default.

---

### 04-REQ-10.E1: Stalled exit code

**Spec says:** "Report stalled, exit non-zero."
**Code does:** Returns state with `RunStatus.STALLED` but doesn't set exit code directly. Exit code responsibility falls to the CLI layer.
**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** low
**Rationale:** The exit code may be handled at the CLI layer. Need to verify whether the CLI translates `STALLED` to non-zero exit.

---

### 05-REQ-6.3: Memory summary not regenerated at sync barriers

**Spec says:** "THE system SHALL regenerate the summary at sync barriers and on demand."
**Code does:** `render_summary()` exists and works correctly, but the orchestrator loop does not call it at sync barriers. The integration between the orchestrator and the render function is missing.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Part of the larger sync barrier integration gap. The function works but the wiring is missing.

---

### 06-REQ-6.1: Sync barriers not wired into orchestrator

**Spec says:** "WHEN the session count reaches a configurable interval (default: every 5), THE orchestrator SHALL pause execution."
**Code does:** `should_trigger_barrier()` in hot_load.py correctly implements the trigger condition, but the orchestrator's `run()` method never calls it. The barrier logic exists but is disconnected.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** All sync barrier building blocks exist but none are called from the orchestrator loop. This is a systematic integration gap.

---

### 06-REQ-6.2: Knowledge summary not triggered at barriers

**Spec says:** "THE orchestrator SHALL regenerate the knowledge summary."
**Code does:** `render_summary()` exists but is not called from the orchestrator at sync barriers.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Same root cause as 06-REQ-6.1 -- sync barrier integration missing.

---

### 06-REQ-6.3: Hot-loading not triggered at barriers

**Spec says:** "THE orchestrator SHALL hot-load new specifications when enabled."
**Code does:** `hot_load_specs()` is fully implemented but is not called from the orchestrator loop.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Same root cause as 06-REQ-6.1 -- sync barrier integration missing.

---

### 06-REQ-7.3: Hot-load does not persist updated plan

**Spec says:** "THE system SHALL re-compute topological ordering and persist the updated plan."
**Code does:** Calls `resolve_order()` to re-compute ordering but does not write the updated plan to `plan.json`. Returns the graph without persisting.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Hot-loaded specs would be lost on restart if the updated plan isn't persisted.

---

### 07-REQ-2.2: Git log filtering method

**Spec says:** Use `git log --invert-grep --author=<agent_author>` to exclude agent commits.
**Code does:** Fetches all commits and filters in Python: `[c for c in all_commits if c.author != agent_author]`.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The Python-side filtering is functionally equivalent and arguably more maintainable. The result is identical.

---

### 07-REQ-2.3: File overlap detection non-functional

**Spec says:** Standup report should detect file overlap between agent and human changes.
**Code does:** `_collect_agent_files()` returns an empty dict because `SessionRecord` lacks a `touched_paths` field. File overlap detection always finds zero overlaps.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** The `SessionRecord` data model is missing the `touched_paths` field needed for this feature. This is a data model gap.

---

### 07-REQ-2.5: Cost breakdown by model tier non-functional

**Spec says:** Standup report should break down costs by model tier.
**Code does:** All sessions grouped under a single "default" tier because `SessionRecord` lacks a `model` field.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** The `SessionRecord` data model is missing the `model` field. Requires adding the field and populating it during session recording.

---

### 07-REQ-5.E2: Completed task reset warning

**Spec says:** "Print a warning that completed tasks cannot be reset and exit successfully."
**Code does:** Uses `logger.warning()` (goes to log) rather than user-visible output. CLI displays a generic "Nothing to reset" message.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** low
**Rationale:** The warning message should be user-facing rather than log-only to explain why the reset was a no-op.

---

### 08-REQ-5.1: Fix loop does not execute coding sessions

**Spec says:** "The fix loop SHALL run one coding session per failure cluster per pass."
**Code does:** The loop correctly runs checks, clusters, and generates specs, but does NOT invoke the SessionRunner. A comment states: "Session runner integration is handled at the CLI level; the loop structure supports it but sessions are not executed inline."
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** Without session execution, the fix loop generates specs but cannot actually fix errors. This is the core value proposition of the feature.

---

### 08-REQ-5.2: Cost limit termination missing

**Spec says:** "Loop terminates when cost limit is reached."
**Code does:** The `COST_LIMIT` termination reason exists in the enum but is never checked. No cost tracking or comparison against a ceiling in the loop.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Without cost tracking, the fix loop could run unbounded (limited only by max_passes). When sessions are added, cost limits will be needed.

---

### 08-REQ-5.3: SessionRunner machinery not used

**Spec says:** "Fix sessions SHALL use the same SessionRunner machinery as regular coding sessions."
**Code does:** SessionRunner is not imported or invoked in the fix loop.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** Closely related to 08-REQ-5.1. The fix loop is incomplete without session execution.

---

### 09-REQ-3.1: Task group size check counting

**Spec says:** "Count subtasks excluding verification steps (N.V)."
**Code does:** The upstream parser regex (`\d+\.\d+`) only matches digit.digit patterns, never `N.V`. Verification steps are never parsed into subtasks, so the exclusion logic is dead code. The count is correct by accident.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** low
**Rationale:** The count happens to be correct because unparsed verification steps are naturally excluded. However, the parser should be fixed to handle `N.V` patterns for correctness.

---

### 09-REQ-4.1: Verification step check always fires

**Spec says:** "Check that each task group contains a verification step (N.V)."
**Code does:** The parser regex `\d+\.\d+` cannot match `N.V` patterns, so verification steps are never in `group.subtasks`. The check ALWAYS reports missing verification, producing 100% false positives.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** The parser regex needs to be extended to match `\d+\.V\d*` patterns. Currently every spec produces false "missing verification" warnings.

---

### 10-REQ-4.1: PR granularity "session" not enforced

**Spec says:** "WHEN pr_granularity is session, create one PR per task group session."
**Code does:** The `pr_granularity` config field exists in `PlatformConfig` but no code reads or enforces it. The behavior is determined by the orchestrator, not the platform module.
**Drift type:** structural
**Suggested mitigation:** Needs manual review
**Priority:** medium
**Rationale:** The enforcement may be in the orchestrator layer. Need to verify whether the orchestrator implements this logic.

---

### 10-REQ-4.2: PR granularity "spec" not enforced

**Spec says:** "WHEN pr_granularity is spec, batch task groups into a single PR per spec."
**Code does:** Same as 10-REQ-4.1 -- `pr_granularity` config exists but no enforcement logic in the platform module.
**Drift type:** structural
**Suggested mitigation:** Needs manual review
**Priority:** medium
**Rationale:** Same as 10-REQ-4.1 -- may be handled at the orchestrator level.

---

### 10-REQ-5.3: Factory does not pass all config to GitHubPlatform

**Spec says:** "The factory SHALL pass CI timeout, labels, auto-merge, and wait flags."
**Code does:** Factory passes `ci_timeout` and `auto_merge` but does NOT pass `labels` or `wait_for_ci`/`wait_for_review` flags. `GitHubPlatform.__init__` doesn't accept them.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Labels are passed at `create_pr` call time by the orchestrator. Wait flags control whether the orchestrator calls `wait_for_ci`/`wait_for_review` at all. The factory should wire these through for consistency.

---

### 11-REQ-6.3: JSONL sink debug gating

**Spec says:** "THE JSONL sink SHALL only be attached when debug mode is enabled."
**Code does:** The `JsonlSink` class writes all events unconditionally. Debug-gating is an attachment-time policy handled by the orchestrator, not internal to the sink.
**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** low
**Rationale:** The attachment policy is an orchestrator concern. Need to verify whether the orchestrator only adds the JSONL sink in debug mode.

---

### 11-REQ-7.3: Graceful degradation fallback policy

**Spec says:** "Session outcomes SHALL fall back to JSONL-only recording when DuckDB is unavailable."
**Code does:** `open_knowledge_store()` returns `None` on failure, but the fallback attachment logic (JSONL-only when DuckDB unavailable) is not implemented in the knowledge module.
**Drift type:** missing-edge-case
**Suggested mitigation:** Needs manual review
**Priority:** low
**Rationale:** This is an orchestrator-level policy. The knowledge module correctly returns None, but the fallback wiring needs to be verified at the integration layer.

---

### 12-REQ-1.3: Fact provenance fields missing from data model

**Spec says:** "Populate id, content, category, spec_name, session_id, commit_sha, confidence, created_at in memory_facts."
**Code does:** The `Fact` dataclass lacks `session_id` and `commit_sha` fields. `_write_to_duckdb()` uses `getattr(fact, "session_id", None)` and `getattr(fact, "commit_sha", None)` as fallbacks, which always yield `None` for session-extracted facts.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** The Fact data model from spec 05 predates the provenance requirements from spec 12. The model needs `session_id` and `commit_sha` fields added.

---

### 13-REQ-1.1: Fact provenance fields not populated

**Spec says:** "THE system SHALL populate spec_name, session_id, and commit_sha."
**Code does:** `spec_name` is populated. `session_id` and `commit_sha` are always NULL because the `Fact` dataclass lacks those fields.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Same root cause as 12-REQ-1.3. The Fact data model needs to be extended.

---

### 13-REQ-2.1: Causal extraction not wired into pipeline

**Spec says:** "THE system SHALL include instructions for the extraction model to identify cause-effect relationships."
**Code does:** `enrich_extraction_with_causal()` and `CAUSAL_EXTRACTION_ADDENDUM` exist but are never called from `extract_facts()` or any production code path.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** The causal extraction enrichment is a key feature of Time Vision but the integration is missing. The function exists but isn't called.

---

### 13-REQ-2.2: Causal link storage not wired

**Spec says:** "THE system SHALL store causal relationships in fact_causes."
**Code does:** `parse_causal_links()` and `add_causal_link()` both exist but no production code connects them -- the pipeline from extraction to storage is not wired.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** Same integration gap as 13-REQ-2.1. Individual functions work but the pipeline connecting them is absent.

---

### 13-REQ-2.E1: Causal extraction edge case not exercised

**Spec says:** "IF the extraction model fails to identify any causal links, THEN facts are stored without causal metadata."
**Code does:** `parse_causal_links()` handles empty responses correctly, but since the pipeline is never invoked in production, the edge case is never exercised.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Edge case handling is correct at the function level but untestable in production due to missing integration.

---

### 13-REQ-4.1: Temporal query not wired into ask command

**Spec says:** "WHEN a temporal query is submitted via ask, THE system SHALL use vector search + causal graph traversal."
**Code does:** `temporal_query()` exists and correctly implements the pipeline, but the `ask` CLI command uses only the Oracle RAG pipeline and does not invoke `temporal_query()`.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** The temporal query feature is fully implemented but not accessible via the CLI. The `ask` command should detect temporal queries and route them through `temporal_query()`.

---

### 13-REQ-4.2: Temporal query lacks synthesis step

**Spec says:** "THE temporal query result SHALL include a causal timeline and a synthesized natural-language answer."
**Code does:** `temporal_query()` returns a `Timeline` object but does not pass it to a synthesis model. No synthesis step exists in the temporal pipeline.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** The timeline is constructed correctly but lacks the natural-language synthesis that would make it user-friendly.

---

### 13-REQ-5.1: Pattern detection query diverges from design

**Spec says:** "THE system SHALL analyze co-occurrences in fact_causes and session_outcomes."
**Code does:** `detect_patterns()` queries ONLY `session_outcomes`. No cross-reference with `fact_causes`. The query also uses `failed.touched_path` instead of the design-specified `failed.spec_name`.
**Drift type:** structural
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** The pattern detection is functional but less powerful than specified. The `fact_causes` cross-reference would enable richer pattern detection.

---

### 13-REQ-7.1: Causal context enhancement not wired

**Spec says:** "BEFORE each session, THE system SHALL query the causal graph for facts linked to the current spec and touched files."
**Code does:** `select_context_with_causal()` exists and correctly implements causal graph traversal, but is never called from session startup code. The `touched_files` parameter is accepted but unused.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** This is a key quality-of-context improvement that would help coding sessions leverage causal knowledge. The function exists but integration is missing.

---

## Unimplemented Requirements

| Requirement | Spec | Description |
|-------------|------|-------------|
| _(none)_ | | All requirements have at least partial implementations |

## Superseded Requirements

| Requirement | Original Spec | Superseded By | Type |
|-------------|--------------|---------------|------|
| _(none)_ | | | No supersessions declared across any specs |

## In-Progress Caveats

### 09_spec_validation (completion: 96%)

| Requirement | Status | Notes |
|-------------|--------|-------|
| _(no affected requirements)_ | N/A | The single unchecked item is the final checkpoint task "Specification Validation Complete" -- a verification task, not a requirement. All spec 09 requirements have been classified above. |

## Extra Behavior (Best-Effort)

- **`agent_fox/cli/init.py`**: The `init` command implementation is extensive (176 lines) with gitignore template management that exceeds what the spec describes, but is consistent with the init requirements.
- **`agent_fox/memory/store.py` -- `MemoryStore` class**: A DuckDB-aware memory store class was added to bridge specs 05 and 12. This is not explicitly spec'd as a standalone component but serves as the integration layer between JSONL memory and DuckDB knowledge store.
- **`agent_fox/knowledge/oracle.py` -- Oracle RAG pipeline**: While specified in spec 12, the Oracle implements additional synthesis prompt engineering (citation instructions, contradiction detection prompts) beyond what the design doc details.
- **`agent_fox/cli/app.py` -- CLI structure**: All nine subcommands are registered (init, plan, ask, fix, lint-spec, patterns, reset, standup, status). No unspecified commands detected.

## Mitigation Summary

| Requirement | Mitigation | Priority |
|-------------|-----------|----------|
| 01-REQ-1.E1 | Change spec | low |
| 01-REQ-2.5 | Change spec | low |
| 01-REQ-2.E2 | Get well spec | high |
| 01-REQ-4.E1 | Get well spec | medium |
| 03-REQ-3.4 | Get well spec | high |
| 03-REQ-3.E1 | Change spec | low |
| 03-REQ-6.E1 | Get well spec | medium |
| 03-REQ-8.1 | Get well spec | high |
| 03-REQ-8.2 | Get well spec | high |
| 03-REQ-8.E1 | Get well spec | high |
| 04-REQ-1.E2 | Get well spec | low |
| 04-REQ-3.2 | Get well spec | medium |
| 04-REQ-4.E1 | Change spec | low |
| 04-REQ-10.E1 | Needs manual review | low |
| 05-REQ-6.3 | Get well spec | medium |
| 06-REQ-6.1 | Get well spec | medium |
| 06-REQ-6.2 | Get well spec | medium |
| 06-REQ-6.3 | Get well spec | medium |
| 06-REQ-7.3 | Get well spec | medium |
| 07-REQ-2.2 | Change spec | low |
| 07-REQ-2.3 | Get well spec | medium |
| 07-REQ-2.5 | Get well spec | medium |
| 07-REQ-5.E2 | Get well spec | low |
| 08-REQ-5.1 | Get well spec | high |
| 08-REQ-5.2 | Get well spec | medium |
| 08-REQ-5.3 | Get well spec | high |
| 09-REQ-3.1 | Get well spec | low |
| 09-REQ-4.1 | Get well spec | medium |
| 10-REQ-4.1 | Needs manual review | medium |
| 10-REQ-4.2 | Needs manual review | medium |
| 10-REQ-5.3 | Get well spec | medium |
| 11-REQ-6.3 | Needs manual review | low |
| 11-REQ-7.3 | Needs manual review | low |
| 12-REQ-1.3 | Get well spec | medium |
| 13-REQ-1.1 | Get well spec | medium |
| 13-REQ-2.1 | Get well spec | high |
| 13-REQ-2.2 | Get well spec | high |
| 13-REQ-2.E1 | Get well spec | medium |
| 13-REQ-4.1 | Get well spec | high |
| 13-REQ-4.2 | Get well spec | medium |
| 13-REQ-5.1 | Get well spec | medium |
| 13-REQ-7.1 | Get well spec | high |
