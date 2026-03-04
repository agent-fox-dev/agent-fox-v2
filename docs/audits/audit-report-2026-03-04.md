# Spec Audit Report

**Generated:** 2026-03-04
**Branch:** develop
**Specs analyzed:** 18

## Skipped Items

| Item | Reason |
|------|--------|
| `fix_01_ruff_format` | Name does not match `\d{2}_[a-z_]+` pattern |
| `fix_02_unnarrrowed_content_block_union` | Name does not match `\d{2}_[a-z_]+` pattern |
| `test_spec` | Name does not match expected pattern |
| `prd.md` | Not a spec directory |
| `v2.md` | Not a spec directory |

## Summary

| Category | Count |
|----------|-------|
| Compliant | 399 |
| Drifted | 14 |
| Unimplemented | 0 |
| Superseded | 0 |
| In-progress (expected gaps) | 0 |

## Compliant Requirements

### 01_core_foundation (38/38 compliant)

| Requirement | Description |
|-------------|-------------|
| 01-REQ-1.1 | CLI `agent-fox` command with `--version` and `--help` |
| 01-REQ-1.2 | Subcommand registration without modifying entry point |
| 01-REQ-1.3 | Themed banner with project name and version |
| 01-REQ-1.4 | Console script entry point via pyproject.toml |
| 01-REQ-1.E1 | Unknown subcommand exits with code 2 |
| 01-REQ-2.1 | Load TOML config, validate with pydantic, merge defaults |
| 01-REQ-2.2 | Clear error for invalid field value |
| 01-REQ-2.3 | Missing fields use documented defaults |
| 01-REQ-2.4 | All PRD Section 6 settings exposed |
| 01-REQ-2.5 | CLI options override config values |
| 01-REQ-2.6 | Unknown keys logged and ignored |
| 01-REQ-2.E1 | Missing config file returns defaults |
| 01-REQ-2.E2 | Invalid TOML raises clear parse error |
| 01-REQ-2.E3 | Out-of-range numeric values clamped with warning |
| 01-REQ-3.1 | Init creates `.agent-fox/` with config, hooks/, worktrees/ |
| 01-REQ-3.2 | Create/verify develop branch |
| 01-REQ-3.3 | Already-initialized preserves config |
| 01-REQ-3.4 | `.agent-fox/*` in .gitignore with track exceptions |
| 01-REQ-3.5 | Non-git repo exits with error code 1 |
| 01-REQ-3.E1 | `.agent-fox/` exists but config missing creates config |
| 01-REQ-3.E2 | Develop branch already exists is no-op |
| 01-REQ-4.1 | Base `AgentFoxError` exception class |
| 01-REQ-4.2 | Specific exception subclasses |
| 01-REQ-4.3 | Human-readable message + structured context |
| 01-REQ-4.E1 | Unexpected exception at CLI top level handled |
| 01-REQ-5.1 | Three model tiers (SIMPLE, STANDARD, ADVANCED) |
| 01-REQ-5.2 | Model entry with ID, tier, input/output prices |
| 01-REQ-5.3 | Lookup by tier name or model ID |
| 01-REQ-5.4 | Cost calculation function |
| 01-REQ-5.E1 | Unknown model raises ConfigError with valid options |
| 01-REQ-6.1 | Logging format `[LEVEL] component: message` |
| 01-REQ-6.2 | Default WARNING, `--verbose` for DEBUG |
| 01-REQ-6.3 | Named loggers per module |
| 01-REQ-6.E1 | `--verbose` + `--quiet` prefers verbose |
| 01-REQ-7.1 | Theme with named color roles |
| 01-REQ-7.2 | Theme overrides from `[theme]` config |
| 01-REQ-7.3 | Playful mode with fox-themed messages |
| 01-REQ-7.4 | Neutral mode with professional messages |
| 01-REQ-7.E1 | Invalid Rich style falls back to default |

### 02_planning_engine (28/29 compliant)

| Requirement | Description |
|-------------|-------------|
| 02-REQ-1.1 | Scan `.specs/` for spec directories sorted by prefix |
| 02-REQ-1.2 | `--spec` restricts to single spec |
| 02-REQ-1.3 | Skip specs without `tasks.md` with warning |
| 02-REQ-1.E1 | Empty/missing `.specs/` raises PlanError |
| 02-REQ-1.E2 | `--spec` value not found raises PlanError |
| 02-REQ-2.1 | Parse top-level task groups from `tasks.md` |
| 02-REQ-2.2 | Extract nested subtasks |
| 02-REQ-2.3 | Detect optional `*` marker |
| 02-REQ-2.4 | Extract title and body text |
| 02-REQ-2.E1 | No parseable groups returns empty list |
| 02-REQ-2.E2 | Non-contiguous group numbers accepted |
| 02-REQ-3.1 | Sequential intra-spec edges |
| 02-REQ-3.2 | Cross-spec edges from prd.md dependency table |
| 02-REQ-3.3 | Node ID format `{spec_name}:{group_number}` |
| 02-REQ-3.4 | All nodes initialized with `pending` |
| 02-REQ-3.E2 | Cycle detection raises PlanError |
| 02-REQ-4.1 | Topological ordering |
| 02-REQ-4.2 | Deterministic ordering by prefix then group |
| 02-REQ-4.E1 | Empty graph produces empty ordering |
| 02-REQ-5.1 | Fast mode removes optional nodes |
| 02-REQ-5.2 | Rewire dependencies around removed nodes |
| 02-REQ-5.3 | Record fast-mode flag in metadata |
| 02-REQ-6.1 | Serialize graph as JSON |
| 02-REQ-6.2 | Metadata with timestamp, fast-mode, version |
| 02-REQ-6.3 | Load existing plan when not `--reanalyze` |
| 02-REQ-6.4 | `--reanalyze` discards and rebuilds |
| 02-REQ-6.E1 | Corrupted plan.json discarded and rebuilt |
| 02-REQ-7.1 | `agent-fox plan` subcommand with summary |
| 02-REQ-7.2 | `--fast` flag |
| 02-REQ-7.3 | `--spec NAME` option |
| 02-REQ-7.4 | `--reanalyze` flag |
| 02-REQ-7.5 | `--verify` placeholder |

### 03_session_and_workspace (28/30 compliant)

| Requirement | Description |
|-------------|-------------|
| 03-REQ-1.1 | Create worktree at `.agent-fox/worktrees/{spec}/{group}` |
| 03-REQ-1.2 | Feature branch `feature/{spec_name}/{group_number}` |
| 03-REQ-1.3 | Return `WorkspaceInfo` with path, branch, spec, group |
| 03-REQ-1.E1 | Stale worktree removed and re-created |
| 03-REQ-1.E2 | Stale feature branch deleted |
| 03-REQ-1.E3 | Git error raises `WorkspaceError` |
| 03-REQ-2.1 | Destroy removes worktree and deletes branch |
| 03-REQ-2.2 | Empty spec directory removed |
| 03-REQ-2.E1 | Non-existent worktree path is no-op |
| 03-REQ-2.E2 | Branch deletion failure logged as warning |
| 03-REQ-3.1 | Invoke claude-code-sdk with prompt, system prompt, cwd, model |
| 03-REQ-3.2 | Iterate messages, collect final ResultMessage |
| 03-REQ-3.4 | `bypassPermissions` mode + PreToolUse allowlist |
| 03-REQ-3.E1 | SDK exceptions caught, return failed SessionOutcome |
| 03-REQ-3.E2 | `is_error=True` sets failed status |
| 03-REQ-4.1 | Read spec documents for context |
| 03-REQ-4.2 | Accept memory facts list |
| 03-REQ-4.3 | Return formatted string with section headers |
| 03-REQ-4.E1 | Missing spec file skipped with warning |
| 03-REQ-5.1 | System prompt from templates with role parameter |
| 03-REQ-5.2 | Task prompt identifies task group, instructs commit |
| 03-REQ-6.1 | Wrap SDK query in `asyncio.wait_for()` with timeout |
| 03-REQ-6.2 | Timeout returns SessionOutcome with status `timeout` |
| 03-REQ-6.E1 | Preserve partial metrics on timeout |
| 03-REQ-7.1 | Fast-forward merge of feature branch into develop |
| 03-REQ-7.2 | Rebase and retry on FF failure |
| 03-REQ-7.3 | Return changed files list on success |
| 03-REQ-7.E2 | No new commits is a no-op |
| 03-REQ-8.1 | PreToolUse hook intercepts Bash invocations |
| 03-REQ-8.2 | Block non-allowlisted commands |
| 03-REQ-8.E1 | Empty command string blocked |
| 03-REQ-9.1 | Git module provides branch/merge/rebase functions |
| 03-REQ-9.2 | Git failures raise WorkspaceError or IntegrationError |

### 04_orchestrator (31/32 compliant)

| Requirement | Description |
|-------------|-------------|
| 04-REQ-1.1 | Load task graph, identify ready tasks |
| 04-REQ-1.2 | Execute tasks serial or parallel |
| 04-REQ-1.3 | After session, update graph, persist, re-evaluate |
| 04-REQ-1.4 | Warn when stalled |
| 04-REQ-1.E1 | Missing/corrupted plan.json raises PlanError |
| 04-REQ-1.E2 | Empty plan exits successfully |
| 04-REQ-2.1 | Retry failed tasks up to max_retries |
| 04-REQ-2.2 | Pass previous error to retry |
| 04-REQ-2.3 | All retries exhausted marks task as blocked |
| 04-REQ-2.E1 | max_retries=0 blocks on first failure |
| 04-REQ-3.1 | Cascade-block dependent tasks |
| 04-REQ-3.2 | Record blocking reason |
| 04-REQ-3.E1 | Multiple upstream paths handled |
| 04-REQ-4.1 | Persist ExecutionState to state.jsonl |
| 04-REQ-4.2 | State includes plan hash, statuses, history, totals |
| 04-REQ-4.3 | Resume: load state, verify plan hash, continue |
| 04-REQ-4.E1 | Plan hash mismatch starts fresh |
| 04-REQ-4.E2 | Corrupted state file discarded |
| 04-REQ-5.1 | Cost limit stops launches |
| 04-REQ-5.2 | Allow in-flight to complete on cost limit |
| 04-REQ-5.3 | Session limit stops launches |
| 04-REQ-5.E1 | Single session exceeding budget not cancelled |
| 04-REQ-6.1 | Parallel execution up to configured parallelism |
| 04-REQ-6.2 | Max parallelism capped at 8 |
| 04-REQ-6.3 | Sequential state writes |
| 04-REQ-6.E1 | Fewer ready than parallelism, execute available |
| 04-REQ-7.1 | Task transitions pending->in_progress once per attempt |
| 04-REQ-7.2 | Resume does not re-execute completed tasks |
| 04-REQ-7.E1 | In-progress tasks on resume treated as pending |
| 04-REQ-8.1 | SIGINT saves state |
| 04-REQ-8.2 | SIGINT cancels in-flight parallel tasks |
| 04-REQ-8.3 | SIGINT prints progress summary |
| 04-REQ-8.E1 | Double SIGINT exits immediately |
| 04-REQ-9.1 | Inter-session delay |
| 04-REQ-9.E1 | Delay 0 means no pause |
| 04-REQ-10.1 | Completed task re-evaluates pending tasks |
| 04-REQ-10.2 | Blocked task cascades |
| 04-REQ-10.E1 | All remaining blocked, report stalled |

### 05_structured_memory (26/27 compliant)

| Requirement | Description |
|-------------|-------------|
| 05-REQ-1.1 | Extract facts using SIMPLE model |
| 05-REQ-1.2 | Extraction prompt requests content, category, confidence, keywords |
| 05-REQ-1.3 | Assign UUID, spec_name, ISO 8601 timestamp |
| 05-REQ-1.E1 | Invalid JSON from LLM: log warning, skip |
| 05-REQ-1.E2 | Zero facts: log debug, continue |
| 05-REQ-2.1 | Six fact categories |
| 05-REQ-2.2 | Unknown category defaults to `gotcha` |
| 05-REQ-3.1 | Store in `.agent-fox/memory.jsonl` |
| 05-REQ-3.2 | Fact contains all specified fields |
| 05-REQ-3.3 | Append without modifying existing lines |
| 05-REQ-3.E1 | Create file if it doesn't exist |
| 05-REQ-3.E2 | Write failure: log error, continue |
| 05-REQ-4.2 | Rank by keyword match count + recency bonus |
| 05-REQ-4.3 | Return at most 50 facts |
| 05-REQ-4.E1 | No matches: return empty list |
| 05-REQ-4.E2 | Missing/empty file: return empty list |
| 05-REQ-5.1 | Deduplicate by content hash, keep earliest |
| 05-REQ-5.2 | Resolve supersession chains |
| 05-REQ-5.3 | Rewrite JSONL in place |
| 05-REQ-5.E1 | Empty/missing file: no compaction needed |
| 05-REQ-5.E2 | Idempotent compaction |
| 05-REQ-6.1 | Generate `docs/memory.md` organized by category |
| 05-REQ-6.2 | Each entry includes content, spec_name, confidence |
| 05-REQ-6.3 | Regenerate at sync barriers and on demand |
| 05-REQ-6.E1 | Create `docs/` if missing |
| 05-REQ-6.E2 | Empty KB generates "no facts" message |

### 06_hooks_sync_security (25/25 compliant)

| Requirement | Description |
|-------------|-------------|
| 06-REQ-1.1 | Execute pre-session hooks in order |
| 06-REQ-1.2 | Execute post-session hooks in order |
| 06-REQ-1.E1 | No hooks configured: proceed without error |
| 06-REQ-2.1 | Non-zero exit + abort mode: raise HookError |
| 06-REQ-2.2 | Non-zero exit + warn mode: log warning, continue |
| 06-REQ-2.3 | Default mode is "abort" |
| 06-REQ-2.E1 | Hook not found/not executable: treat as failure |
| 06-REQ-3.1 | Configurable timeout (default 300s) |
| 06-REQ-3.2 | Timeout terminates subprocess, treated as failure |
| 06-REQ-4.1 | Pass AF_SPEC_NAME, AF_TASK_GROUP, AF_WORKSPACE, AF_BRANCH |
| 06-REQ-4.2 | Sync barrier hooks use `__sync_barrier__` |
| 06-REQ-5.1 | `--no-hooks` skips all hooks |
| 06-REQ-6.1 | Sync barriers at configurable intervals |
| 06-REQ-6.2 | Regenerate knowledge summary at barrier |
| 06-REQ-6.3 | Scan `.specs/` for new specs at barrier |
| 06-REQ-6.E1 | sync_interval=0 disables barriers |
| 06-REQ-7.1 | Parse tasks for new specs, add to graph |
| 06-REQ-7.2 | Resolve cross-spec dependencies |
| 06-REQ-7.3 | Re-compute topological ordering |
| 06-REQ-7.E1 | Dependency on non-existent spec: log warning, skip |
| 06-REQ-7.E2 | No new specs: continue without modifying graph |
| 06-REQ-8.1 | PreToolUse hook intercepts Bash, extracts command |
| 06-REQ-8.2 | Block if not on allowlist |
| 06-REQ-8.3 | Default allowlist of development commands |
| 06-REQ-8.E1 | Empty command: block with error |
| 06-REQ-8.E2 | Non-Bash tools pass through |
| 06-REQ-9.1 | `bash_allowlist` replaces default entirely |
| 06-REQ-9.2 | `bash_allowlist_extend` adds to default |
| 06-REQ-9.E1 | Both set: bash_allowlist takes precedence |

### 07_operational_commands (27/27 compliant)

| Requirement | Description |
|-------------|-------------|
| 07-REQ-1.1 | Status shows task counts by status |
| 07-REQ-1.2 | Status shows cumulative tokens and estimated cost |
| 07-REQ-1.3 | Status shows blocked/failed tasks with reasons |
| 07-REQ-1.E1 | No state file: show plan with all pending |
| 07-REQ-1.E2 | No state or plan: error instructing `agent-fox plan` |
| 07-REQ-2.1 | Standup covers configurable time window |
| 07-REQ-2.2 | Standup includes human commits |
| 07-REQ-2.3 | Standup identifies file overlaps |
| 07-REQ-2.4 | Standup includes queue summary |
| 07-REQ-2.5 | Standup includes cost breakdown by model tier |
| 07-REQ-2.E1 | No agent activity: report zero, show human commits |
| 07-REQ-2.E2 | No git commits: report zero human commits |
| 07-REQ-3.1 | `--format` option: table, json, yaml |
| 07-REQ-3.2 | JSON output is valid JSON |
| 07-REQ-3.3 | YAML output is valid YAML |
| 07-REQ-3.4 | Standup `--output` writes to file |
| 07-REQ-3.E1 | Unwritable output path: error, exit 1 |
| 07-REQ-4.1 | Full reset: reset failed/blocked/in_progress to pending |
| 07-REQ-4.2 | Clean up worktree and branch per reset task |
| 07-REQ-4.3 | Full reset: show list, prompt confirmation |
| 07-REQ-4.4 | `--yes` skips confirmation |
| 07-REQ-4.E1 | Nothing to reset: info message, exit 0 |
| 07-REQ-4.E2 | No state file: error instructing `agent-fox code` |
| 07-REQ-5.1 | Single-task reset: reset to pending, clean up |
| 07-REQ-5.2 | Cascade unblock sole-blocker dependents |
| 07-REQ-5.3 | Single-task reset: no confirmation |
| 07-REQ-5.E1 | Unknown task ID: error listing valid IDs |
| 07-REQ-5.E2 | Completed task: warning, no changes |

### 08_error_autofix (19/22 compliant)

| Requirement | Description |
|-------------|-------------|
| 08-REQ-1.1 | Inspect project config files to detect checks |
| 08-REQ-1.2 | Detect pytest, ruff, mypy, npm test/lint, make test, cargo test |
| 08-REQ-1.3 | CheckDescriptor with name, command, category |
| 08-REQ-1.E1 | No checks detected: error, non-zero exit |
| 08-REQ-1.E2 | Unparseable config: log warning, skip |
| 08-REQ-2.1 | Run each check as subprocess, capture output |
| 08-REQ-2.2 | Non-zero exit: create FailureRecord |
| 08-REQ-2.3 | All checks pass: report all pass, terminate loop |
| 08-REQ-2.E1 | Timeout (5 min): record failure, continue |
| 08-REQ-3.2 | Cluster includes label, failures, suggested_approach |
| 08-REQ-3.3 | AI unavailable: fallback to one cluster per check |
| 08-REQ-4.1 | Generate fix spec with requirements, design, tasks |
| 08-REQ-4.2 | Write to `.agent-fox/fix_specs/pass_{N}_{label}/` |
| 08-REQ-5.3 | Use same SessionRunner as regular sessions |
| 08-REQ-6.1 | Summary report with passes, clusters, sessions, reason |
| 08-REQ-6.2 | Termination reason enum |
| 08-REQ-7.1 | Expose as `agent-fox fix` subcommand |
| 08-REQ-7.2 | `--max-passes` option (int, default 3) |
| 08-REQ-7.E1 | max_passes <= 0: clamp to 1, log warning |

### 09_spec_validation (23/25 compliant)

| Requirement | Description |
|-------------|-------------|
| 09-REQ-1.1 | Discover all spec folders |
| 09-REQ-1.2 | Run all enabled validation rules |
| 09-REQ-1.3 | Sort findings by spec name, file name, severity |
| 09-REQ-1.E1 | No specs directory: single Error finding |
| 09-REQ-2.1 | Check for 5 expected files |
| 09-REQ-2.2 | Error-severity finding per missing file |
| 09-REQ-3.1 | Count subtasks excluding verification steps |
| 09-REQ-3.2 | Warning when count exceeds 6 |
| 09-REQ-4.1 | Check for N.V verification subtask |
| 09-REQ-4.2 | Warning when verification step missing |
| 09-REQ-5.1 | Check requirement sections for acceptance criteria |
| 09-REQ-5.2 | Error when section has no criteria |
| 09-REQ-6.1 | Parse cross-spec dependency declarations |
| 09-REQ-6.2 | Error when dependency references non-existent spec |
| 09-REQ-6.3 | Error when dependency references non-existent group |
| 09-REQ-7.1 | Collect requirement IDs from requirements.md and test_spec.md |
| 09-REQ-7.2 | Warning when requirement ID not referenced |
| 09-REQ-8.2 | Identify vague criteria as Hint findings |
| 09-REQ-8.3 | Identify implementation-leaking criteria as Hints |
| 09-REQ-8.E1 | AI unavailable: log warning, continue static |
| 09-REQ-9.3 | JSON and YAML serialize findings plus summary |
| 09-REQ-9.4 | Exit code 1 when any Error findings |
| 09-REQ-9.5 | Exit code 0 when no Error findings |

### 10_platform_integration (26/26 compliant)

| Requirement | Description |
|-------------|-------------|
| 10-REQ-1.1 | Platform as typing.Protocol with 4 methods |
| 10-REQ-1.2 | create_pr accepts branch, title, body, labels |
| 10-REQ-1.3 | wait_for_ci accepts PR URL and timeout |
| 10-REQ-1.4 | wait_for_review accepts PR URL |
| 10-REQ-1.5 | merge_pr accepts PR URL |
| 10-REQ-2.1 | Platform type "none" uses NullPlatform |
| 10-REQ-2.2 | NullPlatform.create_pr merges directly |
| 10-REQ-2.3 | NullPlatform.wait_for_ci returns True |
| 10-REQ-2.4 | NullPlatform.wait_for_review returns True |
| 10-REQ-2.5 | NullPlatform.merge_pr is no-op |
| 10-REQ-3.1 | Platform type "github" uses GitHubPlatform |
| 10-REQ-3.2 | GitHubPlatform.create_pr executes `gh pr create` |
| 10-REQ-3.3 | wait_for_ci polls at 30s intervals |
| 10-REQ-3.4 | wait_for_review polls at 60s intervals |
| 10-REQ-3.5 | merge_pr executes `gh pr merge` |
| 10-REQ-3.E1 | gh not installed: IntegrationError |
| 10-REQ-3.E2 | gh pr create fails: IntegrationError |
| 10-REQ-3.E3 | CI check failure: returns False |
| 10-REQ-3.E4 | CI timeout: returns False |
| 10-REQ-3.E5 | Review rejected: returns False |
| 10-REQ-3.E6 | gh pr merge fails: IntegrationError |
| 10-REQ-4.1 | Platform provides building-block primitives |
| 10-REQ-4.2 | PR granularity is orchestrator-level concern |
| 10-REQ-5.1 | create_platform(config) factory |
| 10-REQ-5.2 | config.type "none" -> NullPlatform |
| 10-REQ-5.3 | config.type "github" -> GitHubPlatform |
| 10-REQ-5.E1 | Unrecognized type -> ConfigError |

### 11_duckdb_knowledge_store (23/23 compliant)

| Requirement | Description |
|-------------|-------------|
| 11-REQ-1.1 | Create DuckDB at configured store_path |
| 11-REQ-1.2 | Install/load VSS extension |
| 11-REQ-1.3 | Close connection cleanly |
| 11-REQ-1.E1 | Create parent directory if missing |
| 11-REQ-1.E2 | Raise KnowledgeStoreError on open failure |
| 11-REQ-2.1 | Create all schema tables on first use |
| 11-REQ-2.2 | Record version 1 as initial schema version |
| 11-REQ-2.3 | memory_embeddings uses FLOAT[N] from config |
| 11-REQ-3.1 | Apply pending migrations in order |
| 11-REQ-3.2 | Each migration is a numbered Python function |
| 11-REQ-3.3 | Record version row on migration |
| 11-REQ-3.E1 | Migration failure -> KnowledgeStoreError |
| 11-REQ-4.1 | SessionSink as typing.Protocol |
| 11-REQ-4.2 | Session runner calls sinks transparently |
| 11-REQ-4.3 | Multiple sinks composable via dispatcher |
| 11-REQ-5.1 | DuckDB sink implements SessionSink |
| 11-REQ-5.2 | record_session_outcome always writes |
| 11-REQ-5.3 | Tool signals written only when debug=True |
| 11-REQ-5.4 | Tool signals are no-ops when debug=False |
| 11-REQ-5.E1 | DuckDB write failure: log warning, don't raise |
| 11-REQ-6.1 | JSONL sink implements SessionSink |
| 11-REQ-6.2 | JSONL sink writes all events as JSON lines |
| 11-REQ-6.3 | JSONL sink only attached in debug mode |
| 11-REQ-7.1 | Corrupted DB: log warning, continue without store |
| 11-REQ-7.2 | Mid-run DuckDB failure: log error, continue |
| 11-REQ-7.3 | Fall back to JSONL-only or skip |

### 12_fox_ball (20/22 compliant)

| Requirement | Description |
|-------------|-------------|
| 12-REQ-1.1 | Dual-write to JSONL and DuckDB |
| 12-REQ-1.2 | JSONL remains source of truth |
| 12-REQ-1.3 | Populate all provenance fields in DuckDB |
| 12-REQ-1.E1 | DuckDB write fails: still write JSONL |
| 12-REQ-2.E1 | Embedding failure: write fact without embedding |
| 12-REQ-2.E2 | Embedding API fails on ask: report error |
| 12-REQ-3.1 | Vector similarity search using cosine |
| 12-REQ-3.2 | Return top-k results with provenance and score |
| 12-REQ-3.3 | Exclude facts without embeddings |
| 12-REQ-3.E1 | Empty store: return empty result set |
| 12-REQ-4.1 | Ingest ADRs as category="adr" facts |
| 12-REQ-4.2 | Ingest git commits as category="git" facts |
| 12-REQ-4.3 | Ingested sources embedded and stored |
| 12-REQ-5.1 | ask command: embed, search, synthesize, return |
| 12-REQ-5.2 | Answer includes source attributions |
| 12-REQ-5.3 | Single API call with STANDARD model |
| 12-REQ-5.E1 | Empty store: message about no knowledge |
| 12-REQ-5.E2 | Store unavailable: error message |
| 12-REQ-6.1 | Contradiction detection in synthesis |
| 12-REQ-7.1 | Track supersession via superseded_by column |
| 12-REQ-7.2 | Superseded facts excluded from search |
| 12-REQ-8.1 | Confidence indicator in oracle answer |

### 13_time_vision (17/18 compliant)

| Requirement | Description |
|-------------|-------------|
| 13-REQ-1.1 | Populate provenance fields in memory_facts |
| 13-REQ-1.2 | Store NULL for unavailable provenance |
| 13-REQ-2.1 | Extraction prompt includes causal instructions |
| 13-REQ-2.2 | Store causal relationship in fact_causes |
| 13-REQ-2.E1 | No causal links: store facts without causal metadata |
| 13-REQ-2.E2 | Causal link to non-existent fact: skip, warn |
| 13-REQ-3.1 | store_causal_links with INSERT OR IGNORE |
| 13-REQ-3.2 | Query direct causes of a fact |
| 13-REQ-3.3 | Query direct effects of a fact |
| 13-REQ-3.4 | Traverse causal chain with configurable max_depth |
| 13-REQ-3.E1 | Duplicate causal link silently ignored |
| 13-REQ-4.1 | Temporal query: vector search + causal traversal |
| 13-REQ-4.2 | temporal_query returns Timeline |
| 13-REQ-5.1 | Batch pattern detection |
| 13-REQ-5.2 | Pattern includes trigger, effect, occurrences, confidence |
| 13-REQ-5.3 | `agent-fox patterns` CLI command |
| 13-REQ-5.E1 | No patterns: informational message |
| 13-REQ-6.1 | Timeline rendering with all fields |
| 13-REQ-6.2 | Indentation depth corresponds to chain position |
| 13-REQ-7.1 | Query causal graph for context before session |
| 13-REQ-7.2 | Causal facts are additive within 50-fact budget |

### 14_cli_banner (12/12 compliant)

| Requirement | Description |
|-------------|-------------|
| 14-REQ-1.1 | Fox art in banner output |
| 14-REQ-1.2 | Fox art styled with header role |
| 14-REQ-2.1 | Version in banner |
| 14-REQ-2.2 | Model ID in banner |
| 14-REQ-2.3 | Version/model line styled with header |
| 14-REQ-2.E1 | Model resolution fallback |
| 14-REQ-3.1 | Working directory in banner |
| 14-REQ-3.2 | CWD styled with muted role |
| 14-REQ-3.E1 | OSError fallback to "(unknown)" |
| 14-REQ-4.1 | Banner on every invocation |
| 14-REQ-4.2 | `--quiet` suppresses banner |

### 15_session_prompt (18/19 compliant)

| Requirement | Description |
|-------------|-------------|
| 15-REQ-1.1 | Coordinator system prompt includes role definition |
| 15-REQ-1.2 | Coding system prompt includes coding instructions |
| 15-REQ-1.3 | Template files in `_templates/prompts/` |
| 15-REQ-1.E1 | Missing template raises PlanError |
| 15-REQ-2.1 | Context block appended after template |
| 15-REQ-2.3 | Memory facts formatted as bulleted list |
| 15-REQ-2.E1 | Empty context omits section |
| 15-REQ-3.1 | Task prompt includes spec name |
| 15-REQ-3.2 | Task prompt includes group number |
| 15-REQ-3.3 | Task prompt includes previous error on retry |
| 15-REQ-3.E1 | First attempt omits error section |
| 15-REQ-4.1 | Commit message format in task prompt |
| 15-REQ-4.2 | Checkbox update instructions |
| 15-REQ-5.1 | Prompt length within model context window |
| 15-REQ-5.E1 | Oversized prompt: truncate context, log warning |

### 15_standup_formatting (22/22 compliant)

| Requirement | Description |
|-------------|-------------|
| 15-REQ-1.1 | Table format uses Rich table |
| 15-REQ-1.2 | Table includes all standup sections |
| 15-REQ-1.E1 | Terminal too narrow: wrap gracefully |
| 15-REQ-2.1 | Task activity section with per-task rows |
| 15-REQ-2.2 | Human commit section with authors |
| 15-REQ-2.3 | Queue summary section |
| 15-REQ-2.4 | Cost breakdown section |
| 15-REQ-2.5 | File overlap section |
| 15-REQ-2.E1 | Empty sections show placeholder |
| 15-REQ-3.1 | Token counts formatted with commas |
| 15-REQ-3.2 | Cost formatted as $X.XXXX |
| 15-REQ-3.3 | Duration formatted as Xm Ys |
| 15-REQ-3.E1 | Zero values displayed as "0" or "$0.0000" |
| 15-REQ-4.1 | Status indicators use Unicode symbols |
| 15-REQ-4.2 | Color coding for status |
| 15-REQ-4.E1 | Non-Unicode terminal: fallback text labels |
| 15-REQ-5.1 | Consistent section ordering |

### 16_code_command (21/22 compliant)

| Requirement | Description |
|-------------|-------------|
| 16-REQ-1.1 | `agent-fox code` subcommand |
| 16-REQ-1.2 | Auto-plan if no plan exists |
| 16-REQ-1.3 | `--fast` flag |
| 16-REQ-1.4 | `--spec NAME` option |
| 16-REQ-1.5 | `--parallel` flag |
| 16-REQ-1.6 | `--reanalyze` flag |
| 16-REQ-1.E1 | Not initialized: error instructing `agent-fox init` |
| 16-REQ-2.1 | Override `models.coding` |
| 16-REQ-2.2 | Override `orchestrator.max_retries` |
| 16-REQ-2.3 | Override `orchestrator.max_sessions` |
| 16-REQ-2.4 | Override `orchestrator.max_cost` |
| 16-REQ-2.E1 | Invalid override value: error with message |
| 16-REQ-3.2 | Exit code 0 for completed |
| 16-REQ-3.3 | Exit code 1 for stalled/interrupted |
| 16-REQ-4.1 | Wire plan -> orchestrator -> session runner |
| 16-REQ-4.2 | Pass config overrides to orchestrator |
| 16-REQ-4.3 | Respect `--no-hooks` |
| 16-REQ-4.E1 | Orchestrator exception: error, exit 1 |

### 17_init_claude_settings (10/10 compliant)

| Requirement | Description |
|-------------|-------------|
| 17-REQ-1.1 | Create `.claude/settings.local.json` on init |
| 17-REQ-1.2 | Populate allowedTools with canonical list |
| 17-REQ-1.3 | Include both Bash and Read tool entries |
| 17-REQ-1.E1 | `.claude/` directory created if missing |
| 17-REQ-2.1 | Merge with existing settings preserving user entries |
| 17-REQ-2.2 | Add missing canonical entries |
| 17-REQ-2.3 | Do not remove user-added entries |
| 17-REQ-2.E1 | Malformed JSON: backup and recreate |
| 17-REQ-3.1 | Idempotent: re-running produces same result |
| 17-REQ-3.2 | No duplicate entries in allowedTools |

## Drifted Requirements

### 02-REQ-3.E1: Dangling cross-spec dependency handling

**Spec says:** The system SHALL raise a `PlanError` when a cross-spec dependency references a non-existent spec or task group.
**Code does:** Silently filters cross-spec dependencies that reference specs not in the discovered set (`plan.py` lines 83-89), rather than raising.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The silent-filter behavior is intentional -- it enables `--spec` single-spec filtering to work without raising on unresolved cross-deps. The spec should acknowledge this by-design exception.

---

### 03-REQ-3.3: SessionOutcome missing `files_touched`

**Spec says:** `SessionOutcome` SHALL include a `files_touched` field.
**Code does:** `SessionOutcome` (in `knowledge/sink.py`) does not include `files_touched`. Files touched are tracked at the orchestrator/harvester level via `get_changed_files()`.
**Drift type:** structural
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** File tracking was deliberately moved to the harvester layer where it naturally belongs (post-merge). The spec should reflect this architectural refinement.

---

### 03-REQ-7.E1: Rebase failure fallback to merge commit

**Spec says:** On unresolvable rebase conflict, abort rebase, raise `IntegrationError`, leave develop unchanged.
**Code does:** On rebase failure, aborts rebase and falls back to a regular merge commit (`merge_commit()`). Only raises `IntegrationError` if the merge commit also fails (`harvester.py` lines 87-107).
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** medium
**Rationale:** The merge-commit fallback is a deliberate resilience improvement. It avoids blocking the entire pipeline on a rebase conflict when a merge commit would succeed. The spec should document this two-stage merge strategy.

---

### 04-REQ-9.2: Inter-session delay skip when no more ready tasks

**Spec says:** Delay SHALL be skipped when there are no more ready tasks to launch.
**Code does:** Delay skip is implicit in the loop structure (loop exits when no ready tasks remain). The behavior is functionally equivalent but there is no explicit guard checking for remaining ready tasks.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** The loop naturally exits without inserting a delay when no tasks remain. Functionally compliant; spec could be clarified to say "delay is only inserted between consecutive session launches."

---

### 05-REQ-4.1: Fact selection logic (AND vs OR)

**Spec says:** Select facts by matching `spec_name` (exact match) AND keyword overlap.
**Code does:** Matches on `spec_name` OR keyword overlap. Facts with matching spec_name are included even without keyword overlap; facts with keyword overlap are included without spec_name match (`retrieval.py` lines 54-59).
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** medium
**Rationale:** OR logic produces broader, more useful context for sessions. Requiring both spec_name AND keyword overlap would be overly restrictive, potentially omitting relevant facts from the same spec. The spec should reflect the intentional OR-based selection.

---

### 08-REQ-3.1: Clustering model tier

**Spec says:** Send failure records to the STANDARD model tier for clustering.
**Code does:** Uses `config.models.coordinator` (`clusterer.py` line 68) rather than explicitly resolving the STANDARD tier. The coordinator model may or may not be STANDARD.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** low
**Rationale:** Using the configured coordinator model is more flexible and consistent with the rest of the system. The spec should reference the coordinator model rather than hardcoding STANDARD.

---

### 08-REQ-5.1: No final re-check after last pass

**Spec says:** After the last pass's fix sessions complete, run quality checks one final time to verify the outcome.
**Code does:** Checks only run at the start of each pass iteration. If the last pass exhausts `max_passes`, the fixes from the last pass are never verified.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Users may believe all checks pass when they don't. A final verification after the last pass would ensure the reported outcome matches reality.

---

### 08-REQ-5.2: Cost limit not implemented in fix loop

**Spec says:** The fix loop SHALL terminate when the configured cost limit is reached. `COST_LIMIT` is one of four termination reasons.
**Code does:** The `COST_LIMIT` termination reason exists in the `TerminationReason` enum but is never set. The loop does not track cumulative cost or check against any limit.
**Drift type:** missing-edge-case
**Suggested mitigation:** Get well spec
**Priority:** high
**Rationale:** Without cost limit enforcement, the fix loop could run up unbounded costs. This is a missing safety mechanism that the spec explicitly requires.

---

### 09-REQ-8.1: AI validation model selection

**Spec says:** Use the STANDARD tier model via `resolve_model()` for AI-assisted validation.
**Code does:** Hardcodes `"claude-sonnet-4-20250514"` in `lint_spec.py` line 195 instead of calling `resolve_model("STANDARD")`.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Hardcoding the model ID bypasses the model registry and will break when model versions change. Should use `resolve_model("STANDARD")` for consistency with the rest of the codebase.

---

### 09-REQ-9.2: Table format rendering technology

**Spec says:** Use Rich library `rich.table.Table` for table output with columns grouped by spec.
**Code does:** Uses plain text string formatting with Unicode severity markers. Content is correct but rendering technology differs from the design doc.
**Drift type:** structural
**Suggested mitigation:** Needs manual review
**Priority:** low
**Rationale:** The output contains all required information (severity, file, rule, message, line, summary). Whether Rich tables add value over the current compact format is a UX decision.

---

### 12-REQ-2.1 / 12-REQ-2.2: Embedding technology

**Spec says:** Generate embeddings using Anthropic voyage-3 API with 1024 dimensions. Support batch embedding in single API call.
**Code does:** Uses local `sentence-transformers` library (`SentenceTransformer` from `sentence_transformers`) instead of the Anthropic embedding API. Embedding dimensions come from config and may differ from 1024.
**Drift type:** behavioral
**Suggested mitigation:** Change spec
**Priority:** medium
**Rationale:** Switching from Anthropic voyage-3 to local sentence-transformers eliminates an API dependency, reduces cost, and removes latency for embedding generation. This is a deliberate architectural improvement but should be documented in the spec (or ideally an ADR).

---

### 13-REQ-6.3: Timeline plain text rendering

**Spec says:** Output is always plain text regardless of `use_color` value.
**Code does:** Only strips ANSI escapes when `use_color=False`. When `use_color=True`, ANSI codes in the data pass through to output.
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** low
**Rationale:** A recent commit (73848c1) added ANSI stripping for `use_color=False` but the spec says output should always be plain text. Either the spec should be updated to allow color, or the code should strip ANSI unconditionally.

---

### 15-REQ-2.2: Template section separator

**Spec says:** Template sections for coding role joined with `\n\n---\n\n` separator and `\n\n---\n\n## Context\n\n` before the context block.
**Code does:** Sections joined with `"\n\n".join(sections)` and context appended as `\n\n## Context\n\n{context}\n`. No `---` horizontal rules (`prompt.py` line 151).
**Drift type:** structural
**Suggested mitigation:** Needs manual review
**Priority:** low
**Rationale:** The `---` separators may improve prompt readability for the LLM but their absence is unlikely to affect behavior. Worth testing whether separators improve session quality.

---

### 16-REQ-3.1: Summary line merges blocked into failed

**Spec says:** Summary line shows `N failed` for tasks with failed status.
**Code does:** `failed = counts.get("failed", 0) + counts.get("blocked", 0)` -- blocked and failed are merged into a single "failed" count (`code.py` line 108).
**Drift type:** behavioral
**Suggested mitigation:** Get well spec
**Priority:** medium
**Rationale:** Users cannot distinguish between tasks that truly failed and tasks that are blocked on dependencies. These are semantically different statuses that warrant separate display.

---

## Unimplemented Requirements

None.

## Superseded Requirements

None.

## In-Progress Caveats

### 09_spec_validation (completion: 97%)

| Requirement | Status | Notes |
|-------------|--------|-------|
| (none) | | Task group 5 (Checkpoint) unchecked in tasks.md but all requirements are implemented. Likely a stale checkbox. |

### 17_init_claude_settings (completion: 0% -- stale)

| Requirement | Status | Notes |
|-------------|--------|-------|
| (none) | | All tasks.md checkboxes are unchecked but all 10 requirements are fully implemented. The tasks.md file is stale and does not reflect actual implementation status. Property tests are missing but integration tests exist. |

## Extra Behavior (Best-Effort)

- **`merge_commit()` in `git.py`**: Non-fast-forward merge function used as harvester fallback. Not specified in any spec.
- **`MemoryStore` class** in `store.py`: Dual-write store integrating DuckDB and embeddings. Serves as cross-cutting infrastructure across specs 05, 11, 12.
- **Causal extraction** functions in `extraction.py`: `enrich_extraction_with_causal`, `parse_causal_links`, `CAUSAL_EXTRACTION_ADDENDUM` -- from spec 13 integrated into spec 05's module.
- **`--dry-run` flag** on `agent-fox fix`: Allows generating fix specs without running sessions. Not in spec 08 requirements.
- **Agent Commits section** in standup formatting: Undocumented output section in `format_standup()`.
- **DuckDB/knowledge store wiring** in `code` command: Cross-cutting from spec 11.
- **`SessionTimeoutError`** naming: Spec 01 says `TimeoutError` but code uses `SessionTimeoutError` to avoid shadowing the Python builtin. Sensible deviation.
- **`KnowledgeStoreError`**: Additional exception class not listed in 01-REQ-4.2, added for later specs.

## Mitigation Summary

| Requirement | Mitigation | Priority |
|-------------|-----------|----------|
| 02-REQ-3.E1 | Change spec | low |
| 03-REQ-3.3 | Change spec | low |
| 03-REQ-7.E1 | Change spec | medium |
| 04-REQ-9.2 | Change spec | low |
| 05-REQ-4.1 | Change spec | medium |
| 08-REQ-3.1 | Change spec | low |
| 08-REQ-5.1 | Get well spec | medium |
| 08-REQ-5.2 | Get well spec | high |
| 09-REQ-8.1 | Get well spec | medium |
| 09-REQ-9.2 | Needs manual review | low |
| 12-REQ-2.1/2.2 | Change spec | medium |
| 13-REQ-6.3 | Get well spec | low |
| 15-REQ-2.2 | Needs manual review | low |
| 16-REQ-3.1 | Get well spec | medium |
