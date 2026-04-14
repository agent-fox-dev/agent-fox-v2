# Chapter 02 — Architecture & Library Design

## Design Principles

Three principles govern every architectural decision in v3:

**Library-first.** Every capability is a Python module you can import and use independently. The CLI is a thin shell over the library. The daemon is a thin shell over the library. If you want to embed the planner into a CI pipeline, the knowledge store into a notebook, or a single archetype session into a custom script — you can, with no ceremony.

**Composition over configuration.** v2 had a three-level config hierarchy (global → project → archetype) with over 80 settings. v3 uses sensible defaults, project-level overrides, and composable building blocks. You configure what you need to change, and the system does the right thing for everything else.

**Agents are untrusted processes.** Agents run code, execute shell commands, and make HTTP requests. They are treated with the same caution you'd apply to a contractor who has terminal access: isolated workspace, no ambient credentials, auditable actions, bounded permissions.

## Package Structure

The project is organized as a Python monorepo with clear package boundaries. Each package has a defined public API and can be installed independently for library use, or together for the full system.

**`agent_fox.spec`** — Spec parsing, validation, auto-fix. Knows how to read `.specs/` directories, verify the five-artifact package is complete, parse task groups, resolve dependencies, and run the validation pipeline. No dependency on the execution engine. Useful standalone for CI linting of specs.

**`agent_fox.plan`** — Graph construction, topological sort, archetype injection, file impact analysis, critical path analysis, graph serialization. Takes parsed specs, produces a plan. No dependency on the execution engine. Useful standalone for plan visualization or custom dispatchers.

**`agent_fox.engine`** — The orchestrator. Dispatches sessions from a plan, manages the pool, handles results, retry, and escalation. Delegates merge integration to `agent_fox.workspace`. Depends on `spec`, `plan`, `harness`, `knowledge`, `workspace`, and `security`.

**`agent_fox.harness`** — The abstraction layer between the orchestrator and the actual coding agent process. Defines the `Harness` protocol (start session, send message, receive events, stop). Ships with a `ClaudeCodeHarness` implementation. Additional harnesses (Gemini CLI, OpenCode) can be contributed as plugins.

**`agent_fox.knowledge`** — The DuckDB-backed knowledge store. Fact storage, work item management, semantic search (ONNX-based embeddings), confidence scoring. Delivered in Phase 0 with fact CRUD, work item CRUD (create, query, triage, status transitions, fingerprint deduplication), findings, session summaries, metrics, and semantic search. Supersession chain management (Phase 2) and cq-compatible import/export (Phase 5) are added in later phases. No dependency on the execution engine. Useful standalone as a project knowledge base — a CI pipeline can create work items from linter output, or a script can query and sync them to an external tracker, without importing the nightshift daemon or the orchestrator.

**`agent_fox.workspace`** — Git worktree management, sandbox setup, merge cascade, branch lifecycle. Handles the physical isolation of agent work.

**`agent_fox.security`** — PuzzlePod integration (sandbox profile management, container lifecycle, credential configuration), secret leak detection, environment sanitization. Manages the mapping between agent-fox archetypes and PuzzlePod sandbox profiles.

**`agent_fox.nightshift`** — The autonomous maintenance daemon. Hunt categories, critic consolidation, deduplication, triage, fix pipeline. Depends on `engine`, `knowledge`, and `workspace`.

**`agent_fox.cli`** — The command-line interface. Thin layer that parses arguments and calls library functions. Designed for both human and agent consumption (JSON output mode, runtime schema introspection, machine-readable errors).

## Harness Abstraction

v2 was tightly coupled to the Claude Agent SDK. v3 introduces a harness protocol that decouples the orchestrator from the agent runtime. **Claude Code is the primary harness** — it provides the capabilities that the security model, context management, and reliability guarantees depend on. Other harnesses (Gemini CLI, OpenCode) can implement the protocol, but they operate with degraded guarantees where they lack equivalent capabilities. The protocol's value is not equal-footing multi-harness support — it is a clean separation of concerns that prevents a second v2-style SDK lock-in while being honest about what Claude Code provides.

### Protocol Shape

The `Harness` protocol defines five core operations:

| Operation | Parameters | Returns / Yields | Description |
|-----------|-----------|-----------------|-------------|
| `start` | system_prompt, task_prompt, tools, model_config | session_id | Start a new agent session |
| `stream` | session_id | async iterator of `Event` | Stream events from a running session |
| `inject` | session_id, message | — | Queue a message for the next turn (does not interrupt in-flight generation) |
| `stop` | session_id, reason | — | Stop a session gracefully (allow current turn to complete) or forcefully |
| `capabilities` | — | set of capability names | Declare which optional capabilities this harness supports |

The protocol is **async** — `stream` yields typed `Event` objects via an async iterator. The orchestrator consumes events as they arrive, records them to the transcript, and acts on them (e.g., monitoring turn count, detecting tool calls).

**Error conditions by operation:**

| Operation | Error | Meaning |
|-----------|-------|---------|
| `start` | `HarnessStartError` | Session could not be created (binary not found, container failed to launch, model unavailable) |
| `start` | `SessionLimitError` | Harness-level concurrency limit reached |
| `stream` | `SessionNotFoundError` | Session ID does not exist or has already ended |
| `inject` | `SessionNotFoundError` | Session ID does not exist or has already ended |
| `inject` | `SessionEndedError` | Session completed between the inject call and delivery |
| `stop` | `SessionNotFoundError` | Session ID does not exist (idempotent — stopping an already-stopped session is not an error) |

Recoverable errors (rate limits, transient API failures) are retried internally by the harness and surfaced as `error` events in the stream only if retries are exhausted. Non-recoverable errors (`HarnessStartError`, `SessionLimitError`) raise immediately and are handled by the engine's Decide phase.

The `tools` parameter is a list of tool definitions (name, description, parameter schema) that the agent may use. The set varies by archetype — Reviewers get read-only file tools, Coders get the full suite.

### Event Model

Events are typed objects with a `type` discriminator field:

| Event Type | Key Fields | Description |
|-----------|-----------|-------------|
| `assistant_message` | `content: str` | Text output from the agent |
| `tool_call` | `tool_name: str, arguments: dict, call_id: str` | Agent invokes a tool |
| `tool_result` | `call_id: str, output: str, is_error: bool` | Tool execution result |
| `status_update` | `status: str, detail: str or null` | Progress indicator (e.g., "thinking", "writing file") |
| `error` | `code: str, message: str, recoverable: bool` | Harness-level error (API failure, rate limit) |
| `session_end` | `reason: str, session_id: str` | Session completed or was stopped |

All events include a `timestamp` and `turn_number` field. A **turn** is one agent round-trip: the agent receives input (user message or tool results), generates one or more tool calls and/or an assistant message, and yields control back to the orchestrator. Each turn increments `turn_number` by 1. The orchestrator uses `turn_number` to track budget consumption. Recoverable errors (rate limits, transient API failures) are retried by the harness internally; non-recoverable errors bubble up to the orchestrator for assess/decide handling.

### Harness Implementation

**`ClaudeCodeHarness`** — Launches Claude Code as a subprocess and communicates via its JSON streaming protocol on stdout. Uses the Claude Code SDK's programmatic API for:
- Permission callback — gates tool execution per archetype profile
- Conversation parameter — enables session resume from checkpoint
- PreCompact hook — injects critical context before context window compaction

All archetypes use this harness. Archetype-specific behavior (read-only access, no shell, restricted tools) is enforced by the permission callback, not by switching harness implementations. A Reviewer session runs the same Claude Code subprocess as a Coder session — the callback simply denies write and shell tool calls. This keeps a single execution model, a single credential path, and a single set of capabilities across all archetypes.

**Capabilities declared:** `resume`, `structured_output`, `pre_compact_hook`, `effort_control` (four active; `fork_session` reserved for Phase 5).

### Capability Negotiation

Beyond the core operations, a harness declares which optional capabilities it supports. The orchestrator queries `capabilities()` once at harness initialization and adapts its behavior:

| Capability | When Present | When Absent | Used By |
|-----------|-------------|-------------|---------|
| `resume` | Retry resumes from checkpoint with error context injected | Retry starts a fresh session with error context prepended as "prior attempt" | Engine (decide phase) |
| `structured_output` | Harvest extracts typed JSON from agent output | Harvest parses freeform text with regex fallback | Reviewer, Maintainer (extraction) |
| `pre_compact_hook` | Orchestrator injects task description + unresolved findings before compaction | Compaction proceeds without injection; agent may lose task context | Engine (execute phase) |
| `effort_control` | Orchestrator sets thinking budget based on model tier (simple → low, advanced → high) | Model runs with default effort | Engine (prepare phase). ClaudeCodeHarness only. |
| `fork_session` | Orchestrator can spawn sub-agent sessions for targeted queries | Not available; deferred to Phase 5 | Not used in v3 (future) |

This avoids both extremes: fully opaque `harness_options` (where the orchestrator can't use features intelligently) and Claude-specific coupling (where other harnesses can't participate). A third-party harness declares what it supports and the orchestrator adapts.

### Degradation Impact

Capability negotiation allows graceful degradation, but "graceful" does not mean "equivalent." Three capabilities protect core guarantees. When absent, the degradation is significant:

| Missing Capability | What Breaks | Severity |
|-------------------|-------------|----------|
| `permission_callback` (via harness runtime) | The security model relies on callback-based tool authorization to enforce archetype permissions. Without it, a Reviewer can write files and a Verifier can access the network. The orchestrator falls back to prompt-only permission enforcement ("do not write files"), which is advisory, not enforceable. A misbehaving or jailbroken agent ignores prompt instructions. | **Security boundary degraded.** Prompt-only enforcement is defense-in-depth's weakest layer. |
| `pre_compact_hook` | When the context window fills, the runtime compacts older messages. Without the hook, the orchestrator cannot inject the task description and unresolved findings before compaction. The agent may lose its task context and produce off-topic or incomplete work. | **Quality degradation.** Longer sessions are more likely to drift from the task. |
| `resume` | Crash recovery and retry start fresh sessions with error context prepended as a "prior attempt" narrative. The agent re-reads the codebase, re-discovers the task state, and re-does work already committed. This wastes turns and money, and the agent may take a different (possibly worse) approach. | **Reliability and cost degradation.** Retries are slower, more expensive, and less predictable. |

**Practical implication:** "Harness-agnostic" means the protocol is open and the orchestrator adapts. It does not mean all harnesses produce equivalent results. Claude Code is the primary harness. Other harnesses are adapters with known limitations. The engine logs which capabilities are active at session start so degradation is visible, not silent.

**CMA as protocol validation.** Anthropic's Claude Managed Agents (CMA) — a hosted agent-as-a-service platform that runs Claude in cloud containers with built-in tool execution, multi-agent orchestration, and persistent memory stores — validates the harness protocol design. CMA's API maps cleanly to the protocol shape: `POST /sessions` → `start`, SSE stream → `stream`, `POST /events` → `inject`, `user.interrupt` → `stop`. CMA would declare `{resume, structured_output}` — no `pre_compact_hook` (CMA compacts internally), no `effort_control` (CMA has fast mode but not thinking budget control). This is the same degradation profile as other non-Claude-Code harnesses, and the existing degradation paths handle it. CMA is a plausible Phase 5 harness candidate (see ch 06, Claude Managed Agents analysis). The protocol exists to prevent lock-in — CMA's arrival demonstrates that the abstraction layer is justified.

**Positioning:** agent-fox's value is the spec-driven orchestration layer, not "running Claude in a container." CMA gives you agents; agent-fox gives you an engineering process built on agents. CMA's multi-agent is ad-hoc (the coordinator decides at runtime what to delegate); agent-fox's is planned (DAG-driven, dependency-aware, deterministic). CMA's memory is document-based text; agent-fox's knowledge is structured, scored, embedded, and injected with token-budget-aware context assembly. CMA has no concept of specs, planning, work items, night-shift, or merge cascade. As managed agent platforms mature and commoditize the "Claude in a sandbox" layer, agent-fox's differentiation becomes clearer, not weaker.

**Why PuzzlePod over Scion?** Scion is a container orchestrator that manages agent lifecycles — it is infrastructure, not a governance layer. PuzzlePod adds runtime policy evaluation and kernel-enforced sandboxing on top of Podman, which is exactly what agent-fox needs: containers with governance, not just containers. The Fork-Explore-Commit model aligns with agent-fox's session lifecycle, and the phantom token architecture replaces the need for a custom credential proxy. For teams that need Kubernetes-scale execution, a `ScionHarness` adapter remains a plausible future option.

## Credential Isolation

API keys never enter agent context. This is a hard constraint, not a best practice.

Credential isolation is handled by **PuzzlePod's phantom token architecture**:

**Phantom token lifecycle:**
1. At container startup, `agent_fox.security` requests a phantom token from PuzzlePod scoped to the domains required by the active harness and the configured Claude deployment target (Anthropic direct, Google Vertex AI, or AWS Bedrock).
2. The token is injected into the container environment using the appropriate provider variable(s): `ANTHROPIC_API_KEY=pt_...` for Anthropic direct, `GOOGLE_APPLICATION_CREDENTIALS` and `CLOUD_ML_REGION` for Vertex, or `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION` for Bedrock. PuzzlePod maps the phantom token to whichever credential set the provider requires.
3. Outbound HTTPS requests pass through `puzzle-proxy` (configured via `HTTPS_PROXY` inside the container), which resolves the phantom token to the real credential before forwarding. The proxy is domain-scoped: `api.anthropic.com` for Anthropic direct, `*-aiplatform.googleapis.com` for Vertex, `bedrock-runtime.*.amazonaws.com` for Bedrock.
4. Tokens are **ephemeral** — valid only for the lifetime of the container. They cannot be reused across sessions.
5. Requests to unscoped domains receive no credential injection (the phantom token is not forwarded, and the request proceeds without credentials).

This is stronger than a standalone proxy because PuzzlePod also runs DLP (data loss prevention) scanning on outbound requests — pattern matching and entropy detection to prevent credential exfiltration even if an agent constructs requests manually. Requests flagged by DLP are blocked and the agent receives a connection error. The violation is logged to the session transcript.

For teams with complex credential policies (multiple services, key rotation, audit trails), PuzzlePod supports multiple credential backends: encrypted local file, HashiCorp Vault, Kubernetes secrets, and OS keyring. OneCLI integration remains available as an alternative for teams already using it.

The fallback for `--no-sandbox` mode (see below): the orchestrator holds the real credentials and passes them via environment variables at process start (the appropriate set for the configured provider — `ANTHROPIC_API_KEY` for Anthropic direct, Vertex credentials for Vertex, AWS credentials for Bedrock). Weaker, but functional for local development.

The security model is defense-in-depth:

1. **Phantom tokens (default):** Agent never holds the key. Even a compromised agent process cannot exfiltrate credentials because it literally does not have them. Enforced by PuzzlePod's credential proxy inside the container.
2. **DLP scanning (always on in sandbox mode):** Outbound requests are scanned for credential patterns and high-entropy strings.
3. **Leak detection (always on):** The `agent_fox.security` module scans tool outputs, agent messages, and file contents for patterns that look like API keys, tokens, or PEM material. Detections are logged as warnings and optionally block the session.

## Process Sandboxing

Each agent session runs in an OCI container managed by Podman, with governance provided by PuzzlePod. This is the default and primary execution model on both macOS and Linux.

### Why PuzzlePod

Standard container security is static — configured at start time. AI agents are unpredictable at runtime (an LLM decides what to execute, which files to write, which network calls to make). PuzzlePod fills this gap with runtime governance: policy-evaluated changesets, kernel-enforced sandboxing that survives daemon crashes, and credential isolation via phantom tokens.

agent-fox does not need the full depth of PuzzlePod's security stack (BPF LSM, SELinux policies, seccomp USER_NOTIF mediation). It uses PuzzlePod as a sandbox runtime, leveraging the layers that matter for agent orchestration:

- **Fork-Explore-Commit model.** Each agent session runs in an OverlayFS branch. All writes go to an ephemeral upper layer. When the session completes, the changeset can be evaluated before being committed to the workspace. This maps naturally to agent-fox's "agent writes code, then we assess and merge" workflow.
- **Sandbox profiles per archetype.** PuzzlePod profiles define filesystem access, network mode, and resource limits. agent-fox defines three network modes, mapped to PuzzlePod profile configuration:

  | Network Mode | Behavior | Used By |
  |-------------|----------|---------|
  | `gated` | Outbound HTTPS via puzzle-proxy — agent tools can reach approved domains (package registries, APIs) | Coder, Reviewer |
  | `localhost` | Loopback only (127.0.0.1) for agent tool calls — test runners that bind to localhost work; outbound requests do not | Verifier |
  | `blocked` | No network for agent tool calls — tools run against local files only | Maintainer (hunt) |

  All modes maintain harness API access via puzzle-proxy. Network modes restrict what the agent's tool-level operations (shell commands, HTTP requests) can reach, not the harness ↔ Claude API communication channel.

  Archetype-to-profile mapping:

  - **Coder** → `gated` network, read-write workspace.
  - **Reviewer** → `gated` network (Claude Code subprocess needs API access; proxy domain-scoped to the Claude API endpoint only), read-only workspace. Pre-review mode has no shell execution; drift-review and audit-review modes have read-only shell access in an ephemeral sandbox (writes discarded).
  - **Verifier** → `localhost` network, read-only workspace with shell execution. "Read-only" means the Verifier's changeset is discarded after session completion — the Verifier cannot persist filesystem changes. The OverlayFS ephemeral layer allows test-framework artifacts (`__pycache__`, `.pytest_cache`, coverage files) to be written during execution.
  - **Maintainer** → Hunt mode: `blocked` network, read-only workspace, shell execution (local analysis tools only). Extraction mode: the orchestrator passes the transcript as session context and harvests structured facts from the output; the worktree is not mounted. The night-shift fix pipeline uses the Coder archetype and its sandbox profile, not the Maintainer.

  The `agent_fox.security` package provides a `profile_for_archetype(archetype, mode=None) -> SandboxProfile` function. The `mode` parameter is optional and archetype-specific: Maintainer accepts `"hunt"` or `"extraction"`; Reviewer accepts `"pre"`, `"drift"`, or `"audit"` (`"pre"` maps to the read-only-no-shell profile; `"drift"` and `"audit"` map to the read-only-with-shell profile). Coder and Verifier have no mode variants — `mode` is omitted or `None`. The engine calls this function; the security package returns the PuzzlePod profile configuration.
- **Credential isolation** via phantom tokens (see above).
- **Kernel-enforced containment.** Namespaces, Landlock, seccomp, and cgroups are enforced by the kernel. If the PuzzlePod daemon or agent-fox crashes, isolation survives.

### Platform Model

**Linux (primary):** Podman + PuzzlePod run natively. Full sandbox with OverlayFS, Landlock, seccomp, namespace isolation. Kernel >= 6.7 required for full Landlock support.

**macOS (development):** Podman runs containers in a Linux VM (Podman machine). PuzzlePod runs inside the VM. The orchestrator communicates with Podman via its remote API. This provides the same isolation model as Linux — no "degraded on macOS" asterisk.

### Workspace Integration

Each agent session gets its own git worktree (created by `agent_fox.workspace`) which is mounted into the container at `/workspace`. On macOS, worktrees are mounted into the Podman VM via virtiofs, then bind-mounted into the container. The worktree is on a dedicated feature branch. The OverlayFS branch sits on top of this mount — agent writes go to the ephemeral layer. On session success, agent-fox extracts the changeset from the OverlayFS upper directory and applies it as a git commit on the worktree branch. agent-fox then runs its merge cascade. PuzzlePod's Fork-Explore-Commit model provides the isolation; agent-fox manages the git operations.

### The `--no-sandbox` Escape Hatch

For local development iteration where full container isolation is unnecessary, `af run --no-sandbox` bypasses the container and runs the harness directly on the host. The agent still gets its own git worktree and a sanitized environment, but without container-level isolation. This is an explicit opt-in to reduced security, not the default, and should not be used for unattended execution.

**Environment sanitization in `--no-sandbox` mode:** The agent process inherits a sanitized copy of the host environment. All environment variables are stripped except an explicit allowlist: `PATH`, `HOME`, `TMPDIR`, `LANG`, `TERM`, and harness-specific variables (`ANTHROPIC_API_KEY` for Anthropic direct; `GOOGLE_APPLICATION_CREDENTIALS`, `CLOUD_ML_REGION` for Vertex; `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` for Bedrock). Credentials are passed via environment variables at process start (weaker than phantom tokens, but functional for local development). The working directory is set to the worktree root.

### PuzzlePod as a Dependency

PuzzlePod is a Rust binary, not a Python library. It is an external dependency installed alongside Podman (minimum versions: Podman >= 5.0, PuzzlePod >= 0.1).

**Dependency source:** agent-fox depends on a maintained fork at `https://github.com/agent-fox-dev/puzzlepod`, not directly on upstream (`LobsterTrap/puzzlepod`). The fork tracks upstream and is the vehicle for agent-fox-specific fixes and contributions. The contribution model:

- **Urgent fixes** (blocking Phase 1 validation, breaking bugs): fix in the fork, release from fork, PR upstream. agent-fox is never blocked on upstream maintainer response time.
- **Feature work** (agent-fox-specific profiles, integration improvements): develop in the fork, validate in agent-fox CI, PR upstream when stable.
- **Upstream tracking:** fork rebases on upstream releases. agent-fox pins to specific fork releases (not `main` tracking) to prevent unexpected breakage.

**Integration surface:** `agent_fox.security` communicates with PuzzlePod via:
- **CLI (`puzzled`)** — for sandbox lifecycle operations: create, start, stop, cleanup, commit.
- **REST API** — for credential configuration and profile management at runtime.

The `agent_fox.security` package wraps these interactions behind an internal `SandboxRuntime` interface so that a fallback to direct Podman (without PuzzlePod) can be implemented by swapping the runtime. This is the containment boundary if the fork/upstream relationship becomes untenable.

`af init` checks that both `podman` and `puzzled` are installed and that `puzzled` is running (not just installed). It reports their versions. If `puzzled` is not running, `af init` prints the platform-specific start command (`systemctl start puzzled` on Linux, `puzzled --daemon` on macOS). If either is missing, `af init` provides installation guidance with links to official documentation.

On macOS, `af init` also checks for a running Podman machine and offers to create one if absent.

## Agent-First CLI Design

The CLI serves two consumers: humans typing commands and agents invoking commands programmatically. Following the principles from Poehnelt's "Rewrite Your CLI for AI Agents":

**JSON by default when not interactive.** When stdout is a TTY, the CLI renders human-friendly output (tables, colors, progress bars). When stdout is piped or the `--output json` flag is set, every command emits structured JSON — one object per logical result, newline-delimited.

**Runtime schema introspection.** `af schema <command>` returns the JSON schema for a command's input and output. An agent can discover what parameters a command accepts without reading documentation.

**Machine-readable errors.** Errors are JSON objects with `code`, `message`, and `context` fields. The CLI never exits with just a human-readable string to stderr.

**Self-describing help.** `af help --format json` returns the full command tree with descriptions, parameter schemas, and examples. This can be injected into an agent's system prompt as a skill definition.

**Idempotent where possible.** `af plan` and `af validate` produce the same output given the same inputs. Commands that modify state (like `af run`) are clearly marked as such.

The CLI is organized around the user workflow:

- `af init` — Initialize a project (create `.agent-fox/` config, `.specs/` directory). `af init --profiles` copies the default archetype profiles into `.agent-fox/profiles/` for editing.
- `af spec new <name>` — Scaffold a new spec directory with templates for all five artifacts.
- `af validate [<spec>]` — Run validation on one or all specs.
- `af run [<spec>]` — Execute specs. This is the main entry point. Implicitly validates and plans before dispatching — the user never has to run a separate planning step.
- `af plan [<spec>]` — Inspect the task graph without executing. Builds the DAG from specs, persists to `.agent-fox/plan.json`, and exits. This is a diagnostic/inspection tool, not a required workflow step. Useful for: previewing what `af run` will do before spending money on agent sessions, CI pipelines that visualize the plan, and debugging graph construction issues.
- `af status` — Report current execution state, in-flight sessions, cost, knowledge stats. `--work-items` includes a work item summary.
- `af resume [--skip <node-id>]` — Resume dispatch after circuit breaker cooldown or merge-blocked state. `--skip` marks a node as `blocked` and bypasses it.
- `af abort` — Terminate the current plan execution. In-flight sessions are stopped gracefully.
- `af cost` — Detailed per-session cost reporting by spec, archetype, and model tier.
- `af knowledge query <topic>` — Search the knowledge store.
- `af knowledge export-memory` — Regenerate `PROJECT_MEMORY.md` from current knowledge state.
- `af knowledge reindex` — Re-embed all records after changing the embedding model.
- `af work-item create` — Manually create a work item (title, description, affected files, severity).
- `af work-item list` — List work items (filterable by status, severity, category).
- `af nightshift` — Start the autonomous maintenance daemon.
- `af nightshift list` — List work items (filterable by status, severity, category).
- `af nightshift approve <id>` — Approve a work item for fixing.
- `af nightshift triage` — Prioritize and review pending work items.
- `af nightshift sync-issues` — One-way push of work items to GitHub Issues.

## Configuration

Project configuration lives in `.agent-fox/config.toml`. The file is optional — the system runs with defaults if absent.

Configuration is flat and focused. The following table lists the critical keys with their types and defaults:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `project.name` | string | directory name | Project name for reporting |
| `project.develop_branch` | string | `"develop"` | Branch that agents merge into |
| `project.specs_dir` | string | `".specs"` | Path to specs directory |
| `credentials.provider` | string | `"anthropic"` | Claude deployment target (`anthropic`, `vertex`, `bedrock`) |
| `credentials.mode` | string | `"phantom"` | Credential mode (`phantom`, `ephemeral`, `onecli`) |
| `execution.max_parallel` | int | `4` | Maximum concurrent sessions |
| `execution.turn_budget` | int | `200` | Default turn budget per session |
| `execution.token_budget` | int | `500000` | Default token budget per session |
| `execution.cost_ceiling_usd` | float | none | Project-wide cost ceiling in USD (no enforcement if absent) |
| `execution.cost_warning_ratio` | float | `0.8` | Warning at this fraction of ceiling |
| `knowledge.embedding_model` | string | `"gte-small"` | ONNX embedding model name |
| `knowledge.embedding_device` | string | `"auto"` | Execution provider (`auto`, `cpu`, `coreml`, `cuda`) |
| `knowledge.similarity_threshold` | float | `0.7` | Minimum similarity for search results |
| `knowledge.memory_size_cap` | int | `4000` | Token cap for PROJECT_MEMORY.md |
| `nightshift.enabled_categories` | string[] | all eight | Which hunt categories to run |
| `nightshift.hunt_interval_hours` | float | `4.0` | Hours between hunt scans |
| `nightshift.fix_interval_minutes` | float | `15.0` | Minutes between fix checks |
| `nightshift.cost_ceiling_usd` | float | 50% of project ceiling | Night-shift cost ceiling |
| `nightshift.mode` | string | `"manual"` | Fix approval mode (`auto`, `manual`) |
| `execution.partial_advance_threshold` | int | `2` | Max major findings before partial is treated as failure |
| `execution.stuck_session_timeout` | int | `600` | Seconds of inactivity before killing a session |
| `execution.circuit_breaker_threshold` | int | `3` | Consecutive failures before halting dispatch |
| `execution.spec_cost_ceiling_usd` | float | none | Per-spec cost ceiling in USD |
| `execution.checkpoint_turn_interval` | int | `20` | Checkpoint every N turns |
| `execution.checkpoint_time_interval` | int | `300` | Checkpoint every N seconds |
| `execution.sync_barrier_interval` | int | `1800` | Seconds between sync barrier checks |
| `execution.quality_gate_command` | string | none | Shell command that must exit 0 for success (e.g., `make check`) |
| `execution.retry_attempts_per_tier` | int | `2` | Retry attempts at each model tier before escalating |
| `knowledge.injection_token_budget` | int | `2000` | Max tokens of knowledge injected into context |
| `merge.ai_resolution_enabled` | bool | `false` | Enable AI-assisted merge conflict resolution (Phase 5) |

Per-archetype overrides are nested under `archetype.<name>.*`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `archetype.<name>.model_tier` | string | adaptive | Force model tier (`simple`, `standard`, `advanced`) |
| `archetype.<name>.turn_budget` | int | `200` | Override turn budget for this archetype |
| `archetype.<name>.token_budget` | int | `500000` | Override token budget for this archetype |
| `archetype.reviewer.instance_count` | int | `1` | Number of parallel Reviewer instances per mode |
| `archetype.reviewer.pre_review_enabled` | bool | `true` | Enable pre-review injection |
| `archetype.reviewer.drift_review_enabled` | bool | `true` | Enable drift-review injection (conditional on design.md) |
| `archetype.reviewer.audit_review_enabled` | bool | `true` | Enable audit-review injection |
| `archetype.reviewer.promote_findings` | bool | `false` | Promote audit-review findings beyond current spec scope to work items |

v3 does not support global (user-level) configuration. Project config is the only level. This eliminates the "which config is active?" confusion from v2. If you want shared settings across projects, use a template that you copy.

Credential configuration (API keys, credential backends like Vault or OS keyring) is managed through PuzzlePod's own system-level configuration, not through agent-fox's project config. agent-fox's project config specifies which credential *mode* to use, not the credentials themselves.

## Tech Stack & Dependencies

### Host Toolchain

The following tools must be present on the developer's machine (or CI host) before agent-fox can build and run. `af init` checks for all of them and reports missing or version-incompatible entries.

| Tool | Minimum Version | Purpose |
|------|-----------------|---------|
| Python | 3.12+ | Runtime for the agent-fox library and CLI |
| uv | latest | Package management, virtualenv creation, lockfile resolution. The only supported installer — do not use pip, poetry, or setuptools directly |
| Make | GNU Make 4.0+ | Build automation. The project ships a `Makefile` with targets for common workflows (`make test`, `make lint`, `make build`, `make container`) |
| Podman | 5.0+ | OCI container runtime. Docker is not used — Podman provides rootless, daemonless containers compatible with the PuzzlePod governance model |
| Rust | stable (1.75+) | Required to build PuzzlePod from source. Pre-built binaries are available for common platforms, but Rust + Cargo must be present for source installs or development |
| Cargo | (ships with Rust) | Rust package manager. Used to compile and install PuzzlePod (`puzzled`) |

**Why uv, not pip.** uv is faster, handles lockfiles natively, and produces reproducible environments without `pip-tools` ceremony. All dependency resolution goes through `uv lock` / `uv sync`. The `pyproject.toml` is the single source of truth for Python dependencies.

**Why Make.** Make is universal, available on every Unix system, and requires zero installation on Linux. It provides a thin, stable interface over the actual build commands — a new contributor runs `make test` without knowing whether that invokes `uv run pytest` or something else. Makefiles are not clever; they are obvious.

### Container Toolchain

agent-fox builds and runs OCI containers via Podman. The container layer uses the following conventions:

**Containerfile, not Dockerfile.** All container definitions use `Containerfile` (the OCI-standard filename). Do not use `Dockerfile`. Podman supports both, but the project standardizes on `Containerfile` to avoid implying a Docker dependency.

**Red Hat UBI 10 Minimal base image.** Agent session containers are built from `registry.access.redhat.com/ubi10/ubi-minimal`. UBI (Universal Base Image) Minimal provides a small, hardened, freely redistributable base with `microdnf` for package installation. It avoids the supply-chain concerns of community images and the size bloat of full OS images. Specific rationale:

- **Small footprint.** UBI Minimal is ~100MB compressed. Agent containers should start fast and consume minimal disk.
- **Security posture.** Red Hat maintains CVE patching on a predictable cadence. The base image is scanned and signed.
- **License clarity.** UBI is free to use and redistribute without a Red Hat subscription.
- **RHEL ecosystem compatibility.** Packages installed via `microdnf` come from the RHEL repository, avoiding ABI mismatches.

The `Containerfile` installs only the packages required for the agent archetype's workload — Python, git, and archetype-specific tools. No kitchen-sink images.

**PuzzlePod** (>= 0.1, from `agent-fox-dev/puzzlepod` fork) — Rust binary providing runtime governance on top of Podman. See the [Process Sandboxing](#process-sandboxing) section for details. On macOS, Podman runs containers inside a Linux VM (Podman machine); PuzzlePod runs inside the VM.

### Python Dependencies

Python 3.12+ is required. The dependency footprint is deliberately small:

- `duckdb` — Knowledge store. Embedded, in-process, no server.
- `onnxruntime` — Embeddings for semantic search. Supports CoreML (Apple Silicon), CUDA (Linux GPU), and CPU execution providers. No torch dependency.
- `gitpython` — Worktree management.
- `claude-code-sdk` — Programmatic control of Claude Code as a subprocess. Used by `ClaudeCodeHarness` for session management, permission callbacks, and event streaming. Claude Code handles API communication internally, including Anthropic direct, Vertex AI, and Bedrock transports — agent-fox does not need the `anthropic` Python SDK as a direct dependency.
- `click` — CLI framework.
- `tomli-w` — TOML writing. Reading uses `tomllib` from the standard library (Python 3.11+).
- `pydantic` — Data validation for specs, plans, and knowledge units.

All dependencies are declared in `pyproject.toml` and locked via `uv lock`. Install with `uv sync` (development) or `uv pip install agent-fox` (library use).

The default embedding model is `gte-small` (384-dimensional, ~67MB ONNX artifact) that runs efficiently on Apple Silicon via CoreML or on Linux via CPU/CUDA. No torch required for the default path. Users who need higher-quality retrieval can install a full torch-backed model via `uv pip install agent-fox[knowledge-torch]`.

---

*Previous: [01 — Spec System](./01-spec-system.md)*
*Next: [03 — Archetypes, Planning & Execution](./03-execution.md)*
