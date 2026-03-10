# ADR: Agent Archetypes

**Status:** Accepted
**Date:** 2026-03-09

## Context

agent-fox executes all task graph nodes with a single "coder" agent
configuration — the same system prompt, model tier, and security allowlist.
This limits the system's ability to perform specialized tasks such as spec
review, post-implementation verification, documentation, and architecture
mapping. Additionally, session execution is tightly coupled to the Claude
Agent SDK (`claude_code_sdk`), making it difficult to test or swap runtimes.

## Decision

We introduce two changes, delivered in two sequential phases:

### Phase A: SDK Abstraction Layer

- Define an `AgentBackend` runtime-checkable `typing.Protocol` with three
  members: `name` (property), `execute()` (async generator), and `close()`.
- Define three frozen canonical message types (`ToolUseMessage`,
  `AssistantMessage`, `ResultMessage`) that all backends must produce.
- Implement `ClaudeBackend` as the concrete adapter wrapping `claude_code_sdk`.
  All SDK imports are confined to `agent_fox/session/backends/claude.py`.
- Refactor `session.py` to depend only on the protocol and canonical messages.

### Phase B: Agent Archetypes

- An **archetype registry** (`agent_fox/session/archetypes.py`) maps named
  configurations to task graph nodes. Each entry specifies: prompt template
  files, default model tier, injection mode, security allowlist override, and
  behavioral flags.
- The roster includes six archetypes: `coder`, `skeptic`, `verifier`,
  `librarian`, `cartographer`, and `coordinator` (not task-assignable).
- `Node` gains `archetype` (str) and `instances` (int) fields with backward-
  compatible defaults (`"coder"` / `1`).
- The **graph builder** auto-injects archetype nodes: `auto_pre` (Skeptic
  before first coder group) and `auto_post` (Verifier after last coder group).
- A three-layer **assignment priority** determines each node's archetype:
  `tasks.md` tag (highest) > coordinator override > graph builder default.
- **Multi-instance dispatch** runs N independent sessions in parallel.
  Convergence is deterministic with no LLM calls: Skeptic uses union/dedup
  with majority-gated critical findings; Verifier uses majority vote.
- **Retry-predecessor** logic resets the predecessor coder node when a
  Verifier fails, up to `max_retries`.
- **GitHub issue filing** uses search-before-create idempotency via `gh` CLI.
  Failures are logged and never block execution.
- **Configuration** via `[archetypes]` section in `config.toml`. All
  archetypes except Coder are disabled by default — zero behavioral change
  unless explicitly opted in.

## Alternatives Considered

1. **Hardcoded role switching.** We considered adding an if-else chain in the
   session runner for each role. Rejected because it doesn't scale — adding a
   new archetype would require modifying session execution code rather than
   just adding a registry entry and template file.

2. **Plugin-based archetype loading.** We considered a dynamic plugin system
   with entry points. Rejected as over-engineering for the current roster of
   six archetypes. The registry pattern is simpler and sufficient.

3. **LLM-based convergence.** We considered using an LLM to merge multi-
   instance outputs. Rejected for determinism and cost — convergence should be
   predictable string manipulation, not another LLM call.

## Consequences

### Positive

- **Testability:** The `AgentBackend` protocol enables mock backends in tests
  without patching SDK internals.
- **Vendor flexibility:** Alternative agent runtimes can be added by
  implementing the protocol.
- **Extensibility:** New archetypes require only a template file and a registry
  entry (no code changes for standard execution semantics).
- **Quality gates:** Skeptic and Verifier archetypes add automated review and
  verification to the task graph.
- **Zero-risk rollout:** All new archetypes are disabled by default. Existing
  behavior is unchanged unless the user enables archetypes via config.
- **Backward compatibility:** Legacy `plan.json` files without archetype
  fields load with correct defaults.

### Negative

- **Complexity:** The archetype system adds new concepts (registry, injection,
  convergence, retry-predecessor) that developers must understand.
- **Configuration surface:** The `[archetypes]` config section adds multiple
  new knobs (toggles, instances, models, allowlists per archetype).

### Risks

- **Retry-predecessor cycles:** Incorrectly configured retry limits could
  cause long retry loops. Mitigated by the `max_retries` cap.
- **Template drift:** Archetype prompt templates may need updates as the
  project evolves. Mitigated by keeping templates as separate markdown files.
