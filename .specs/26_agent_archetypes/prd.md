# PRD: Agent Archetypes

> Source: [GitHub Issue #114](https://github.com/agent-fox-dev/agent-fox-v2/issues/114)

## Overview

agent-fox currently runs every task with the same agent persona: the Coder,
hardcoded against the Claude Agent SDK. This spec introduces two complementary
changes, delivered in two sequential implementation phases:

1. **SDK abstraction layer** (Phase A) — an `AgentBackend` protocol that
   encapsulates all Claude SDK interaction behind a narrow interface. This is
   a low-risk mechanical refactor: extract existing code behind a protocol,
   ship the `ClaudeBackend` adapter, rewire imports. It can be merged and
   validated independently before Phase B begins.

2. **Agent archetypes** (Phase B) — specialized agent configurations (system
   prompt, model tier, security allowlist) that the orchestrator assigns to
   task graph nodes based on metadata. Builds on the clean session interface
   from Phase A.

Phase A and Phase B are documented in a single spec because they share a
design surface (the session execution layer), but they are **sequenced for
independent delivery and independent risk**. Phase A is infrastructure;
Phase B is feature work.

## Problem Statement

Every task group — whether it's writing code, reviewing a spec, updating
documentation, or mapping architecture — gets the same coding agent with the
same system prompt. This means:

1. **No specialization.** The Coder prompt includes workflow steps (git-flow,
   commit conventions, quality gates) that are irrelevant for review or
   documentation tasks. Irrelevant instructions waste context window and can
   confuse the agent.
2. **No quality gate before execution.** There is no mechanism for a review
   agent to challenge a spec's assumptions before the Coder starts
   implementing. Errors caught late in execution are expensive.
3. **No cost optimization.** Review and documentation tasks don't need the most
   expensive model tier. Today everything runs on ADVANCED because there's no
   per-task model selection.
4. **No post-implementation verification.** Once the Coder finishes, there is
   no independent check that the output actually conforms to the spec's
   acceptance criteria, passes quality standards, or has adequate test
   coverage. Bugs slip through because the same agent that wrote the code is
   the only one that "reviewed" it.
5. **No read-only enforcement.** An agent reviewing a spec should not be able
   to modify source code. Today, all sessions share the same bash allowlist.
6. **Hard SDK coupling.** All session execution is hardcoded against the Claude
   Agent SDK in `session.py` (5 SDK-specific types imported). Unit tests must
   mock these types individually. If the SDK API changes, or if a different
   agent runtime is needed, the session layer requires a rewrite.

## Goals

- Define an **`AgentBackend` protocol** that encapsulates all SDK interaction
  behind a single async interface (`execute()` yielding canonical messages)
- Extract all Claude SDK code into a **`ClaudeBackend` adapter** that
  implements the protocol — no SDK imports outside the adapter module
- Refactor `session.py` to depend only on the protocol, not on SDK types
- Define an **archetype registry** that maps archetype names to prompt
  templates, model tiers, and optional allowlist overrides
- Add an `archetype` field to task graph nodes (`Node` dataclass) so the
  planner can assign archetypes during plan generation
- Replace the hardcoded `_ROLE_TEMPLATES` dict — `build_system_prompt()`
  resolves archetypes from the registry
- Update `NodeSessionRunner` to read the archetype from node metadata and
  select the correct prompt, model, and allowlist
- Ship five archetypes: **Coder** (existing behavior), **Skeptic** (spec
  review), **Verifier** (post-implementation quality and spec conformance),
  **Librarian** (documentation), **Cartographer** (architecture mapping)
- Provide archetype enable/disable toggles in `config.toml` so users can
  control which archetypes the planner is allowed to assign
- Support **multi-instance execution** for review archetypes (Skeptic,
  Verifier) to produce converged opinions from independent runs
- File Skeptic and Verifier findings as **GitHub issues** with idempotent
  create-or-update semantics for human visibility and resolution tracking
- Ensure backward compatibility: plans without archetype metadata default to
  the Coder

## Non-Goals

- **Scheduling and triggers.** "Night shift" scans, cron-based activation, and
  event-driven triggers (e.g., "run Security Shaman on flagged tasks") are
  future concerns. This spec only provides the framework and the archetypes.
- **Additional archetypes beyond the initial five.** Security Shaman,
  Performance Oracle, and Archaeologist require detection systems (vulnerability
  scanners, profiling tools, code familiarity scoring) that do not exist yet.
  The framework makes adding them trivial; implementing them is deferred.
- **Implementing alternative backends.** This spec extracts the `AgentBackend`
  protocol and ships the `ClaudeBackend` adapter. Actually implementing a
  LangChain or AWS Strands backend is a future spec that builds on this
  foundation. The protocol is designed to accommodate them based on the
  research in spec 25 (RFC), but this spec does not ship them.

## Key Decisions

- **Archetypes are data for prompt and model selection.** An archetype's
  *identity* — template files, model tier, allowlist, injection mode — is
  pure configuration. Adding a new archetype with standard execution semantics
  means adding a template file and a registry entry: no new Python classes.
  However, archetypes with custom execution semantics (blocking-threshold
  evaluation, convergence logic, GitHub issue filing) require
  archetype-specific code in addition to the registry entry. The Skeptic and
  Verifier are examples: their prompt and model selection is data-driven, but
  their post-session behavior is code.

- **Plan nodes carry archetype metadata.** The `Node` dataclass gets an
  `archetype: str` field (default: `"coder"`) and an `instances: int` field
  (default: 1). The coordinator agent sets these during planning based on task
  type. The orchestrator reads them and passes them to the session lifecycle.
  This keeps archetype assignment in the planning phase (where the LLM has
  context) and out of the deterministic execution loop.

- **Existing role system is replaced.** The hardcoded `_ROLE_TEMPLATES` dict
  in `prompt.py` (which maps `"coding"` to `["coding.md", "git-flow.md"]` and
  `"coordinator"` to `["coordinator.md"]`) is deleted. Its entries migrate into
  the archetype registry as data: `"coder"` maps to templates
  `["coding.md", "git-flow.md"]`, model tier `ADVANCED`, and the global
  allowlist. The `"coordinator"` also becomes a registry entry (templates
  `["coordinator.md"]`, model tier `STANDARD`). The coordinator is in the
  registry for template resolution, but it is **not part of the task-facing
  roster** — it cannot be assigned to task nodes. It is only used by the
  planning engine. `build_system_prompt()` resolves templates from the registry
  by archetype name instead of a hardcoded dict.

- **Per-archetype model tiers.** Each archetype declares a default model tier
  (e.g., `"ADVANCED"` for the Coder, `"STANDARD"` for the Skeptic). The
  `ModelConfig` section of `config.toml` is extended with per-archetype
  overrides. This allows cost-conscious users to run review archetypes on
  cheaper models.

- **Per-archetype allowlist overrides.** The Skeptic archetype should be
  read-only: it can run `ls`, `cat`, `git log`, `git diff`, but not `git
  commit`, `rm`, or build commands. Each archetype can declare an allowlist
  override; if absent, the global `security.bash_allowlist` applies.

- **The Skeptic is a plan node, not a hook.** The Skeptic runs as a regular
  task graph node (e.g., `03_session_and_workspace:0` with archetype
  `"skeptic"`). It uses a worktree, produces a review file, and is harvested
  like any other session. This avoids a new execution path and lets the
  orchestrator handle retries, cost tracking, and state persistence for
  Skeptic sessions identically to Coder sessions.

- **The Skeptic informs, not blocks (by default).** The Skeptic's output is a
  set of questions and observations filed as a GitHub issue (linked to the
  spec). The Skeptic node always completes successfully — its successor (the
  Coder) receives the Skeptic's findings as additional context in its prompt.
  This means execution continues without human intervention. Only when the
  Skeptic's findings exceed a configurable severity threshold (e.g., > N
  critical findings) does the Skeptic mark itself as `"blocked"`, which
  cascade-blocks the downstream Coder via the existing orchestrator logic.
  This threshold is conservative by default (high — most reviews pass
  through) so that the Skeptic acts as an advisory layer, not a bottleneck.

- **Multi-instance convergence.** A plan node can specify `instances: N`
  (default: 1) to run N independent sessions of the same archetype in
  parallel. The orchestrator dispatches all N instances, collects their
  outputs, and a convergence step merges the results. Convergence is
  archetype-specific:
  - **Skeptic:** Union all findings. Deduplicate by exact match on the
    finding's `(severity, description)` tuple (normalized: lowercased,
    whitespace-collapsed). A critical finding only counts toward the blocking
    threshold if it appears in >= ceil(N/2) instance outputs.
  - **Verifier:** Majority vote on the overall verdict. PASS if >= ceil(N/2)
    instances say PASS. Individual per-requirement findings are unioned.
  - **Coder:** Single-instance only. `instances > 1` is clamped to 1 with a
    warning (multiple Coders would produce conflicting code changes).
  The convergence logic runs no LLM calls. It is deterministic string
  manipulation and counting. The `instances` field on the `Node` dataclass
  defaults to 1 for backward compatibility.

- **Parallel sibling archetypes at the same stage.** Multiple different
  archetypes can run at the same plan stage as independent siblings. After the
  Coder finishes, both a Verifier and a Security Shaman (future) can execute
  concurrently — they share the same predecessor but have no dependency on
  each other. This is a natural consequence of the task graph model: sibling
  nodes with the same parent are eligible for parallel dispatch. No new
  orchestrator logic is needed for this. The graph builder injects all enabled
  post-coder archetypes as siblings of the last Coder group. Each archetype
  in the registry declares its `injection` mode to control how it enters the
  graph (see "Injection Modes" below).

- **Verifier failure requires new orchestrator logic.** When a Verifier node
  fails (verdict: FAIL), the desired behavior is to re-run the *Coder*
  predecessor with the Verifier's report as error context, then re-run the
  Verifier. This is **not** the existing retry mechanism — standard retry
  re-runs the failed node itself, not a predecessor. This spec introduces a
  new orchestrator capability: **retry-predecessor-on-downstream-failure**.
  When a `post_coder` node with `retry_predecessor = true` fails:
  1. The orchestrator resets the predecessor Coder node to `pending`.
  2. It attaches the Verifier's failure report as `previous_error` on the
     Coder node.
  3. The Coder re-runs, addressing the Verifier's findings.
  4. On Coder success, the Verifier re-runs automatically (it depends on the
     Coder).
  5. This cycle repeats up to `max_retries` times. After exhaustion, the
     Verifier node is blocked per normal rules.
  This is explicitly new orchestrator behavior. It is limited to nodes with
  `retry_predecessor = true` in the registry (currently only the Verifier).

- **SDK abstraction is Phase A.** Refactoring the session layer to extract
  the SDK coupling is done first as an independent, low-risk deliverable.
  The `AgentBackend` protocol from spec 25 (RFC) is incorporated here; spec
  25 is superseded. The protocol design is informed by the spec 25 research
  into LangChain and AWS Strands APIs, ensuring the interface will
  accommodate future backends without redesign. Phase A can be merged and
  validated before Phase B (archetypes) begins.

- **Backward compatibility via defaults.** Existing `plan.json` files without
  `archetype` fields are valid — every node defaults to `"coder"`. Existing
  `config.toml` files without `[archetypes]` sections use defaults (only Coder
  enabled). No migration required.

## Archetype Assignment

How does the system decide which archetype runs for each task? Assignment uses
three layers with clear priority.

### Layer 1: Deterministic Injection (Graph Builder)

When `build_graph()` constructs the task graph from `tasks.md` files, it
applies automatic archetype injection based on `config.toml` toggles:

1. **Pre-coder injection.** If `archetypes.skeptic = true`, the graph builder
   inserts a group-0 node with `archetype="skeptic"` at the start of each
   spec, before the first task group. This node depends on nothing within the
   spec (it's the root) and the first real task group (group 1) depends on it.
   The Skeptic node's `instances` field is set from
   `archetypes.instances.skeptic` (default: 1).

2. **Post-coder injection.** The graph builder inserts **one node per enabled
   post-coder archetype** after the last Coder group of each spec. All
   injected nodes depend on the same predecessor (the final implementation
   group) and are **siblings** — independent of each other, eligible for
   parallel execution.

   - If `archetypes.verifier = true`, a Verifier node is injected.
   - Future archetypes with `injection = "post_coder"` in the registry are
     also injected when enabled (e.g., Security Shaman).

   Each injected node gets its `instances` count from
   `archetypes.instances.{name}`. Since sibling nodes share no edges between
   them, the orchestrator's existing parallel dispatch executes them
   concurrently (subject to the `parallel` config limit).

   Example graph for a spec with 4 Coder groups, Verifier enabled, and a
   future Security Shaman enabled:

   ```
   skeptic:0 → coder:1 → coder:2 → coder:3 → coder:4 ─┬→ verifier:5
                                                         └→ shaman:6
   ```

   Both `verifier:5` and `shaman:6` depend on `coder:4` and can run in
   parallel. Neither depends on the other.

3. **Default archetype.** All task groups parsed from `tasks.md` default to
   `archetype="coder"` unless overridden.

This layer is fully deterministic — no LLM calls. It handles the common
structural patterns (review-before, verify-after) automatically.

### Layer 2: Coordinator Annotation (LLM-assisted)

The coordinator agent, which already analyzes specs and produces cross-spec
dependencies, is extended to also annotate archetype assignments. The
coordinator's prompt is updated to include the list of enabled archetypes
and their descriptions. When it produces the dependency output, it can
additionally output archetype overrides:

```json
{
  "archetype_overrides": [
    {"node": "03_session:3", "archetype": "librarian", "reason": "task 3 is 'Checkpoint - update documentation'"},
    {"node": "05_memory:4", "archetype": "cartographer", "reason": "task 4 is 'Update ADRs for memory architecture'"}
  ]
}
```

The graph builder applies these overrides after constructing the base graph.
If an override references a disabled archetype, the override is ignored with
a warning.

This layer handles **context-sensitive** assignment that requires understanding
task content — distinguishing "write documentation" from "write code" based on
the task title and body.

**Misassignment guardrails.** The coordinator can misassign archetypes (e.g.,
labeling a coding task as `"librarian"`). Mitigations:

- **Non-coding archetypes cannot commit code changes.** The Librarian and
  Cartographer templates instruct the agent to produce documentation only.
  If a coding task is misassigned, the session will likely fail (no code
  changes produced), triggering a retry with the default Coder archetype.
- **Log all overrides.** Every coordinator annotation is logged at INFO level
  with the reason, making misassignments visible in the execution log.
- **`tasks.md` directives always win.** A spec author can correct a bad
  coordinator annotation by adding an explicit directive.

### Layer 3: Explicit Annotation (tasks.md)

Spec authors can explicitly set an archetype in `tasks.md` using a visible
tag on the task group line:

```markdown
- [ ] 3. Update architecture docs [archetype: cartographer]
  - [ ] 3.1 Generate dependency graph
  - [ ] 3.2 Update ADR for new module structure
```

The task parser extracts the `[archetype: X]` tag and sets it on the
`TaskGroupDef`. This takes **highest priority** — it overrides both the
graph builder defaults and coordinator annotations.

The tag uses square brackets (not HTML comments) so it is **visible in
rendered markdown**. A human reading the spec can immediately see which
archetype is assigned.

### Priority Order

When multiple layers assign different archetypes to the same node:

1. **Explicit `tasks.md` tag** (highest priority — human intent)
2. **Coordinator annotation** (LLM-assisted context understanding)
3. **Graph builder default** (deterministic rules)

The graph builder logs the final archetype assignment for each node at INFO
level for transparency.

## Injection Modes

Each archetype in the registry declares an `injection` mode that controls how
it enters the task graph. This is about *how the archetype is assigned to
nodes*, not where in the graph it runs:

| Mode | Meaning | Example |
|------|---------|---------|
| `auto_pre` | Graph builder auto-injects before first Coder group | Skeptic |
| `auto_post` | Graph builder auto-injects after last Coder group (as sibling) | Verifier, future Security Shaman |
| `manual` | Only assigned via coordinator annotation or `tasks.md` tag | Librarian, Cartographer |

An archetype with `injection = "manual"` is never auto-injected; it must be
explicitly assigned. An `auto_post` archetype is auto-injected *and* can also
be manually assigned to other nodes if desired (e.g., a Verifier mid-spec).

The Coder has no injection mode — it is the default archetype for all
`tasks.md` groups.

## The Roster

### The Coder (existing behavior, refined)

**Purpose:** Implement features, fix bugs, write tests.
**Injection:** Default for all `tasks.md` groups.
**When:** Feature task groups, test-writing task groups, all current behavior.
**Template:** `coding.md` + `git-flow.md` (unchanged).
**Model tier:** ADVANCED (default).
**Allowlist:** Global default (full coding allowlist).

### The Skeptic

**Purpose:** Challenge specs, find ambiguities, question assumptions, identify
missing edge cases. Files findings as a GitHub issue and produces a review
document that is injected as context into the successor Coder session.
**Injection:** `auto_pre` — injected as group 0, before the first Coder group.
**When:** Before a spec's first implementation group, if enabled.
**Template:** New `skeptic.md` template. Instructs the agent to read the spec's
PRD, requirements, design, and test spec, then produce a structured review
with findings categorized by severity (critical, major, minor, observation).
**Model tier:** STANDARD (default — review doesn't need the most capable model).
**Allowlist:** Read-only override (`ls`, `cat`, `git log`, `git diff`,
`git show`, `wc`, `head`, `tail`). Cannot modify files via bash; file writes
go through the SDK's file-write tool only (for the review document).
**Output:**
- A review file at `.specs/{spec_name}/review.md` committed to the feature
  branch and harvested normally.
- A GitHub issue titled `[Skeptic Review] {spec_name}` with structured
  findings (see "GitHub Issue Idempotency" below).
- The review content is passed as additional context to the next Coder
  session so the Coder can proactively address the Skeptic's observations.
**Blocking behavior:** The Skeptic completes successfully (passing the review
to the Coder) unless the number of **critical** findings exceeds the
configured `skeptic_block_threshold` (default: 3). When the threshold is
exceeded, the Skeptic marks itself as blocked, cascade-blocking the Coder
until a human resolves the critical questions on the GitHub issue.
**Multi-instance:** Supports `instances: N` (recommended: 3). Each instance
reviews independently. The convergence step unions all findings, deduplicates
by exact `(severity, description)` match (normalized), and applies the
blocking threshold to the merged set. A critical finding only counts if it
appears in >= ceil(N/2) instance outputs.

### The Verifier

**Purpose:** Verify the Coder's output for code quality, test coverage, and
spec conformance. The Verifier reads the implementation, runs quality checks,
compares the code against the spec's requirements and acceptance criteria, and
produces a structured verdict.
**Injection:** `auto_post` — injected as a sibling after the last Coder group.
Runs in parallel with other `auto_post` archetypes (e.g., Security Shaman).
**When:** After the last Coder group completes.
**Template:** New `verifier.md` template. Instructs the agent to:
1. Read the spec's requirements.md, design.md, and test_spec.md.
2. Read the code changes produced by the Coder (via `git diff develop`).
3. Run the test suite and linter.
4. Check each acceptance criterion for conformance.
5. Produce a structured report: pass/fail per requirement, quality issues,
   missing test coverage, and an overall verdict (PASS / FAIL with reasons).
**Model tier:** STANDARD (default).
**Allowlist:** Global default (needs to run tests and linters).
**Output:**
- A verification report at `.specs/{spec_name}/verification.md` committed
  to the feature branch and harvested normally.
- If the verdict is FAIL, a GitHub issue titled
  `[Verifier] {spec_name} group {N}: FAIL` with detailed findings
  (see "GitHub Issue Idempotency" below).
**Blocking behavior:** A PASS verdict completes the node successfully. A FAIL
verdict marks the node as failed, triggering the
**retry-predecessor-on-downstream-failure** mechanism (see Key Decisions).
The Coder reruns with the Verifier's failure report as context. After
`max_retries` exhausted, the node is blocked per normal orchestrator rules.
**Registry flag:** `retry_predecessor = true`.
**Multi-instance:** Supports `instances: N` (recommended: 3). Verdict is
determined by majority vote: PASS if >= ceil(N/2) instances say PASS.

### The Librarian

**Purpose:** Write documentation, user guides, API references, README updates.
**Injection:** `manual` — assigned by coordinator annotation or `tasks.md` tag.
**When:** Checkpoint task groups, documentation task groups. The coordinator
assigns archetype `"librarian"` to tasks whose title or body indicates
documentation work.
**Template:** New `librarian.md` template. Instructs the agent to read
existing docs, understand the codebase, and produce/update documentation.
**Model tier:** STANDARD (default).
**Allowlist:** Global default (needs to read code and run doc generators).
**Output:** Documentation files committed and harvested normally.

### The Cartographer

**Purpose:** Map dependencies, generate architecture diagrams, update ADRs.
**Injection:** `manual` — assigned by coordinator annotation or `tasks.md` tag.
**When:** After structural changes (new modules, moved files, changed
interfaces). The coordinator assigns archetype `"cartographer"` to tasks whose
title or body indicates architecture documentation.
**Template:** New `cartographer.md` template. Instructs the agent to analyze
imports, draw dependency graphs (Mermaid), and create/update ADRs.
**Model tier:** STANDARD (default).
**Allowlist:** Global default.
**Output:** ADR files and architecture docs committed and harvested normally.

## SDK Abstraction Layer (Phase A)

This spec subsumes the research and requirements from spec 25 (RFC). The SDK
abstraction is Phase A — implemented first as an independent, low-risk
deliverable before the archetype feature work begins.

### AgentBackend Protocol

A `typing.Protocol` defining the contract any agent SDK adapter must implement:

```python
@runtime_checkable
class AgentBackend(Protocol):
    @property
    def name(self) -> str: ...

    async def execute(
        self,
        prompt: str,
        *,
        system_prompt: str,
        model: str,
        cwd: str,
        permission_callback: PermissionCallback | None = None,
    ) -> AsyncIterator[AgentMessage]: ...

    async def close(self) -> None: ...
```

### Canonical Message Model

Three frozen dataclasses that all backends must map their native messages into:

- `ToolUseMessage(tool_name, tool_input)` — agent invoked a tool
- `AssistantMessage(content)` — thinking / text output
- `ResultMessage(status, input_tokens, output_tokens, duration_ms,
  error_message, is_error)` — terminal message with usage metrics

The session runner consumes only these types. It never sees SDK-specific
message objects.

### ClaudeBackend Adapter

Extracts all existing Claude SDK code from `session.py` into
`agent_fox/session/backends/claude.py`. Maps `ClaudeCodeOptions`,
`ClaudeSDKClient`, `ResultMessage`, and the permission types to the
canonical protocol. All existing behavior is preserved exactly.

### Backend in Archetype Config

Each archetype in the registry can optionally specify a `backend` string
(default: `"claude"`). For this spec, all archetypes use `ClaudeBackend`.
The configuration extension point exists for future backends:

```toml
[archetypes.backends]
# Override execution backend per archetype (optional).
# Default: "claude" for all archetypes.
# skeptic = "langchain"  # Future: run Skeptic via LangChain agent
```

### Research Basis

The protocol design is informed by the spec 25 research into three SDKs:
- **Claude SDK:** async context manager + query/receive streaming
- **LangChain/LangGraph:** `ainvoke()` / `astream_events()` with middleware
  guardrails
- **AWS Strands:** synchronous callable with `HookProvider` lifecycle events

The `AsyncIterator[AgentMessage]` signature accommodates all three execution
models. See `.specs/25_sdk_abstraction_layer/prd.md` (superseded, status
marked in that file) for the full research details.

## GitHub Issue Idempotency

Both the Skeptic and Verifier file GitHub issues with their findings. On
re-runs (retries, re-planning, resumed execution), duplicate issues must be
avoided.

**Strategy: search-before-create.**

1. Before creating an issue, the archetype's post-session logic searches for
   an existing open issue with the same title prefix (e.g.,
   `[Skeptic Review] 03_session_and_workspace`).
2. If found: **update** the existing issue body with the new findings and
   append a comment noting the re-run.
3. If not found: **create** a new issue.

The search uses `gh issue list --search "in:title [Skeptic Review] {spec}"
--state open --json number,title` — deterministic, no LLM calls.

When the Skeptic completes with zero critical findings (no block), it closes
the issue (if one exists) with a comment: "All findings resolved — closing."

## Cost Model

Multi-instance execution and review archetypes add sessions. The cost impact
should be understood before enabling them.

### Per-Spec Cost Estimate (STANDARD tier at ~$0.50/session)

| Configuration | Sessions/Spec | Est. Cost/Spec |
|---------------|---------------|----------------|
| Coder only (current) | N (task groups) | N * $0.50 |
| + Skeptic (1 instance) | N + 1 | (N+1) * $0.50 |
| + Skeptic (3 instances) | N + 3 | (N+3) * $0.50 |
| + Verifier (1 instance) | N + 2 | (N+2) * $0.50 |
| + Skeptic (3) + Verifier (3) | N + 6 | (N+6) * $0.50 |
| Full roster, 3 instances each | N + 6 | (N+6) * $0.50 |

For a project with 10 specs averaging 5 Coder groups each:

| Configuration | Total Sessions | Est. Total Cost |
|---------------|---------------|-----------------|
| Coder only | 50 | ~$25 |
| + Skeptic(3) + Verifier(3) | 110 | ~$55 |

**Cost doubles** with full review coverage at 3 instances. Whether this is
worthwhile depends on the cost of bugs caught late vs. the cost of review
sessions. The config makes this a per-project choice:

- `archetypes.instances.skeptic = 1` for cost-sensitive projects (still gets
  review, just without convergence)
- `archetypes.instances.skeptic = 3` for high-stakes projects where review
  quality justifies the cost

The existing `max_cost` ceiling applies to all sessions including review
archetypes, preventing runaway cost.

## Supersedes

- `25_sdk_abstraction_layer` — fully replaced by this spec (Phase A). The SDK
  abstraction protocol, canonical message model, and ClaudeBackend adapter
  from spec 25 (RFC) are incorporated here.

## Configuration

```toml
# .agent-fox/config.toml

[archetypes]
# Enable/disable archetypes for the planner.
# Only enabled archetypes can be assigned to plan nodes.
coder = true              # Always true — cannot be disabled
skeptic = true            # Insert Skeptic review before each spec
verifier = true           # Insert Verifier after Coder groups
librarian = true          # Allow Librarian assignment
cartographer = true       # Allow Cartographer assignment

[archetypes.instances]
# Number of parallel instances per archetype (default: 1).
# Multiple instances run independently and their outputs are converged.
skeptic = 3               # 3 independent reviewers for convergence
verifier = 3              # 3 independent verifiers, majority-vote verdict
# coder = 1              # Multi-instance coding is not supported

[archetypes.skeptic]
# Skeptic-specific configuration
block_threshold = 3       # Block only if > N critical findings (after convergence)

[archetypes.models]
# Override model tier per archetype (optional).
# Defaults: coder=ADVANCED, skeptic=STANDARD, verifier=STANDARD,
#           librarian=STANDARD, cartographer=STANDARD
# skeptic = "SIMPLE"      # Uncomment to use a cheaper model for reviews

[archetypes.allowlists]
# Override bash allowlist per archetype (optional).
# If not set, the global security.bash_allowlist applies.
# skeptic = ["ls", "cat", "git", "wc", "head", "tail"]

[archetypes.backends]
# Override execution backend per archetype (optional).
# Default: "claude" for all archetypes.
# Future: "langchain", "strands", etc.
```

## Clarifications

1. **One archetype per node, multiple instances per node.** A task node is
   dispatched to exactly one archetype, but can run N independent instances of
   that archetype in parallel. The planner determines both the archetype and
   the instance count. If a task needs both coding and review, the planner
   creates two separate nodes.

2. **The coordinator is in the registry but not in the roster.** The
   coordinator entry exists in the archetype registry for template resolution
   (so `build_system_prompt("coordinator")` works). But it is not a
   task-facing archetype — it cannot be assigned to task graph nodes. The
   roster (Coder, Skeptic, Verifier, Librarian, Cartographer) is the set of
   archetypes assignable to tasks.

3. **Archetype assignment is the planner's job.** The deterministic orchestrator
   does not decide archetypes. It reads the `archetype` field from the plan
   node and resolves it against the registry. If the field is missing, it
   defaults to `"coder"`.

4. **Skeptic nodes use group number 0.** By convention, the Skeptic review node
   for a spec uses group number 0 (before the test-writing group 1). The
   graph builder inserts it during plan construction. This preserves the
   invariant that group N depends on group N-1 within a spec.

5. **Disabled archetypes produce a warning.** If a plan node references a
   disabled archetype, the orchestrator logs a warning and falls back to the
   Coder. It does not block execution.

6. **Spec 25 is superseded.** The SDK abstraction layer from spec 25 (RFC) is
   incorporated into this spec as Phase A. Spec 25's PRD is retained for
   historical reference (research into LangChain and Strands APIs) and is
   marked `status: superseded` in its own document.

7. **Archetype assignment priority.** `tasks.md` tag > coordinator annotation
   > graph builder default. This means a spec author can always override the
   LLM's choice, and the LLM can always override the default rules. The graph
   builder logs the final assignment for transparency.

8. **Skeptic-to-Coder handoff.** The Skeptic's review.md is included as
   additional context in the Coder's system prompt (appended to the assembled
   spec context). The Coder sees the Skeptic's observations and can
   proactively address them during implementation. This is a data handoff,
   not a control-flow dependency beyond the existing group ordering.

9. **Verifier failure is new orchestrator logic.** The
   retry-predecessor-on-downstream-failure mechanism is explicitly new
   behavior added to the orchestrator. It is gated by the `retry_predecessor`
   flag in the archetype registry — only archetypes that set this flag (the
   Verifier) trigger predecessor re-runs. Standard retry (re-run the failed
   node itself) is unaffected.

10. **Multi-instance convergence is deterministic.** The convergence step runs
    no LLM calls. Skeptic: union + deduplicate by exact `(severity,
    description)` tuple match (lowercased, whitespace-collapsed), then
    majority-gate critical findings. Verifier: majority vote on verdict.
    No embeddings, no semantic similarity — pure string operations.

11. **Instance count limits.** The Coder archetype does not support
    `instances > 1` (multiple Coders would produce conflicting code changes).
    If a plan node specifies `instances > 1` for the Coder, the orchestrator
    logs a warning and runs a single instance. Other archetypes support 1-5
    instances. Values > 5 are clamped with a warning.

12. **Multiple archetypes at the same stage.** Different archetypes can run
    concurrently at the same plan stage. This is distinct from multi-instance
    (N copies of the same archetype). Multiple `auto_post` archetypes are
    injected as sibling nodes that share the same predecessor — the task graph
    already supports this via independent nodes with a common dependency. The
    orchestrator's existing parallel dispatch handles them with no new logic.

13. **Implementation phasing.** Phase A (SDK abstraction) is delivered first
    and can be merged independently. Phase B (archetypes) builds on Phase A.
    This sequencing means Phase A can be validated in production before
    Phase B adds complexity. If Phase B is descoped or delayed, Phase A still
    delivers value (improved testability, vendor resilience).

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 2 | 2 | Config system (pydantic models) — group 2 is where `AgentFoxConfig` is defined |
| 03_session_and_workspace | 3 | 3 | `build_system_prompt()`, `build_task_prompt()` in prompt.py — group 3 is where the prompt builder is created |
| 15_session_prompt | 2 | 3 | Template loading and `_ROLE_TEMPLATES` — group 2 is where template infrastructure is built |
| 02_planning_engine | 3 | 2 | `Node` dataclass and plan serialization — group 3 is where the graph types are defined |
| 04_orchestrator | 1 | 4 | Orchestrator execution loop — group 1 is where the execution loop starts; new retry-predecessor logic added |
