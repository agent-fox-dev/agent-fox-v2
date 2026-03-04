# Spec Audit Report

**Generated:** 2026-03-04
**Branch:** develop
**Specs analyzed:** 18 (17 numbered specs + 1 duplicate-numbered; 1 skipped for missing design.md)

## Summary

| Category | Count |
|----------|-------|
| Compliant | 433 |
| Drifted | 17 |
| Unimplemented | 0 |
| Superseded | 0 |
| In-progress (expected gaps) | 0 |

**Overall compliance: 96.2% (433/450)**

### Warnings

- **Spec 16_code_command:** Missing `design.md` and `prd.md`. Requirements audited against code but interface comparison skipped.
- **Spec 15 ID collision:** Both `15_session_prompt` and `15_standup_formatting` use the `15-REQ-*` prefix, creating requirement ID ambiguity. Each is reported separately below.
- **Spec 17_init_claude_settings:** `tasks.md` shows 0% completion (all unchecked) but implementation is fully present in code.
- **fix_01_ruff_format:** Skipped — does not match `NN_snake_case` naming pattern.
- **fix_02_unnarrrowed_content_block_union:** Skipped — does not match `NN_snake_case` naming pattern (also note typo: triple-r in "unnarrrowed").
- **test_spec, prd.md, v2.md:** Skipped — files/directories not matching spec folder pattern.

## Per-Spec Breakdown

| Spec | Total Reqs | Compliant | Drifted | Tasks % |
|------|-----------|-----------|---------|---------|
| 01_core_foundation | 38 | 38 | 0 | 100% |
| 02_planning_engine | 33 | 32 | 1 | 100% |
| 03_session_and_workspace | 35 | 33 | 2 | 100% |
| 04_orchestrator | 40 | 37 | 3 | 100% |
| 05_structured_memory | 27 | 26 | 1 | 100% |
| 06_hooks_sync_security | 29 | 29 | 0 | 100% |
| 07_operational_commands | 27 | 25 | 2 | 100% |
| 08_error_autofix | 21 | 21 | 0 | 100% |
| 09_spec_validation | 25 | 25 | 0 | 97% |
| 10_platform_integration | 27 | 27 | 0 | 100% |
| 11_duckdb_knowledge_store | 26 | 26 | 0 | 100% |
| 12_fox_ball | 24 | 24 | 0 | 100% |
| 13_time_vision | 19 | 14 | 5 | 100% |
| 14_cli_banner | 12 | 12 | 0 | 100% |
| 15_session_prompt | 17 | 17 | 0 | 100% |
| 15_standup_formatting | 21 | 20 | 1 | 100% |
| 16_code_command* | 19 | 17 | 2 | 100% |
| 17_init_claude_settings | 10 | 10 | 0 | 0%** |
| **Total** | **450** | **433** | **17** | |

\* Missing design.md — interface comparison skipped.
\*\* tasks.md not updated but implementation is complete.

## Compliant Requirements

All 433 compliant requirements are listed per-spec below (condensed).

<details>
<summary>01_core_foundation (38/38 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 01-REQ-1.1 | CLI top-level command with --version and --help |
| 01-REQ-1.2 | Subcommand registration |
| 01-REQ-1.3 | Themed banner on every invocation |
| 01-REQ-1.4 | Console script entry point |
| 01-REQ-1.E1 | Unknown subcommand exits with code 2 |
| 01-REQ-2.1 | Load config.toml, validate with pydantic, merge defaults |
| 01-REQ-2.2 | Clear error for invalid fields |
| 01-REQ-2.3 | Default values for absent fields |
| 01-REQ-2.4 | Expose all PRD Section 6 settings |
| 01-REQ-2.5 | CLI overrides preferred over config |
| 01-REQ-2.6 | Unknown keys logged and ignored |
| 01-REQ-2.E1 | Missing config file uses defaults |
| 01-REQ-2.E2 | Invalid TOML exits with code 1 |
| 01-REQ-2.E3 | Out-of-range numerics clamped |
| 01-REQ-3.1 | Init creates .agent-fox/ with config.toml, hooks/, worktrees/ |
| 01-REQ-3.2 | Init creates/verifies develop branch |
| 01-REQ-3.3 | Already-initialized preserves config |
| 01-REQ-3.4 | .gitignore updated with .agent-fox entries |
| 01-REQ-3.5 | Exit with error if not in git repo |
| 01-REQ-3.E1 | .agent-fox/ exists but config missing creates config |
| 01-REQ-3.E2 | Existing develop branch not duplicated |
| 01-REQ-4.1 | Base AgentFoxError exception |
| 01-REQ-4.2 | Specific exception classes |
| 01-REQ-4.3 | Human-readable message + structured context |
| 01-REQ-4.E1 | Unhandled exceptions caught at CLI top level |
| 01-REQ-5.1 | Three model tiers |
| 01-REQ-5.2 | Model entry with ID, tier, pricing |
| 01-REQ-5.3 | Lookup function resolves tier or model ID |
| 01-REQ-5.4 | Cost calculation function |
| 01-REQ-5.E1 | Unknown model raises ConfigError |
| 01-REQ-6.1 | Logging format [LEVEL] component: message |
| 01-REQ-6.2 | Default WARNING, --verbose switches to DEBUG |
| 01-REQ-6.3 | Named loggers per module |
| 01-REQ-6.E1 | --verbose wins over --quiet |
| 01-REQ-7.1 | Theme with named color roles |
| 01-REQ-7.2 | Theme overrides from [theme] config |
| 01-REQ-7.3 | Playful fox-themed messages when enabled |
| 01-REQ-7.4 | Neutral messages when playful disabled |
| 01-REQ-7.E1 | Invalid Rich style falls back to default |

</details>

<details>
<summary>02_planning_engine (32/33 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 02-REQ-1.1 | Scan .specs/ for NN_name/ dirs, sorted by prefix |
| 02-REQ-1.2 | --spec restricts to single spec |
| 02-REQ-1.3 | Skip spec without tasks.md with warning |
| 02-REQ-1.E1 | No .specs/ raises PlanError |
| 02-REQ-1.E2 | --spec mismatch raises PlanError with available names |
| 02-REQ-2.1 | Parse top-level task groups |
| 02-REQ-2.2 | Extract nested subtasks |
| 02-REQ-2.3 | Detect optional marker * |
| 02-REQ-2.4 | Extract title and body text |
| 02-REQ-2.E1 | Empty tasks.md returns empty list with warning |
| 02-REQ-2.E2 | Non-contiguous group numbers accepted |
| 02-REQ-3.1 | Sequential intra-spec edges |
| 02-REQ-3.2 | Cross-spec edges from prd.md dependency table |
| 02-REQ-3.3 | Node ID format {spec_name}:{group_number} |
| 02-REQ-3.4 | All nodes initialized PENDING |
| 02-REQ-3.E1 | Dangling cross-spec reference raises PlanError |
| 02-REQ-3.E2 | Cycle detection raises PlanError |
| 02-REQ-4.1 | Topological ordering with correct edge direction |
| 02-REQ-4.2 | Deterministic tie-breaking by spec prefix then group number |
| 02-REQ-5.1 | Fast mode removes optional nodes, sets SKIPPED |
| 02-REQ-5.2 | Rewire dependencies around optional nodes |
| 02-REQ-5.3 | Fast mode flag in plan metadata |
| 02-REQ-6.1 | Serialize graph as JSON to plan.json |
| 02-REQ-6.2 | Metadata includes timestamp, fast mode, filtered spec, version |
| 02-REQ-6.3 | Load existing plan when --reanalyze not set |
| 02-REQ-6.4 | --reanalyze discards existing plan |
| 02-REQ-6.E1 | Corrupted plan.json logged and rebuilt |
| 02-REQ-7.1 | agent-fox plan subcommand |
| 02-REQ-7.2 | --fast flag |
| 02-REQ-7.3 | --spec NAME option |
| 02-REQ-7.4 | --reanalyze option |
| 02-REQ-7.5 | --verify placeholder |

</details>

<details>
<summary>03_session_and_workspace (33/35 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 03-REQ-1.1 | Create worktree at .agent-fox/worktrees/{spec}/{group} |
| 03-REQ-1.2 | Feature branch named feature/{spec}/{group} |
| 03-REQ-1.3 | Return WorkspaceInfo |
| 03-REQ-1.E1 | Stale worktree removed and re-created |
| 03-REQ-1.E2 | Existing feature branch deleted |
| 03-REQ-1.E3 | Git error raises WorkspaceError |
| 03-REQ-2.1 | Destroy removes worktree and branch |
| 03-REQ-2.2 | Empty spec directory removed |
| 03-REQ-2.E1 | Missing worktree is no-op |
| 03-REQ-2.E2 | Branch deletion failure logs warning |
| 03-REQ-3.1 | Session runner invokes query() with prompt, system prompt, cwd, model |
| 03-REQ-3.2 | Iterate messages, collect ResultMessage |
| 03-REQ-3.4 | bypassPermissions + PreToolUse allowlist hook |
| 03-REQ-3.E2 | is_error flag sets status to failed |
| 03-REQ-4.1 | Read spec documents |
| 03-REQ-4.2 | Accept memory facts list |
| 03-REQ-4.3 | Return formatted string with section headers |
| 03-REQ-4.E1 | Missing spec file skipped with warning |
| 03-REQ-5.1 | System prompt from templates with placeholders |
| 03-REQ-5.2 | Task prompt identifies group, references tasks.md |
| 03-REQ-6.1 | Wrap query in asyncio.wait_for with session_timeout |
| 03-REQ-6.2 | Timeout returns SessionOutcome with status timeout |
| 03-REQ-6.E1 | Partial metrics preserved on timeout |
| 03-REQ-7.1 | Fast-forward merge of feature branch |
| 03-REQ-7.2 | Rebase and retry on conflict |
| 03-REQ-7.3 | Return list of changed files |
| 03-REQ-7.E1 | Rebase failure aborts and raises IntegrationError |
| 03-REQ-7.E2 | No new commits returns empty list |
| 03-REQ-8.1 | PreToolUse hook extracts command name |
| 03-REQ-8.2 | Block command not on allowlist |
| 03-REQ-8.E1 | Empty command blocked |
| 03-REQ-9.1 | Git module provides branch/merge/rebase functions |
| 03-REQ-9.2 | Git errors raise WorkspaceError or IntegrationError |

</details>

<details>
<summary>04_orchestrator (37/40 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 04-REQ-1.1 | Load task graph, identify ready tasks |
| 04-REQ-1.2 | Execute ready tasks serial or parallel |
| 04-REQ-1.3 | After each session: update graph, persist state, re-evaluate |
| 04-REQ-1.4 | Warn when stalled |
| 04-REQ-1.E1 | Missing/corrupted plan raises PlanError |
| 04-REQ-1.E2 | Empty plan prints message and exits |
| 04-REQ-2.1 | Retry failed sessions up to max_retries |
| 04-REQ-2.2 | Pass previous error message on retry |
| 04-REQ-2.3 | All retries exhausted sets status to blocked |
| 04-REQ-2.E1 | max_retries=0 blocks on first failure |
| 04-REQ-3.1 | Cascade-block transitively dependent tasks |
| 04-REQ-3.E1 | Task blocked if any upstream path is blocked |
| 04-REQ-4.1 | Persist ExecutionState to state.jsonl after every session |
| 04-REQ-4.2 | State includes plan hash, statuses, history, totals |
| 04-REQ-4.3 | Load state, verify plan hash, continue from ready tasks |
| 04-REQ-4.E2 | Corrupted state file discarded with warning |
| 04-REQ-5.1 | Cost limit stops new sessions |
| 04-REQ-5.2 | In-flight sessions complete before reporting |
| 04-REQ-5.3 | Session limit stops new sessions |
| 04-REQ-5.E1 | Single session exceeding budget not cancelled |
| 04-REQ-6.1 | Parallel execution up to configured parallelism |
| 04-REQ-6.2 | Max parallelism capped at 8 with warning |
| 04-REQ-6.E1 | Fewer ready tasks than parallelism executes available only |
| 04-REQ-7.1 | Task transitions pending->in_progress at most once per attempt |
| 04-REQ-7.2 | Resume skips completed tasks |
| 04-REQ-7.E1 | Interrupted in_progress treated as failed on resume |
| 04-REQ-8.1 | SIGINT saves state |
| 04-REQ-8.2 | Cancel in-flight parallel tasks |
| 04-REQ-8.3 | Print resume instructions |
| 04-REQ-8.E1 | Double SIGINT exits immediately |
| 04-REQ-9.1 | Inter-session delay (default 3s) |
| 04-REQ-9.2 | Skip delay when no more ready tasks |
| 04-REQ-9.E1 | Delay 0 means no pause |
| 04-REQ-10.1 | Success marks completed, re-evaluates ready |
| 04-REQ-10.2 | Blocked propagates cascade blocks |
| 04-REQ-10.E1 | All remaining blocked reports stalled, non-zero exit |

</details>

<details>
<summary>05_structured_memory (26/27 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 05-REQ-1.1 | Send transcript to extraction model with structured JSON prompt |
| 05-REQ-1.2 | Extraction prompt requests content, category, confidence, keywords |
| 05-REQ-1.3 | Assign UUID, spec name, ISO timestamp |
| 05-REQ-1.E1 | Invalid JSON from model logged and skipped |
| 05-REQ-1.E2 | Zero facts logs debug and continues |
| 05-REQ-2.1 | Six fact categories defined |
| 05-REQ-2.2 | Unknown category defaults to gotcha with warning |
| 05-REQ-3.1 | Store facts in .agent-fox/memory.jsonl |
| 05-REQ-3.3 | Append without modifying existing lines |
| 05-REQ-3.E1 | Create file if it doesn't exist |
| 05-REQ-3.E2 | Write failure logged without raising |
| 05-REQ-4.1 | Select facts by spec_name match and keyword overlap |
| 05-REQ-4.2 | Rank by keyword match count + recency bonus |
| 05-REQ-4.3 | Return at most 50 facts |
| 05-REQ-4.E1 | No matching facts returns empty list |
| 05-REQ-4.E2 | Missing/empty memory file returns empty list |
| 05-REQ-5.1 | Dedup by content hash (SHA-256), keep earliest |
| 05-REQ-5.2 | Resolve supersession chains |
| 05-REQ-5.3 | Rewrite JSONL in place after compaction |
| 05-REQ-5.E1 | Empty memory reports no compaction needed |
| 05-REQ-5.E2 | Idempotent compaction |
| 05-REQ-6.1 | Generate docs/memory.md organized by category |
| 05-REQ-6.2 | Each entry includes content, spec name, confidence |
| 05-REQ-6.3 | Regenerate at sync barriers and on demand |
| 05-REQ-6.E1 | Create docs/ directory if missing |
| 05-REQ-6.E2 | Empty knowledge base generates placeholder message |

</details>

<details>
<summary>06_hooks_sync_security (29/29 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 06-REQ-1.1 | Pre-session hooks executed in order before session |
| 06-REQ-1.2 | Post-session hooks executed in order after session |
| 06-REQ-1.E1 | No hooks configured proceeds without error |
| 06-REQ-2.1 | Non-zero exit + abort mode raises HookError |
| 06-REQ-2.2 | Non-zero exit + warn mode logs warning and continues |
| 06-REQ-2.3 | Default to abort mode |
| 06-REQ-2.E1 | Missing/non-executable script treated as failure |
| 06-REQ-3.1 | Configurable timeout (default 300s) |
| 06-REQ-3.2 | Timeout treated as hook failure with configured mode |
| 06-REQ-4.1 | AF_SPEC_NAME, AF_TASK_GROUP, AF_WORKSPACE, AF_BRANCH env vars |
| 06-REQ-4.2 | Sync barrier context: __sync_barrier__ and barrier number |
| 06-REQ-5.1 | --no-hooks bypasses all hooks |
| 06-REQ-6.1 | Sync barriers at configurable intervals |
| 06-REQ-6.2 | Regenerate memory summary at sync barrier |
| 06-REQ-6.3 | Scan for new specs at sync barrier (hot-loading) |
| 06-REQ-6.E1 | sync_interval=0 disables barriers |
| 06-REQ-7.1 | Parse new spec task definitions |
| 06-REQ-7.2 | Resolve cross-spec dependencies for new specs |
| 06-REQ-7.3 | Re-compute topological ordering |
| 06-REQ-7.E1 | Non-existent dependency logs warning, skips spec |
| 06-REQ-7.E2 | No new specs returns unchanged graph |
| 06-REQ-8.1 | PreToolUse hook extracts command name (basename) |
| 06-REQ-8.2 | Block command not on allowlist |
| 06-REQ-8.3 | Default allowlist of ~35 standard commands |
| 06-REQ-8.E1 | Empty command blocked |
| 06-REQ-8.E2 | Non-Bash tools pass through |
| 06-REQ-9.1 | bash_allowlist replaces default entirely |
| 06-REQ-9.2 | bash_allowlist_extend adds to defaults |
| 06-REQ-9.E1 | Both set: bash_allowlist precedence, warn |

</details>

<details>
<summary>07_operational_commands (25/27 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 07-REQ-1.1 | generate_status() reads state.jsonl and plan.json, computes task counts |
| 07-REQ-1.2 | StatusReport includes token counts and estimated cost |
| 07-REQ-1.3 | Problem tasks list for failed/blocked tasks with reasons |
| 07-REQ-1.E1 | Missing state shows all pending with zero cost |
| 07-REQ-1.E2 | Missing plan raises AgentFoxError |
| 07-REQ-2.1 | generate_standup() accepts hours parameter, filters sessions |
| 07-REQ-2.2 | partition_commits() filters human commits |
| 07-REQ-2.4 | Queue summary computes ready, pending, blocked counts |
| 07-REQ-2.E1 | Empty windowed sessions produce zero agent activity |
| 07-REQ-2.E2 | partition_commits() handles git failure gracefully |
| 07-REQ-3.1 | --format option with table/json/yaml choices |
| 07-REQ-3.2 | JSON output implemented |
| 07-REQ-3.3 | YAML output implemented |
| 07-REQ-3.4 | --output option writes to file |
| 07-REQ-3.E1 | Handles unwritable paths |
| 07-REQ-4.1 | reset_all() finds resettable tasks |
| 07-REQ-4.2 | Clean worktree dirs and feature branches |
| 07-REQ-4.3 | Shows tasks to reset, calls confirm() |
| 07-REQ-4.4 | --yes flag bypasses confirmation |
| 07-REQ-4.E1 | Nothing to reset returns empty list |
| 07-REQ-4.E2 | Missing state raises AgentFoxError |
| 07-REQ-5.1 | reset_task() resets single task by ID |
| 07-REQ-5.2 | Cascade-unblockable tasks identified |
| 07-REQ-5.3 | Single-task reset has no confirmation prompt |
| 07-REQ-5.E1 | Unknown task raises AgentFoxError |
| 07-REQ-5.E2 | Completed task skipped with notice |

</details>

<details>
<summary>08_error_autofix (21/21 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 08-REQ-1.1 | detect_checks() inspects pyproject.toml, package.json, etc. |
| 08-REQ-1.2 | Detects pytest, ruff, mypy, npm test/lint, etc. |
| 08-REQ-1.3 | CheckDescriptor dataclass with name, command, category |
| 08-REQ-1.E1 | Exit code 1 when no checks detected |
| 08-REQ-1.E2 | Config parse error handled gracefully |
| 08-REQ-2.1 | run_checks() executes each check with capture_output |
| 08-REQ-2.2 | FailureRecord dataclass |
| 08-REQ-2.3 | Returns empty failure list when all pass |
| 08-REQ-2.E1 | 5-minute timeout per check |
| 08-REQ-3.1 | AI clustering of failures |
| 08-REQ-3.2 | FailureCluster dataclass |
| 08-REQ-3.3 | Fallback clustering by check name |
| 08-REQ-4.1 | generate_fix_spec() writes requirements/design/tasks |
| 08-REQ-4.2 | Writes to pass_N_label/ directories |
| 08-REQ-5.1 | run_fix_loop() iterates: checks, cluster, specs, sessions |
| 08-REQ-5.2 | Terminates on ALL_FIXED, MAX_PASSES, COST_LIMIT, INTERRUPTED |
| 08-REQ-5.3 | Uses run_session() from session runner |
| 08-REQ-6.1 | render_fix_report() displays passes, clusters, sessions, reason |
| 08-REQ-6.2 | TerminationReason StrEnum |
| 08-REQ-7.1 | fix_cmd registered as Click command |
| 08-REQ-7.2 | --max-passes option with default 3 |
| 08-REQ-7.E1 | max_passes clamped to >=1 |

</details>

<details>
<summary>09_spec_validation (25/25 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 09-REQ-1.1 | lint_spec command discovers specs |
| 09-REQ-1.2 | validate_specs() runs all rules |
| 09-REQ-1.3 | sort_findings() sorts by spec, file, severity |
| 09-REQ-1.E1 | Handles missing .specs/ |
| 09-REQ-2.1 | check_missing_files() for 5 expected files |
| 09-REQ-2.2 | Error-severity findings for missing files |
| 09-REQ-3.1 | check_oversized_groups() counts subtasks |
| 09-REQ-3.2 | Warning when count > 6 |
| 09-REQ-4.1 | check_missing_verification() for N.V pattern |
| 09-REQ-4.2 | Warning when missing |
| 09-REQ-5.1 | check_missing_acceptance_criteria() parses requirement headings |
| 09-REQ-5.2 | Error finding for sections without criteria |
| 09-REQ-6.1 | check_broken_dependencies() parses dependency table |
| 09-REQ-6.2 | Error for references to non-existent specs |
| 09-REQ-6.3 | Error for references to non-existent groups |
| 09-REQ-7.1 | check_untraced_requirements() collects IDs |
| 09-REQ-7.2 | Warning for IDs not in test_spec |
| 09-REQ-8.1 | AI validation of acceptance criteria |
| 09-REQ-8.2 | Detects vague or unmeasurable criteria |
| 09-REQ-8.3 | Detects implementation-leaking criteria |
| 09-REQ-8.E1 | AI failure handled gracefully |
| 09-REQ-9.1 | Three output formats: table, json, yaml |
| 09-REQ-9.2 | Table format groups by spec |
| 09-REQ-9.3 | JSON and YAML serialization |
| 09-REQ-9.4 | Exit code 1 if error-severity findings |
| 09-REQ-9.5 | Exit code 0 for warnings-only |

</details>

<details>
<summary>10_platform_integration (27/27 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 10-REQ-1.1 | Platform protocol with four async methods |
| 10-REQ-1.2 | create_pr(branch, title, body, labels) -> str |
| 10-REQ-1.3 | wait_for_ci(pr_url, timeout) -> bool |
| 10-REQ-1.4 | wait_for_review(pr_url) -> bool |
| 10-REQ-1.5 | merge_pr(pr_url) -> None |
| 10-REQ-2.1 | NullPlatform when type is "none" |
| 10-REQ-2.2 | NullPlatform.create_pr() merges via git |
| 10-REQ-2.3 | wait_for_ci returns True immediately |
| 10-REQ-2.4 | wait_for_review returns True immediately |
| 10-REQ-2.5 | merge_pr is no-op |
| 10-REQ-3.1 | GitHubPlatform when type is "github" |
| 10-REQ-3.2 | create_pr runs gh pr create |
| 10-REQ-3.3 | wait_for_ci polls at 30-second intervals |
| 10-REQ-3.4 | wait_for_review polls reviewDecision |
| 10-REQ-3.5 | merge_pr executes gh pr merge |
| 10-REQ-3.E1 | Verifies gh CLI availability |
| 10-REQ-3.E2 | Raises IntegrationError on PR creation failure |
| 10-REQ-3.E3 | Returns False on failed CI check |
| 10-REQ-3.E4 | Returns False on CI timeout |
| 10-REQ-3.E5 | Returns False on CHANGES_REQUESTED |
| 10-REQ-3.E6 | Raises IntegrationError on merge failure |
| 10-REQ-4.1 | Platform provides primitives |
| 10-REQ-4.2 | No granularity logic in platform |
| 10-REQ-5.1 | create_platform(config) factory function |
| 10-REQ-5.2 | Returns NullPlatform for type "none" |
| 10-REQ-5.3 | Returns GitHubPlatform for type "github" |
| 10-REQ-5.E1 | Raises ConfigError for unrecognized type |

</details>

<details>
<summary>11_duckdb_knowledge_store (26/26 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 11-REQ-1.1 | KnowledgeDB.open() creates DuckDB file |
| 11-REQ-1.2 | VSS extension install/load |
| 11-REQ-1.3 | close() releases locks |
| 11-REQ-1.E1 | Parent dir creation |
| 11-REQ-1.E2 | Database open failure raises KnowledgeStoreError |
| 11-REQ-2.1 | Schema initialization with 7 tables |
| 11-REQ-2.2 | Records version 1 |
| 11-REQ-2.3 | Configurable embedding dimensions |
| 11-REQ-3.1 | apply_pending_migrations() |
| 11-REQ-3.2 | Migration dataclass |
| 11-REQ-3.3 | record_version() |
| 11-REQ-3.E1 | Migration failure wraps in KnowledgeStoreError |
| 11-REQ-4.1 | SessionSink protocol |
| 11-REQ-4.2 | Session runner calls sink methods polymorphically |
| 11-REQ-4.3 | SinkDispatcher dispatches to multiple sinks |
| 11-REQ-5.1 | DuckDBSink implements SessionSink |
| 11-REQ-5.2 | record_session_outcome always writes |
| 11-REQ-5.3 | Tool calls gated on debug flag |
| 11-REQ-5.4 | Returns immediately when not debug |
| 11-REQ-5.E1 | All write methods swallow exceptions |
| 11-REQ-6.1 | JsonlSink implements SessionSink |
| 11-REQ-6.2 | Writes JSON lines to timestamped file |
| 11-REQ-6.3 | JSONL sink attachment is orchestrator-level |
| 11-REQ-7.1 | open_knowledge_store() returns None on failure |
| 11-REQ-7.2 | DuckDB sink swallows write failures |
| 11-REQ-7.3 | SinkDispatcher handles None store gracefully |

</details>

<details>
<summary>12_fox_ball (24/24 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 12-REQ-1.1 | MemoryStore.write_fact() writes to JSONL then DuckDB |
| 12-REQ-1.2 | JSONL always written; DuckDB best-effort |
| 12-REQ-1.3 | DuckDB write populates all fields |
| 12-REQ-1.E1 | DuckDB failure caught; JSONL already succeeded |
| 12-REQ-2.1 | EmbeddingGenerator.embed_text() generates vectors |
| 12-REQ-2.2 | embed_batch() sends multiple texts in single API call |
| 12-REQ-2.E1 | Embedding failure returns None |
| 12-REQ-2.E2 | Query embedding failure raises KnowledgeStoreError |
| 12-REQ-3.1 | VectorSearch uses cosine distance |
| 12-REQ-3.2 | Returns top-k with content, provenance, similarity |
| 12-REQ-3.3 | INNER JOIN excludes unembedded facts |
| 12-REQ-3.E1 | Returns empty list when no embedded facts |
| 12-REQ-4.1 | ingest_adrs() parses ADR markdown |
| 12-REQ-4.2 | ingest_git_commits() creates facts with commit_sha |
| 12-REQ-4.3 | Both ingestion methods store and embed |
| 12-REQ-5.1 | ask_command embeds question, retrieves, synthesizes |
| 12-REQ-5.2 | Oracle answer includes source provenance |
| 12-REQ-5.3 | Single model call (not streaming) |
| 12-REQ-5.E1 | Empty embeddings check before query |
| 12-REQ-5.E2 | Missing knowledge store exits with code 1 |
| 12-REQ-6.1 | Synthesis prompt flags contradictions |
| 12-REQ-7.1 | MemoryStore.mark_superseded() |
| 12-REQ-7.2 | VectorSearch excludes superseded facts by default |
| 12-REQ-8.1 | Confidence determination from result count and similarity |

</details>

<details>
<summary>13_time_vision (14/19 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 13-REQ-1.1 | Fact provenance fields populated during extraction |
| 13-REQ-1.2 | Null provenance fields accepted without rejection |
| 13-REQ-2.1 | CAUSAL_EXTRACTION_ADDENDUM constant and enrichment function |
| 13-REQ-2.2 | parse_causal_links() and store_causal_links() |
| 13-REQ-2.E1 | Parse failure returns empty list |
| 13-REQ-2.E2 | Validates both fact IDs exist before insertion |
| 13-REQ-3.4 | traverse_causal_chain() with BFS, configurable depth and direction |
| 13-REQ-3.E1 | INSERT OR IGNORE for idempotent insertion |
| 13-REQ-4.1 | temporal_query() uses vector search + causal traversal |
| 13-REQ-5.2 | Pattern dataclass with all required fields |
| 13-REQ-5.3 | patterns_cmd registered as CLI command |
| 13-REQ-5.E1 | Empty patterns message |
| 13-REQ-7.1 | select_context_with_causal() queries causal graph |
| 13-REQ-7.2 | Result trimmed to max_facts |

</details>

<details>
<summary>14_cli_banner (12/12 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 14-REQ-1.1 | FOX_ART constant matches canonical art |
| 14-REQ-1.2 | Fox art printed with style="header" |
| 14-REQ-1.E1 | Falls back to existing theme system |
| 14-REQ-2.1 | Version line format with version and model |
| 14-REQ-2.2 | _resolve_coding_model_display() resolves model |
| 14-REQ-2.3 | Version/model line printed with style="header" |
| 14-REQ-2.E1 | Unresolvable model falls back to raw config value |
| 14-REQ-3.1 | Working directory displayed |
| 14-REQ-3.2 | Working directory printed with style="muted" |
| 14-REQ-3.E1 | OSError caught, displays "(unknown)" |
| 14-REQ-4.1 | render_banner() called unconditionally before subcommands |
| 14-REQ-4.2 | Quiet mode suppresses banner |
| 14-REQ-4.E1 | --version exits before main() body |

</details>

<details>
<summary>15_session_prompt (17/17 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 15-REQ-1.1 | _SPEC_FILES includes test_spec.md |
| 15-REQ-1.2 | test_spec.md after design.md, before tasks.md |
| 15-REQ-1.E1 | Missing files skipped with warning |
| 15-REQ-2.1 | Templates from _templates/prompts/ |
| 15-REQ-2.2 | Coding role uses coding.md + git-flow.md |
| 15-REQ-2.3 | Coordinator role uses coordinator.md |
| 15-REQ-2.4 | build_system_prompt() accepts role parameter |
| 15-REQ-2.5 | Context appended to composed prompt |
| 15-REQ-2.E1 | Missing template raises ConfigError |
| 15-REQ-2.E2 | Invalid role raises ValueError |
| 15-REQ-3.1 | Interpolates {spec_name} and {task_group} |
| 15-REQ-3.2 | Unrecognized placeholders left unchanged |
| 15-REQ-3.E1 | Literal braces preserved |
| 15-REQ-4.1 | _strip_frontmatter() removes YAML frontmatter |
| 15-REQ-4.2 | No frontmatter returns content unchanged |
| 15-REQ-5.1 | build_task_prompt() includes spec_name and task_group |
| 15-REQ-5.2 | Includes checkbox update and commit instructions |
| 15-REQ-5.3 | Includes quality gate reminder |
| 15-REQ-5.E1 | Raises ValueError when task_group < 1 |

</details>

<details>
<summary>15_standup_formatting (20/21 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 15-REQ-1.1 | Header uses em dash (U+2014) |
| 15-REQ-1.2 | Generated timestamp line |
| 15-REQ-1.3 | Blank line after header |
| 15-REQ-1.E1 | Handles singular hour formatting |
| 15-REQ-2.1 | "Agent Activity" section header |
| 15-REQ-2.2 | Per-task line format with all fields |
| 15-REQ-2.3 | TaskActivity dataclass with all fields |
| 15-REQ-2.E1 | Empty activity message |
| 15-REQ-3.1 | "Human Commits" section format |
| 15-REQ-3.E1 | Empty commits message |
| 15-REQ-4.1 | "Queue Status" section with counts |
| 15-REQ-4.2 | Ready task IDs displayed |
| 15-REQ-4.3 | QueueSummary dataclass |
| 15-REQ-4.E1 | Ready line conditional on presence |
| 15-REQ-5.1 | "Heads Up -- File Overlaps" section |
| 15-REQ-5.E1 | Overlaps section omitted when empty |
| 15-REQ-6.1 | Total cost line format |
| 15-REQ-6.2 | total_cost field in StandupReport |
| 15-REQ-6.E1 | Default cost is 0.0 |
| 15-REQ-8.1 | _display_node_id() replaces colons with slashes |
| 15-REQ-8.2 | All task IDs use display format |

</details>

<details>
<summary>16_code_command (17/19 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 16-REQ-1.1 | Click command registered as "code" |
| 16-REQ-1.2 | Config loaded from ctx.obj |
| 16-REQ-1.3 | Orchestrator constructed with config, plan, state paths |
| 16-REQ-1.4 | asyncio.run(orchestrator.run()) |
| 16-REQ-1.E1 | Missing plan file exits with code 1 |
| 16-REQ-1.E2 | Exception caught, friendly error, exits 1 |
| 16-REQ-2.1 | --parallel option |
| 16-REQ-2.2 | --no-hooks flag |
| 16-REQ-2.3 | --max-cost option |
| 16-REQ-2.4 | --max-sessions option |
| 16-REQ-2.5 | _apply_overrides() applies CLI options without modifying persisted config |
| 16-REQ-2.E1 | Clamping handled by Pydantic validator |
| 16-REQ-3.E1 | Empty plan prints "No tasks to execute" |
| 16-REQ-4.1 | Exit code 0 for completed |
| 16-REQ-4.2 | Exit code 1 for errors |
| 16-REQ-4.3 | Exit code 2 for stalled |
| 16-REQ-4.4 | Exit code 3 for cost/session limit |
| 16-REQ-4.5 | Exit code 130 for interrupted |
| 16-REQ-4.E1 | Default exit code 1 for unknown status |
| 16-REQ-5.1 | session_runner_factory() creates NodeSessionRunner |
| 16-REQ-5.2 | Factory injected into Orchestrator |
| 16-REQ-5.E1 | Runner construction failures handled by orchestrator retry |

</details>

<details>
<summary>17_init_claude_settings (10/10 compliant)</summary>

| Requirement | Description |
|-------------|-------------|
| 17-REQ-1.1 | _ensure_claude_settings() creates file when absent |
| 17-REQ-1.2 | .claude/ directory created with parents |
| 17-REQ-1.3 | CANONICAL_PERMISSIONS constant |
| 17-REQ-1.E1 | Returns without modifying when all entries present |
| 17-REQ-2.1 | Missing canonical entries appended |
| 17-REQ-2.2 | Existing entries never removed |
| 17-REQ-2.3 | Existing entries maintain order |
| 17-REQ-2.E1 | Invalid JSON caught, warning logged, file untouched |
| 17-REQ-2.E2 | Missing permissions/allow keys created |
| 17-REQ-2.E3 | Non-list allow detected, warning logged, file untouched |

</details>

## Drifted Requirements

### 02-REQ-4.E1: Empty graph warning

**Spec says:** "IF the graph is empty (no task groups found), THEN THE system SHALL produce an empty ordering and warn the user."
**Code does:** `resolver.py` returns empty list for empty graph but does NOT log a warning to the user.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** low
**Rationale:** The empty ordering is produced correctly, only the warning message is missing. Add `logger.warning()` before the `return []`.

---

### 03-REQ-3.3: SessionOutcome missing files_touched

**Spec says:** "THE session runner SHALL return a SessionOutcome containing: spec name, task group, node ID, status, files touched, input tokens, output tokens, duration in milliseconds, and any error message."
**Code does:** `SessionOutcome` (in `knowledge/sink.py`) includes all listed fields EXCEPT `files_touched`. File tracking happens at the harvester layer, not the session layer.
**Drift type:** structural
**Suggested mitigation:** Needs manual review
**Priority:** medium
**Rationale:** The `files_touched` data is available post-harvest but not in the session outcome. Either add the field and populate it from the harvester, or update the spec to clarify that file tracking is a harvest-time concern.

---

### 03-REQ-3.E1: Generic exception catch instead of ClaudeSDKError

**Spec says:** "IF the claude-code-sdk raises a ClaudeSDKError or any of its subclasses, THEN THE session runner SHALL catch it, wrap it in a SessionError, and return a SessionOutcome with status failed."
**Code does:** `runner.py` catches generic `Exception`, sets status to "failed" and stores the error message. Does NOT specifically catch `ClaudeSDKError` or wrap in `SessionError`.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The broad catch is functionally equivalent and more resilient. The code correctly handles the failure case; the only difference is error type specificity.

---

### 04-REQ-3.2: Blocking reasons not persisted

**Spec says:** "THE orchestrator SHALL record the blocking reason on each cascade-blocked task, identifying the upstream task that caused the block."
**Code does:** Blocking reasons are logged via `logger.info()` but NOT stored in `ExecutionState` or any persistent structure. The `node_states` dict only stores the string "blocked".
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** low
**Rationale:** The information is logged but not persisted. Add a `blocked_reasons: dict[str, str]` field to `ExecutionState` for full traceability.

---

### 04-REQ-4.E1: Plan hash mismatch handling implicit

**Spec says:** "IF the state file exists but the plan hash does not match, THEN THE orchestrator SHALL log a warning and start fresh automatically (discarding the stale state)."
**Code does:** Warning is logged correctly. The stale state is effectively discarded since a new `ExecutionState` is created, but the code path is implicit rather than explicit about the discard.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Functionally correct. The implicit flow achieves the same result. Could add an explicit comment for clarity.

---

### 04-REQ-6.3: Extra asyncio.Lock in parallel batch API

**Spec says:** "THE orchestrator SHALL process session results sequentially in the single-threaded asyncio event loop after asyncio.wait() returns, which provides sequential state-write guarantees without an explicit lock."
**Code does:** The production streaming pool path is lock-free as specified. However, the parallel runner's batch API (test helper) uses an `asyncio.Lock()` for state writes.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The extra lock in the batch API is defense-in-depth for testing. The production code path (streaming pool) is lock-free as spec requires. Harmless divergence.

---

### 05-REQ-3.2: Fact dataclass has extra fields

**Spec says:** "Each stored fact SHALL contain all fields defined by the Fact data model: id, content, category, spec_name, keywords, confidence, created_at, and supersedes."
**Code does:** `Fact` dataclass includes all 8 specified fields PLUS two additional optional fields: `session_id: str | None = None` and `commit_sha: str | None = None` (from later specs 12+).
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Additive, backward-compatible extension from later specs. All core fields are present and correct.

---

### 07-REQ-2.3: File overlap detection data-blocked

**Spec says:** "THE standup report SHALL identify file overlaps: files modified by both the agent (from session records) and a human (from git log) during the reporting window."
**Code does:** `_detect_overlaps()` is called with an empty dict `{}` as `agent_files`, with a comment noting "SessionRecord does not track touched_paths yet." File overlaps are never detected.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** The feature scaffold is in place but lacks the data source. Root cause is that `SessionRecord` (spec 04) does not carry a `touched_paths` field.

---

### 07-REQ-2.5: Cost breakdown single-tier only

**Spec says:** "THE standup report SHALL include a cost breakdown by model tier used during the reporting window."
**Code does:** `_build_cost_breakdown()` groups all sessions under a single "default" tier because `SessionRecord` lacks a `model` field.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** low
**Rationale:** Structural code is present but data granularity is missing. Root cause: `SessionRecord` needs a `model` field.

---

### 13-REQ-3.2: get_causes() is private and returns only IDs

**Spec says:** "THE system SHALL provide a function to query the direct causes of a given fact."
**Code does:** `_get_direct_cause_ids()` is private (underscore prefix) and returns only fact IDs, not full `CausalFact` objects with content and provenance.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The functionality is covered by `traverse_causal_chain()` with `direction="causes"` and `max_depth=1`. The private helper is an implementation detail.

---

### 13-REQ-3.3: get_effects() is private and returns only IDs

**Spec says:** "THE system SHALL provide a function to query the direct effects of a given fact."
**Code does:** `_get_direct_effect_ids()` is private and returns only fact IDs, not full `CausalFact` objects.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Same as 13-REQ-3.2. Covered by `traverse_causal_chain()` with `direction="effects"`.

---

### 13-REQ-4.2: Missing synthesis step in temporal queries

**Spec says:** "THE temporal query result SHALL include both the causal timeline and a synthesized natural-language answer from the synthesis model, grounded in the timeline's facts."
**Code does:** `temporal_query()` returns a `Timeline` object with nodes and a query string, but does NOT invoke a synthesis model. The caller is responsible for synthesis.
**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** medium
**Rationale:** Synthesis may be intentionally handled at the CLI/ask layer rather than inside `temporal_query()`. If so, the spec should clarify the responsibility boundary.

---

### 13-REQ-5.1: Pattern detection SQL grouping differs

**Spec says:** Pattern detection should analyze co-occurrences using `fact_causes` and `session_outcomes` to identify recurring patterns.
**Code does:** The SQL query groups by `changed.touched_path, failed.touched_path` while the design document's SQL groups by `changed.touched_path, failed.spec_name`. This changes the semantics from "changes to path X cause spec Y to fail" to "changes to path X cause failures in path Y."
**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** low
**Rationale:** Both grouping strategies are valid. The code's file-to-file pattern may be more useful than spec-to-file. Determine which granularity is preferred.

---

### 13-REQ-6.3: use_color parameter is dead code

**Spec says:** "THE timeline format SHALL be plain text suitable for piping to other tools (no ANSI escape codes when stdout is not a TTY)."
**Code does:** `Timeline.render()` accepts `use_color: bool = True` but never emits ANSI codes regardless of the parameter value. The parameter is dead code.
**Drift type:** missing-edge-case
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Output is always plain text, satisfying the requirement. Either remove the dead `use_color` parameter or add color support for TTY output.

---

### 15-REQ-7.1: format_tokens is public instead of private

**Spec says:** Design document specifies `_format_tokens` (private with underscore prefix).
**Code does:** Function is named `format_tokens` (public, no underscore) in `formatters.py`.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The public function is more useful since it's imported by `code.py`. The function works correctly.

---

### 16-REQ-3.1: Summary format differs from agent-fox status

**Spec says:** "THE command SHALL print a compact summary containing: task counts, token usage, estimated cost, and run status."
**Code does:** `_print_summary()` prints all required fields but uses different formatting than `format_status`: double space, comma-separated, conditional parts, and combined failed+blocked count.
**Drift type:** behavioral
**Suggested mitigation:** Needs manual review
**Priority:** low
**Rationale:** All required information is present. The format differences (comma vs pipe separators, conditional parts) may be intentional for the code command's UX.

---

### 16-REQ-3.2: Summary style does not match agent-fox status

**Spec says:** "THE summary format SHALL match the compact text style used by `agent-fox status` (no Rich tables)."
**Code does:** The format diverges from `format_status()`. Code command uses comma separators and conditional parts; status uses pipe separators and always includes all categories. Cost format also differs.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The code command's format is arguably better UX (omits zero-count categories). Update spec to acknowledge the format differences, or align the two commands.

---

## Unimplemented Requirements

None. All 450 requirements have corresponding code implementations.

## Superseded Requirements

None. No `## Supersedes` sections were found in any spec's `prd.md`.

## In-Progress Caveats

### 09_spec_validation (completion: 97%)

| Requirement | Status | Notes |
|-------------|--------|-------|
| (none) | N/A | Only the final checkpoint task (Task 5) is unchecked. All 25 requirements are fully compliant. |

### 17_init_claude_settings (completion: 0% per tasks.md)

| Requirement | Status | Notes |
|-------------|--------|-------|
| All 10 reqs | Compliant | Implementation is complete in `agent_fox/cli/init.py`. The `tasks.md` was never updated to check off items. This is a task-tracking issue, not a code gap. |

## Extra Behavior (Best-Effort)

- **`ask` command `--timeline` flag:** The `ask` CLI command includes temporal query integration (`--timeline` flag, imports from `agent_fox.knowledge.temporal`). This is traced to spec 13 but extends beyond spec 12's `ask` command definition.
- **`fix` command `--dry-run` flag:** The `fix` CLI includes a `--dry-run` option not specified in spec 08 requirements. Enhancement beyond spec.
- **Standup "Agent Commits" section:** The standup formatter includes an "Agent Commits" section with corresponding `agent_commits: list[HumanCommit]` field in `StandupReport`. This section is not specified in the `15_standup_formatting` requirements.
- **KnowledgeStoreError exception:** Defined in `errors.py` alongside spec 01's error hierarchy but originates from later specs (11+). Additive, non-breaking.

## Process Issues

1. **Requirement ID Collision (Spec 15):** Both `15_session_prompt` and `15_standup_formatting` use the `15-REQ-*` prefix. This creates ambiguity when requirements are referenced outside their folder context. Consider renaming `15_standup_formatting` to `18_standup_formatting` or using a `15b-REQ-*` prefix.

2. **tasks.md Not Updated (Spec 17):** All 17 task checkboxes are `[ ]` (unchecked), yet the implementation is fully present and complete. This undermines `tasks.md` reliability as a tracking mechanism.

3. **Spec 16 Missing Files:** `16_code_command` has no `design.md` or `prd.md`. Only `requirements.md`, `tasks.md`, and `test_spec.md` are present. Interface comparison was skipped for this spec.

4. **Non-Standard Fix Folders:** `fix_01_ruff_format` and `fix_02_unnarrrowed_content_block_union` (note typo: triple-r) do not follow the `NN_snake_case` pattern. If intended as specs, they should be renumbered. If ad-hoc fixes, consider a separate location like `.specs/_fixes/`.

## Mitigation Summary

| Requirement | Mitigation | Priority |
|-------------|-----------|----------|
| 03-REQ-3.3 | Needs manual review | medium |
| 07-REQ-2.3 | Get well spec | medium |
| 13-REQ-4.2 | Needs manual review | medium |
| 02-REQ-4.E1 | Get well spec | low |
| 03-REQ-3.E1 | Change spec | low |
| 04-REQ-3.2 | Get well spec | low |
| 04-REQ-4.E1 | Change spec | low |
| 04-REQ-6.3 | Change spec | low |
| 05-REQ-3.2 | Change spec | low |
| 07-REQ-2.5 | Get well spec | low |
| 13-REQ-3.2 | Change spec | low |
| 13-REQ-3.3 | Change spec | low |
| 13-REQ-5.1 | Needs manual review | low |
| 13-REQ-6.3 | Change spec | low |
| 15-REQ-7.1 | Change spec | low |
| 16-REQ-3.1 | Needs manual review | low |
| 16-REQ-3.2 | Change spec | low |
