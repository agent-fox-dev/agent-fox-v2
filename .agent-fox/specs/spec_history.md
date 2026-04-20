# Spec History

A chronological summary of all archived specifications (115 specs across 100+
coding sessions). Each entry describes what was implemented, and notes when a
spec superseded, reverted, or modified another.

---

## Foundation & Core Engine (01-09)

| Spec | Summary |
|------|---------|
| 01 | **Core foundation** -- Project skeleton: CLI framework, configuration system, init command, error hierarchy, model registry, logging, terminal theme. |
| 02 | **Planning engine** -- Task graph builder from spec folders with dependency-aware topological sort and plan persistence. |
| 03 | **Session & workspace** -- Isolated git worktree execution, session management via claude-code-sdk, context assembly, work integration back to develop. |
| 04 | **Orchestrator** -- Deterministic orchestrator engine driving sessions in dependency order with retries, resource limits, and execution state persistence. |
| 05 | **Structured memory** -- Fact extraction from sessions into categories, JSONL storage, relevance selection for future context, human-readable summaries. |
| 06 | **Hooks, sync, security** -- Pre/post-session hooks, sync barriers for periodic checkpoints, hot-loading of new specs, command allowlist security. |
| 07 | **Operational commands** -- Three CLI commands: `status` (progress dashboard), `standup` (activity report), `reset` (failure recovery). |
| 08 | **Error autofix** -- Detect quality check failures, group by root cause, generate fix specs automatically, iterate until all checks pass. |
| 09 | **Spec validation** -- Static and optional AI-powered semantic analysis of specs, reporting findings at three severity levels before execution. |

## Platform & Persistence (10-11, 19, 28)

| Spec | Summary |
|------|---------|
| 10 | **Platform integration** -- PR-based workflows via GitHub integration with configurable gates. *Superseded by spec 19.* |
| 11 | **DuckDB knowledge store** -- DuckDB-backed persistence layer with versioned schema, SessionSink abstraction, graceful degradation. |
| 19 | **Git & platform overhaul** -- Robust develop branch setup, removed agent push instructions, wired platform layer into post-harvest, replaced `gh` CLI with GitHub REST API. *Supersedes spec 10.* |
| 28 | **GitHub issue REST API** -- Migrated GitHub issue operations from `gh` CLI to REST API via GitHubPlatform class (extends spec 19). |

## Knowledge & Intelligence (12-13, 42, 52, 90, 94-96, 104)

| Spec | Summary |
|------|---------|
| 12 | **Fox Ball (semantic oracle)** -- Queryable semantic oracle with vector embeddings and `agent-fox ask` command for grounded Q&A. |
| 13 | **Time vision** -- Temporal reasoning via causal link extraction, temporal graph queries, and predictive pattern detection from history. |
| 42 | **Knowledge context** -- Wired traverse_with_reviews() into session context, integrated RankedFactCache, extended findings to include drift and verification. |
| 52 | **Knowledge feedback loop** -- Session-derived facts and causal links flow into DuckDB with fallback extraction. |
| 90 | **Fact lifecycle** -- Deduplication on ingestion via embedding similarity, LLM-powered contradiction detection, age-based confidence decay with auto-supersession. |
| 94 | **Cross-spec vector retrieval** -- Semantic vector search across all facts using subtask descriptions as queries. *Superseded by spec 104.* |
| 96 | **Knowledge consolidation** -- Post-spec dedup, staleness verification via git, redundant fact merging, recurring pattern promotion, causal chain pruning. |
| 104 | **Adaptive retrieval** -- Unified retriever using Reciprocal Rank Fusion (RRF) to fuse keyword, vector, entity graph, and causal chain signals. *Supersedes spec 94.* |

## Entity Graph (95, 102, 107)

| Spec | Summary |
|------|---------|
| 95 | **Entity graph** -- Three DuckDB tables for code entity topology populated via tree-sitter static analysis and git diff. |
| 102 | **Multi-language entity graph** -- Extended entity graph to Go, Rust, TypeScript, JavaScript, Java, C, C++, Ruby with language analyzer framework. |
| 107 | **Additional language analyzers** -- Added C#, Elixir, Kotlin, Dart support to entity graph infrastructure. |

## CLI & UX (14-18, 23, 49, 59, 72, 76, 84)

| Spec | Summary |
|------|---------|
| 14 | **CLI banner** -- Fox ASCII art, version with coding model, and working directory displayed on every invocation. |
| 15a | **Session prompt** -- Overhauled coding session prompt builder; included test_spec.md in context, loaded templates from files. |
| 15b | **Standup formatting** -- Replaced Rich table output with plain-text indented format for standup reports, added per-task session breakdowns. |
| 16 | **Code command** -- `agent-fox code` CLI command wiring orchestrator engine to user-facing options and exit codes. |
| 17 | **Init Claude settings** -- Init command ensures `.claude/settings.local.json` has canonical permission entries for autonomous execution. |
| 18 | **Live progress** -- Live spinner during code execution showing task ID, tool activity, permanent lines for completion/failure. |
| 23 | **Global --json flag** -- Structured JSON input/output on all CLI commands, replacing per-command `--format` options. |
| 49 | **Dump command** -- `agent-fox dump` command to export memory or knowledge DB as Markdown or JSON. |
| 59 | **CLI separation & logging** -- Renamed `dump` to `export` and `lint-spec` to `lint-specs`; extracted backing modules; improved logging. |
| 72 | **Status active tasks** -- Shows currently in-progress tasks in `status` command output. |
| 76 | **Fix progress display** -- Real-time progress visualization for the `fix` command with phase/pass-level progress lines. |
| 84 | **Review output visibility** -- Logged raw review responses to JSONL, emitted audit events, added `agent-fox findings` CLI command. |

## Agent Archetypes & Routing (26, 30, 32, 46, 57, 62, 82, 88-89, 97-100)

| Spec | Summary |
|------|---------|
| 26 | **Agent archetypes** -- Introduced Coder, Skeptic, Verifier, Librarian, Cartographer with per-archetype model tiers, allowlists, templates, SDK protocol. |
| 30 | **Adaptive model routing** -- Speculative execution and quality validation for cost/speed trade-offs. *Superseded by spec 89.* |
| 32 | **Oracle archetype** -- Validates spec assumptions against codebase state before coding, filing drift findings to DuckDB. |
| 46 | **Test auditor** -- Auditor archetype to validate test code against test_spec.md contracts before implementation. |
| 57 | **Archetype model tiers** -- Flipped defaults (Coder to STANDARD, reviewers to ADVANCED), fixed tier ceiling to ADVANCED. *Superseded by spec 89.* |
| 62 | **Remove coordinator** -- Deleted never-activated coordinator archetype: registry entry, template, graph builder code, tests. |
| 82 | **Fix pipeline triage/reviewer** -- Replaced skeptic/verifier with triage and fix_reviewer archetypes for ad-hoc issue analysis. |
| 88 | **Fix coder archetype** -- Dedicated `fix_coder` archetype with issue-driven fix template instead of spec task groups. |
| 89 | **Simplify routing** -- Removed prediction pipeline from model routing while preserving escalation ladder and archetype defaults (~3,300 LOC removed). *Supersedes specs 30 and 57.* |
| 97 | **Archetype modes** -- Added mode infrastructure (ModeConfig, resolve_effective_config, mode field in task graph) without consolidating archetypes. |
| 98 | **Reviewer consolidation** -- Consolidated 5 review/fix archetypes (skeptic, oracle, auditor, fix_reviewer, fix_coder) into Reviewer and Coder with named modes. |
| 99 | **Archetype profiles** -- Readable editable profile files in `.agent-fox/profiles/` with 3-layer prompt assembly and custom archetype support. |
| 100 | **Maintainer archetype** -- New Maintainer archetype with hunt and extraction modes, absorbing triage archetype for nightshift hunt phase. |

## Review & Quality (22, 27, 37, 53-54, 67, 73-74, 83, 109)

| Spec | Summary |
|------|---------|
| 22 | **AI criteria fix** -- `lint-spec --fix` with `--ai` flag to automatically rewrite problematic acceptance criteria. |
| 27 | **Structured review records** -- DuckDB-backed structured records for Skeptic/Verifier output replacing file-based output. |
| 37 | **Confidence normalization** -- Unified confidence values from mixed string/float to float [0.0, 1.0] with DuckDB schema migration. |
| 53 | **Review persistence** -- Persisted review findings to DuckDB and added review-only mode for post-implementation sweeps. |
| 54 | **Quality gate complexity** -- Configurable post-session quality gate, enriched complexity feature vector (file count, cross-spec, language count, duration). |
| 67 | **Quality gate hunt category** -- Night-shift hunt category that auto-discovers quality checks and sends failures to AI for analysis. |
| 73 | **Finding consolidation critic** -- AI-powered critic for cross-category dedup, evidence validation, severity calibration, low-confidence dropping. |
| 74 | **Review parse resilience** -- Reduced review archetype parse failures from 57% to <10% via stricter prompts, fuzzy matching, retry logic. |
| 83 | **Lint spec coverage gaps** -- Six new lint-specs rules: missing execution paths, smoke tests, requirement count limits, task group ordering. |
| 109 | **AI fix pipeline wiring** -- Wired AI fix infrastructure into lint pipeline for auto-fixable findings (vague-criterion, implementation-leak, untraced-requirement). |

## Configuration & Infrastructure (33, 38-39, 55-56, 65-66, 68)

| Spec | Summary |
|------|---------|
| 33 | **Config generation** -- Programmatic `config.toml` generation from Pydantic models, idempotent re-init with smart merging. |
| 38 | **DuckDB hardening** -- Made DuckDB a hard requirement, removed optional patterns and silent degradation. |
| 39 | **Package consolidation** -- Consolidated `agent_fox/memory/` into `agent_fox/knowledge/`, DuckDB as primary read path, JSONL demoted to export-only. |
| 55 | **Claude-only commitment** -- Removed multi-provider abstraction, committed to Claude-only backend, documented via ADR. |
| 56 | **SDK feature adoption** -- Adopted Claude SDK features: turn limits, budget caps, fallback models, extended thinking for coder. |
| 65 | **Platform config overhaul** -- Removed auto_merge, simplified post-harvest to local git push, scoped platform config to issue operations. |
| 66 | **Config hot reload** -- Reload configuration at every sync barrier; skip if file unchanged; guard immutable fields. |
| 68 | **Config simplification** -- Simplified config template to essential options, created config-reference.md, set quality-first defaults. |

## Audit, Logging & Tracking (34, 40, 91-92, 103a)

| Spec | Summary |
|------|---------|
| 34 | **Token tracking** -- Comprehensive token tracking for all LLM calls, configurable pricing, per-archetype cost tracking in SessionRecord. |
| 40 | **Structured audit log** -- 20 event types, dual-write to DuckDB and JSONL, run ID correlation, `agent-fox audit` CLI command. |
| 91 | **Night-shift cost tracking** -- Wired sink_dispatcher and run_id into night-shift sessions for standard audit events and auxiliary AI call cost tracking. |
| 92 | **Transient audit reports** -- Moved audit reports to `.agent-fox/audit/` (gitignored), delete on PASS verdict and spec completion. |
| 103a | **Agent conversation trace** -- `--debug` flag captures full agent-model conversation as structured JSONL trace files. |

## Night Shift & Daemon (61, 70, 79, 81, 85, 106, 110)

| Spec | Summary |
|------|---------|
| 61 | **Night shift** -- Autonomous scheduled maintenance daemon with hunt categories: dependencies, TODOs, coverage, deprecated APIs, lint, dead code, docs. |
| 70 | **Watch mode** -- `--watch` flag keeps orchestrator running and polling for new specs instead of terminating. |
| 79 | **Hunt scan dedup** -- SHA-256 fingerprints in issue bodies to skip creation if matching open `af:hunt` issue exists. |
| 81 | **Night-shift issue-first status** -- Suppresses hunt scans while `af:fix` issues remain open; adds console progress output to night-shift. |
| 85 | **Daemon framework** -- Refactored night-shift into unified daemon with pluggable work streams (spec executor, fix pipeline, hunt scans, spec generator) sharing cost budget. |
| 106 | **Night-shift ignore** -- `.night-shift` ignore file (gitignore syntax) to control which files hunt scans exclude. |
| 110 | **Hunt dedup & ignore** -- Embedding-based similarity matching and `af:ignore` label mechanism for near-duplicate suppression and false positive handling. |

## Fix Pipeline & Escalation (31, 58, 71, 75, 82, 93)

| Spec | Summary |
|------|---------|
| 31 | **Auto improve** -- Iterative improvement passes combining analyzer-coder-verifier loop after quality checks pass, with oracle integration. |
| 58 | **Predecessor escalation** -- When retry_predecessor triggers, record failure on predecessor's escalation ladder so coder escalates. |
| 71 | **Fix issue ordering** -- Intelligent ordering and dependency detection in fix pipeline using AI batch triage and post-fix staleness checks. |
| 75 | **Timeout-aware escalation** -- Distinguishes timeout from logical failures; retries at same tier with increased max_turns before escalating model. |
| 82 | **Fix pipeline triage/reviewer** -- (See Archetypes section.) Replaced skeptic/verifier with triage and fix_reviewer archetypes. |
| 93 | **Fix branch push** -- Optional `push_fix_branch` config to push fix branches to origin after coder-reviewer loop passes. |

## Planning & Scheduling (20-21, 35, 41, 43, 50, 63, 69, 105)

| Spec | Summary |
|------|---------|
| 20 | **Plan analysis** -- Parallelism analysis, critical path computation, dependency quality checks, lint-spec --fix auto-correction. |
| 21 | **Dependency interface validation** -- AI-powered lint rule validating cross-spec dependency declarations against upstream design.md. |
| 35 | **Hard reset** -- `--hard` flag for full or partial project re-execution with git revision tracking and rollback logic. |
| 41 | **Duration task ordering** -- Duration-based task ordering using regression models, historical medians, and presets for optimal parallel scheduling. |
| 43 | **Project model** -- Aggregate spec analysis, critical path computation, file conflict detection, learned blocking thresholds from execution history. |
| 50 | **Reset spec** -- `agent-fox reset --spec <name>` to reset a single spec without affecting others or rolling back develop. |
| 63 | **Plan always rebuild** -- Removed plan cache; `plan` command always rebuilds task graph from `.specs/`; removed `--reanalyze` flag. |
| 69 | **Spec fair scheduling** -- Round-robin scheduling replacing alphabetical order to prevent starvation of newly hot-loaded specs. |
| 105 | **DB plan state** -- Migrated plan structure and execution state from file-based stores to DuckDB tables for transactional consistency. |

## Spec Generation & Validation (86, 108)

| Spec | Summary |
|------|---------|
| 86 | **Spec generator** -- Autonomous spec generation from GitHub issues labeled `af:spec` via multi-turn clarification comments and AI-driven document generation. |
| 108 | **Issue session summary** -- Automatic roll-up summary comments to originating GitHub issues when all spec task groups complete. |

## MCP & Tools (29)

| Spec | Summary |
|------|---------|
| 29 | **MCP server support** -- Token-efficient file tools (fox_outline, fox_read, fox_edit, fox_search) as in-process tools and MCP server. |

## Documentation & Init (24, 44, 47, 64, 101, 111)

| Spec | Summary |
|------|---------|
| 24 | **Dev scripts** -- Developer utility scripts directory with `dump_knowledge.py` for human-readable DuckDB inspection. |
| 44 | **Init AGENTS.md** -- Extended `agent-fox init` to scaffold `AGENTS.md` template from bundled static file. |
| 47 | **Init skills** -- Install bundled Claude Code skills into projects via `agent-fox init --skills`. |
| 64 | **Steering document** -- `.specs/steering.md` for persistent user-maintained directives injected into agent prompts at runtime. |
| 101 | **Knowledge onboarding** -- `agent-fox onboard` command: entity graph analysis, source ingestion, co-change extraction from git, code/docs analysis with LLM. |
| 111 | **Rich memory rendering** -- Enriched `docs/memory.md` with causal chains, entity links, supersession history, relative age, importance ordering from DuckDB. |

## Git & Worktree (45, 48, 51, 60, 78, 80)

| Spec | Summary |
|------|---------|
| 45 | **Robust merge** -- Merge lock for serializing develop-branch merges and merge-conflict agent fallback (replacing `-X theirs`). |
| 48 | **Platform issue abstraction** -- Abstracted issue operations behind platform protocol for GitHub/GitLab; reverted PR creation to local git. |
| 51 | **Sync barrier hardening** -- Parallel drain, worktree verification, bidirectional develop sync, multi-gate spec hot-load. |
| 60 | **End-of-run discovery** -- Check for new specs at end-of-run and hot-load them, continuing execution instead of terminating. |
| 78 | **Local-only feature branches** -- Stopped pushing feature branches to remote; only develop is pushed to origin. |
| 80 | **Worktree cleanup hardening** -- Ensure-then-act verification, "used by worktree" error handling, orphaned directory cleanup. |

## Prompt Caching & Cost (77)

| Spec | Summary |
|------|---------|
| 77 | **Prompt caching** -- Configurable cache policies (NONE/DEFAULT/EXTENDED) with shared helper injecting cache_control markers on all auxiliary API calls. |

## Cleanup & Removals (62, 103b)

| Spec | Summary |
|------|---------|
| 62 | **Remove coordinator** -- (See Archetypes section.) Deleted never-activated coordinator archetype. |
| 103b | **Remove hook runner** -- Removed unused hook runner infrastructure (~700 lines), relocated security module, modernized ConfigReloader return type. |

## Process & Scope (87)

| Spec | Summary |
|------|---------|
| 87 | **Coder scope waste** -- Documented problem where coder sessions discovered work was already implemented, wasting $3-4 per session; recommended pre-flight scope checks. |

## Bug Fix Specs

| Spec | Summary |
|------|---------|
| fix_01 | **Ruff format** -- Applied ruff auto-formatter to 43 Python files for 100% formatting compliance. |
| fix_02 | **Content block union** -- Fixed mypy `[union-attr]` errors by adding type-narrowing isinstance guard on content block union type. |
| fix_03 | **Spec lint fixes** -- Fixed subtask parser not matching N.V verification steps, false positives on completed specs, unvalidated alt dependency table format. |
| fix_04 | **Reset subtask checkboxes** -- Extended `reset --hard` to recursively reset all nested checkboxes within task groups. |
