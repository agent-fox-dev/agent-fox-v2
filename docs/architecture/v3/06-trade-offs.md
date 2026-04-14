# Chapter 06 — Open Questions & Trade-offs

## Resolved Decisions

These decisions have been made and are reflected in the PRD. Documenting the reasoning for future reference.

### Python over Go or Rust

**Decision:** Python.

**Why:** The target user is a developer who already has Python in their toolchain. The knowledge store uses DuckDB (Python-native bindings), embeddings use ONNX runtime (Python bindings), and the primary harness wraps Claude Code (invoked as a subprocess — no performance-critical hot path). The orchestrator's job is to assemble prompts, dispatch processes, and parse results. This is I/O-bound coordination, not compute-bound work. Python's ecosystem advantages (DuckDB, ML libraries, rapid prototyping) outweigh Go's concurrency primitives or Rust's safety guarantees for this workload.

**What could change this:** If the PuzzlePod/Podman integration layer proves to be a bottleneck, a thin Go or Rust shim for the container lifecycle could be justified. But this would be a component, not a rewrite.

### Four Archetypes, Not Seven

**Decision:** Coder, Reviewer, Verifier, Maintainer.

**Why:** The Cartographer (codebase mapping) and Librarian (documentation maintenance) were aspirational in v2 — never fully implemented, and their functions fold naturally into the Maintainer and knowledge system. The Skeptic, Oracle, and Auditor shared the same fundamental behavior (read code, produce findings) with different focus areas. Collapsing them into a single Reviewer with configurable modes reduces implementation surface while preserving all review capabilities.

**Risk:** A single Reviewer prompt asked to do three different things (pre-review, drift detection, audit) might produce worse results than three specialized prompts. Mitigation: the Reviewer's system prompt is mode-specific. The archetype is unified at the orchestrator level, not at the prompt level.

### DuckDB Over SQLite for Knowledge

**Decision:** DuckDB.

**Why:** The knowledge store's query patterns are analytical: vector similarity search, aggregation over confidence scores, filtering by recency, and batch updates. DuckDB's columnar storage and vectorized execution handle these efficiently. SQLite is a better transactional store but a worse analytical one. The knowledge store has no concurrent-write requirements (one orchestrator process writes at a time), so DuckDB's single-writer model is not a limitation.

### Library-First Over Framework-First

**Decision:** Every package is independently importable.

**Why:** Framework-first designs (where you must adopt the entire system to use any part of it) create adoption barriers and make testing harder. Library-first means the planner can be used in a CI pipeline, the knowledge store in a notebook, and a single harness session in a custom script — without pulling in the full orchestrator. The CLI and daemon are thin consumers of the library, not the library itself.

### Capability Negotiation for Harnesses (was Q1)

**Decision:** Option 2 — Capability negotiation.

**Why:** The harness declares which optional capabilities it supports (resume, structured_output, pre_compact_hook). The orchestrator uses them when available, degrades gracefully when not. The capability set is small (five capabilities: `resume`, `structured_output`, `pre_compact_hook`, `effort_control`, `fork_session`) and well-defined — a manageable abstraction tax that avoids both the opacity of fully opaque `harness_options` and the lock-in of a Claude-optimized design.

**What this means for the spec:** The harness protocol in Chapter 02 defines five operations (start, stream, inject, stop, capabilities). The orchestrator's session lifecycle (Chapter 03) branches on capability availability — e.g., retry uses session resume if the harness supports it, falls back to fresh session if not.

### Credential Isolation via PuzzlePod (was Q2)

**Decision:** PuzzlePod's phantom token architecture handles credential isolation in sandbox mode. OneCLI optional for teams with complex policies.

**Why:** The original Q2 decision (ship a custom Python HTTPS proxy) was superseded by the Q6 decision to adopt PuzzlePod. PuzzlePod's `puzzle-proxy` and phantom token system provide credential isolation as a built-in capability — no custom proxy needed. For `--no-sandbox` mode, the orchestrator passes the API key via environment variable at process start (weaker, but functional for local development).

**What this means for the spec:** The `agent_fox.security` package (Chapter 02) manages PuzzlePod credential configuration, not a custom proxy. The defense-in-depth model is: phantom tokens via PuzzlePod (sandbox mode) → environment variable injection (`--no-sandbox` fallback) → leak detection (always on). OneCLI remains available as an upgrade for teams with multiple services and complex credential policies.

### Knowledge Store Primary for Work Items (was Q3)

**Decision:** Option 1 — Knowledge store primary, GitHub sync optional.

**Why:** The knowledge store is the system of record. Night-shift writes work items there. A one-way push to GitHub Issues (`af nightshift sync-issues`) provides external visibility without requiring GitHub as a dependency. Bidirectional sync is Phase 5 territory. The CLI is the primary interface for agent-fox users; GitHub sync is a courtesy for team visibility.

### ONNX Embeddings, Apple Silicon Optimized (was Q4)

**Decision:** Option 4 — Tiny non-torch model via ONNX runtime, optimized for Apple Silicon.

**Why:** An ONNX-based embedding model (e.g., `gte-small` or equivalent) eliminates the torch dependency while keeping embeddings local and free. The ONNX runtime supports CoreML and Metal execution providers on Apple Silicon, so embeddings run on the Neural Engine or GPU rather than CPU — significantly faster on M-series Macs. Users who need higher-quality retrieval can install a full torch-backed model via `uv pip install agent-fox[knowledge-torch]`.

**What this means for the spec:** The `agent_fox.knowledge` package (Chapter 02, 04) depends on `onnxruntime` (not torch) for embeddings. The default model ships as a small ONNX artifact (~25-80MB). Configuration includes an `embedding_device` option (default: `auto`, which selects CoreML on macOS/Apple Silicon, CUDA on Linux with GPU, CPU elsewhere). Chapter 04's embedding model section reflects ONNX as the default path.

### Spec Generation via af-spec Skill (was Q5)

**Decision:** Option 1 — Skill-only (current model).

**Why:** The `af-spec` skill already works inside Claude Code sessions. Users invoke it from their editor or terminal. It produces a complete five-artifact spec package through a guided workflow. No CLI wrapper needed for launch — the skill is the on-ramp. A CLI wrapper (`af spec generate`) can be added later (Phase 5) as a convenience.

### PuzzlePod Container Sandboxing (was Q6)

**Decision:** Container-based sandboxing via PuzzlePod + Podman from Phase 1, on both macOS and Linux. `--no-sandbox` escape hatch for development.

**Why:** Platform-specific sandboxing (bwrap on Linux, deprecated `sandbox-exec` on macOS) created an unacceptable split where the primary development platform had meaningfully weaker isolation. PuzzlePod provides a uniform container-based model with runtime governance that goes beyond static container security:

- **Fork-Explore-Commit** — Agent writes go to an ephemeral OverlayFS layer. Changesets are evaluated by OPA/Rego policy before being committed. Nothing persists without policy approval.
- **Phantom token credentials** — Agents never see real API keys. Surrogate tokens are resolved at the proxy layer. DLP scanning on outbound requests prevents exfiltration.
- **Kernel-enforced containment** — Namespaces, Landlock, seccomp, and cgroups survive daemon crashes. The kernel enforces isolation; userspace makes governance decisions.
- **Per-archetype sandbox profiles** — Filesystem access, network mode, and resource limits are configurable per profile, mapping naturally to agent-fox's four archetypes.

**Trade-offs accepted:**
- Podman + PuzzlePod are mandatory external dependencies. This is a meaningful adoption barrier, mitigated by `af init` providing guided setup and prerequisite checking.
- macOS containers run in a Linux VM (Podman machine), adding ~2GB memory overhead.
- The "time to first run" target is relaxed from 10 to 15 minutes to accommodate Podman/PuzzlePod setup.
- `--no-sandbox` provides an escape hatch for development iteration where full container isolation is unnecessary. This is an explicit opt-in to reduced security, not the default.

**What this means for the spec:** Sandboxing moves from Phase 3 to Phase 1. The `agent_fox.security` package manages PuzzlePod integration (profile mapping, container lifecycle, credential configuration) rather than bwrap/sandbox-exec profiles. The credential proxy is PuzzlePod's built-in phantom token architecture, not a custom Python proxy.

**Risk:** PuzzlePod is new (created 2026-03-24) but has organizational backing — it is part of a larger system under active development. agent-fox maintains a fork (`agent-fox-dev/puzzlepod`) and is never blocked on upstream. The primary risk is not project abandonment but upstream API changes that break agent-fox's integration. Version pinning against fork releases and CI testing mitigate this. See the "PuzzlePod dependency management" trade-off below for ongoing monitoring.

**Fallback path without PuzzlePod:** `agent_fox.security` would manage containers directly via Podman CLI/API. Sandbox profiles would be implemented as Containerfile templates with volume mount restrictions and network modes. Credential isolation would fall back to environment variable injection (the `--no-sandbox` model). Fork-Explore-Commit would be replaced by standard worktree-based isolation (already in `agent_fox.workspace`). This provides container isolation but without runtime governance.

---

## Trade-offs to Monitor

These aren't open questions — they're accepted trade-offs that should be revisited as the system matures.

### Knowledge confidence is a frequency signal, not a correctness signal

The fact lifecycle uses confidence as a proxy for trustworthiness, but confidence actually measures how often a fact was encountered. Three mitigations are in place: outcome-gated confirmation (failed sessions don't boost confidence), LLM-judged supersession without a confidence barrier (correct contradictions aren't blocked by high-confidence incumbents), and change-triggered staleness decay (facts about modified files lose confidence immediately). These reduce the worst failure modes but do not eliminate them. A subtly wrong fact that appears in successful sessions will still accumulate confidence. Ground-truth validation — comparing facts against test outcomes or code analysis — is a potential Phase 3+ extension but adds significant complexity. Monitor for cases where high-confidence facts are demonstrably wrong and assess whether the self-correcting property (supersession → re-extraction) is sufficient in practice.

### Merge serialization may not scale beyond the target concurrency

The merge cascade's global lock (ch 03) is correct for the target scale (4 concurrent sessions, 1-5 person team). Lock hold time is dominated by fast-forward and rebase operations (milliseconds to seconds). But if concurrency limits are raised significantly (8+ parallel sessions) or plans grow large (50+ specs with high parallelism), the merge queue could become a throughput bottleneck — particularly when merges fall through to three-way resolution. A potential optimization is **background rebase**: rebase the completed branch onto the current `develop` *before* acquiring the lock, reducing lock hold time to just the fast-forward attempt. This would require re-rebasing if `develop` moves during the background rebase, but the expected case (no conflicts) makes this a net win. Not needed at the current target scale; worth implementing if concurrency limits are raised.

### Prompt cache optimization requires prefix stability

The cost savings from prompt caching depend on the spec context (system prompt + spec docs) being identical across sessions for the same spec. Any per-session variation in the prefix (injected knowledge facts, prior findings) reduces cache hit rate. The boundary between "stable prefix" and "variable suffix" needs empirical tuning.

### Knowledge extraction adds latency to the pipeline

After each Coder session, a Maintainer session runs to extract facts. This delays the start of the next downstream session. If knowledge extraction is slow (large transcripts, expensive LLM calls), it becomes a bottleneck. Mitigation: extraction runs asynchronously and does not block dispatch of non-dependent nodes.

### The four-archetype model has known gaps

The four built-in archetypes (Coder, Reviewer, Verifier, Maintainer) cover the spec-driven execution loop: implement, review, verify, analyze. Two activities that users reasonably expect — deployment and research/exploration — are outside this loop. The custom archetype mechanism (ch 03, Archetype Extensibility) handles both, but custom archetypes are an escape hatch, not a first-class experience. Monitor whether deployment or research archetypes become common enough across projects to warrant promotion to built-in status (dedicated permission presets, default profiles, CLI integration). The bar for adding a fifth archetype is high: it must have a permission model that doesn't reduce to an existing archetype's, and it must appear in enough real workflows to justify the added surface area.

### Keyword heuristics are brittle proxies for intent

Archetype injection (ch 03 §Phase 2) places audit-review by matching task descriptions against keywords (`test`, `spec`, `coverage`, `verify`). Adaptive model routing (ch 03 §Initial Heuristic Rules) uses a similar keyword set (`refactor`, `migration`, `security`, etc.) to predict model tier. Both are deterministic given the same input text, but they're sensitive to wording choices that carry no semantic difference — "add tests" matches, "write verification" matches differently, "validate behavior" matches nothing. If this causes user confusion (unexpected audit-review placement or model tier), the mitigation path is either expanding the keyword sets, switching to lightweight semantic matching, or encouraging spec authors to use explicit `[archetype: X]` and `[model: Y]` tags for fine-grained control.

### Reviewer findings are LLM judgments, not proofs

Even with shell access in drift-review and audit-review modes (ch 03), Reviewer findings are ultimately LLM interpretations of code and specs. The shell provides empirical grounding (the Reviewer can verify a function signature exists before claiming it doesn't match), but the judgment of whether it *matters* is still subjective. Pre-review findings are entirely subjective by nature — no shell access would change that. The agreement ratio annotation helps distinguish high-confidence from speculative findings, but does not validate correctness. If Reviewer false positive rates are high in practice, the remediation path is: (a) tighten the drift-review and audit-review prompts to require shell-verified evidence for each finding, (b) add a post-hoc validation step where findings are checked against concrete commands before being surfaced to the Coder, or (c) switch the default instance count from 1 to 3 and use agreement ratio as a severity modifier.

### Harness-agnosticism has a quality cost

The harness protocol is open and the orchestrator adapts to declared capabilities. But three capabilities that `ClaudeCodeHarness` provides — permission callbacks, pre-compact hooks, and session resume — protect core guarantees (security, quality, reliability). Other harnesses (Gemini CLI, OpenCode) don't expose equivalent primitives. The degradation when these are absent is not cosmetic:

- **No permission callback** → archetype permissions are prompt-enforced only. A Reviewer *can* write files; the prompt says not to. This reduces the security model from kernel-enforced containment + callback authorization to kernel-enforced containment + prompt advisory. The container still prevents escaping the sandbox, but within the sandbox, tool authorization is advisory.
- **No pre-compact hook** → long sessions lose task context when the context window compacts. The agent may produce off-topic work or re-ask questions it already resolved.
- **No resume** → crash recovery restarts from scratch. The agent re-reads the codebase, re-discovers state, and re-does committed work. Retries cost 2-3x more turns and may diverge from the original approach.

The pragmatic answer: Claude Code is the primary harness. The protocol exists to prevent v2-style SDK lock-in and to allow adaptation if Claude Code's API changes or a genuinely capable alternative emerges. It does not exist to promise equal-footing multi-harness support. The spec should not be read as "any harness works equally well" — it should be read as "Claude Code works fully, others work with documented limitations."

If a future harness provides equivalent capabilities (tool authorization callbacks, context management hooks, session continuations), it can declare them and the orchestrator will use them. The protocol is designed so that this upgrade path exists without requiring orchestrator changes. But until another runtime exposes these primitives, Claude Code is the only harness that delivers the full security and quality model.

### cq integration assumes a protocol that's still pre-v1

As of this writing, cq is a conceptual protocol without a stable specification. agent-fox defines its own knowledge export format (JSON with domain tags, fact statement, metadata, and provenance) and will maintain compatibility with cq if/when a stable specification emerges. The fallback is straightforward: export as agent-fox JSON, add a cq mapping layer later.

### PuzzlePod dependency management

PuzzlePod was created 2026-03-24 and is pre-1.0. agent-fox maintains a fork (`https://github.com/agent-fox-dev/puzzlepod`) and PuzzlePod is part of a larger system under active organizational development. This substantially reduces the abandonment risk — agent-fox is not dependent on a solo maintainer's continued interest, and can fix blocking issues without upstream coordination.

The remaining risks to monitor:

- **Upstream API churn.** PuzzlePod is pre-1.0. CLI and REST API surfaces may change between releases. agent-fox pins to specific fork releases and tests against the fork in CI. Upstream breaking changes are absorbed in the fork before they reach agent-fox.
- **Fork divergence.** If agent-fox's needs diverge from upstream's direction, the fork may accumulate patches that upstream won't accept. This is manageable while the delta is small (bug fixes, profile tweaks). If the fork grows a significant patch set, evaluate whether agent-fox should own its own sandbox runtime (direct Podman integration with agent-fox-specific governance) rather than maintaining an increasingly distant fork.
- **Rust build requirement.** PuzzlePod is a Rust binary. Source builds require a Rust toolchain (stable 1.75+). Pre-built binaries for common platforms mitigate this for end users, but the fork's CI pipeline must produce and publish binary releases for each supported platform.

The containment strategy remains: `agent_fox.security` wraps PuzzlePod behind an internal `SandboxRuntime` interface. A fallback to direct Podman integration (without PuzzlePod governance) is feasible by swapping the runtime implementation — though this loses Fork-Explore-Commit, phantom tokens, and runtime policy evaluation. The fork makes this fallback unlikely but the abstraction is cheap insurance.


### Local-first work items have a team visibility cost

Work items live in the local DuckDB knowledge store, not in an external tracker. This enables knowledge-assembled fix context, cross-type semantic search, and structured fix history — capabilities that depend on co-location with facts and session summaries. But it means team members without `af` CLI access cannot see what the system discovered. The team's existing triage workflow (GitHub Projects, Linear boards) is disconnected from agent-fox's work items.

Mitigations are in place: `af nightshift sync-issues` pushes work items to GitHub/Linear as a read-only view (enriched with knowledge context), `PROJECT_MEMORY.md` includes a work item summary, and `af status --work-items` provides a quick terminal view. But the one-way sync means comments, assignments, and linked PRs on the GitHub side don't flow back. For a solo developer or a small team where everyone runs `af`, this is not a problem. For a team where product managers or non-engineering stakeholders need visibility into discovered technical debt, the local-first model requires them to adopt a new tool or rely on periodic sync snapshots.

If teams consistently report that the local-first model creates visibility gaps, the remediation path is bidirectional sync adapters (Phase 5 extension point). The work item schema already supports externally-created items (`source_session_id` can be null). The risk is that bidirectional sync reintroduces the platform coupling that the local-first model was designed to avoid.

### Claude Managed Agents may commoditize the execution layer

Anthropic's Claude Managed Agents (CMA) is a hosted agent-as-a-service: cloud containers, built-in tools, multi-agent orchestration, persistent memory stores, and outcome-driven evaluation with rubric grading. It ships sandboxing, session management, and tool execution as a platform feature — precisely the infrastructure agent-fox builds locally with PuzzlePod + Podman.

Three tensions to monitor:

- **PuzzlePod justification narrows for cloud deployments.** CMA eliminates the need for local container infrastructure. Teams that don't require local execution or phantom token credential isolation may prefer cloud-hosted sessions. PuzzlePod's value concentrates on scenarios CMA doesn't cover: local/offline execution, kernel-enforced credential isolation, Fork-Explore-Commit governance, and environments where sending code to Anthropic's cloud is unacceptable.
- **If CMA adds planning or task decomposition, the overlap grows.** CMA currently has no concept of specs, dependency graphs, or execution ordering. Its multi-agent is ad-hoc (coordinator decides at runtime). If Anthropic adds a planning layer, structured task decomposition, or dependency-aware dispatch, it begins to overlap with agent-fox's engine. The defense is the spec-driven workflow — five-artifact packages, validation, deterministic planning, and the knowledge feedback loop are deep integration points that a generic platform is unlikely to replicate.
- **Memory stores may approach knowledge store capabilities.** CMA memory stores are text documents with full-text search and versioned audit trails. If Anthropic adds embeddings, semantic search, or structured schemas, the differentiation between CMA memory and agent-fox's DuckDB knowledge store narrows. agent-fox's knowledge pipeline (extraction from transcripts, embedding, confidence lifecycle, token-budget-aware injection, work item co-location) remains significantly richer — but the gap may close.

The containment strategy: agent-fox's harness protocol already accommodates CMA as a future harness adapter (see ch 02, CMA as protocol validation). If CMA matures, a `ManagedAgentHarness` in Phase 5 lets agent-fox use CMA's infrastructure while retaining its own orchestration, planning, and knowledge layers. agent-fox becomes the workflow layer atop CMA's execution layer — complementary, not competing.

### Cross-spec dependency contracts are informal

The dependency table's Relationship column describes what one spec needs from another in natural language ("Imports parsed spec models from group 3"). There is no formal interface contract — no type signatures, no schema validation, no automated check that the upstream output matches the downstream expectation. If the upstream Coder produces a different API than the downstream spec assumes, the mismatch is only detected when the downstream session fails. For a 1-5 person team where the same author often writes both specs, informal contracts are sufficient. If the system scales to larger teams or generated specs, the failure-as-detection model may become too expensive. A potential extension is structured dependency contracts (import paths, function signatures, schema fragments) that the Reviewer can validate pre-execution — but this adds authoring overhead that must justify itself.

---

## Claude Managed Agents — Detailed Analysis

This section provides a comprehensive analysis of Anthropic's Claude Managed Agents (CMA) platform, its relationship to agent-fox v3, and concrete integration opportunities. CMA was announced April 2026 as a beta platform for running Claude as an autonomous agent in managed cloud infrastructure.

### CMA Architecture Summary

CMA is built around four concepts: **Agents** (model + system prompt + tools + MCP servers + skills), **Environments** (container templates with packages and networking rules), **Sessions** (running agent instances), and **Events** (SSE-based bidirectional communication). Agents are versioned and reusable. Environments define cloud containers with configurable package managers (pip, npm, cargo, apt, gem, go) and networking modes (unrestricted or limited with explicit allowed-host lists). Each session gets an isolated container instance with a persistent filesystem within that session.

Notable features:

- **Multi-agent orchestration.** A coordinator agent declares `callable_agents` and delegates work to them at runtime. Called agents run in their own session threads (isolated context, shared filesystem). Only one level of delegation (no nested sub-agents). Thread-level event streaming provides full observability.
- **Memory stores.** Workspace-scoped persistent text document collections. Agents automatically check memory stores before starting and write learnings when done. Up to 8 stores per session, with read-only or read-write access. Full-text search, versioning, and audit trails with redaction for compliance. Individual memories capped at 100KB.
- **Outcomes.** Define a deliverable description and a rubric. A separate grader model (independent context window) evaluates the agent's output against the rubric and provides per-criterion feedback. The agent iterates until the rubric is satisfied or max iterations (up to 20) are reached. This is CMA's closest equivalent to agent-fox's Verifier archetype.
- **Tool confirmation.** Permission policies per tool (always_allow, always_ask). When `always_ask` is configured, the session pauses and emits a `requires_action` stop reason. The caller approves or denies each pending tool call via `user.tool_confirmation` events.
- **Custom tools.** Client-executed tools defined by JSON schema. CMA emits `agent.custom_tool_use` events; the caller executes the tool and returns results via `user.custom_tool_result`.

### ManagedAgentHarness — Feasibility Assessment

CMA maps cleanly to the agent-fox harness protocol (ch 02):

| Harness Operation | CMA Implementation |
|---|---|
| `start(system_prompt, task_prompt, tools, model_config)` | Create agent (or reuse existing) + create environment (or reuse) + `POST /v1/sessions`. System prompt on the agent, task prompt as first `user.message` event. Tools mapped via `agent_toolset_20260401` configs (enable/disable per tool). |
| `stream(session_id)` | `GET /v1/sessions/:id/stream` — SSE event stream. Map `agent.message` → `assistant_message`, `agent.tool_use` → `tool_call`, `agent.tool_result` → `tool_result`, `session.status_idle` → `session_end`. |
| `inject(session_id, message)` | `POST /v1/sessions/:id/events` with `user.message`. Does not interrupt in-flight generation — matches inject semantics. |
| `stop(session_id, reason)` | `POST /v1/sessions/:id/events` with `user.interrupt`. |
| `capabilities()` | `{resume, structured_output}` |

**Capabilities declared:** `resume` (sessions are stateful server-side — native), `structured_output` (custom tools enable structured output extraction). Not declared: `pre_compact_hook` (CMA compacts internally with built-in optimizations; no hook to inject context), `effort_control` (CMA has `speed: "fast"` but no thinking budget control), `fork_session` (not applicable).

**Event model translation:**

| CMA Event | agent-fox Event | Notes |
|---|---|---|
| `agent.message` | `assistant_message` | Direct mapping. Content blocks → text. |
| `agent.thinking` | (not mapped) | Extended thinking content. Could be captured in transcript. |
| `agent.tool_use` | `tool_call` | `name` → `tool_name`, `input` → `arguments`, `id` → `call_id`. |
| `agent.tool_result` | `tool_result` | `id` → `call_id`, `content` → `output`. |
| `agent.custom_tool_use` | `tool_call` | Custom tools require caller execution. The harness would need to handle this internally or expose it as a capability. |
| `session.status_idle` | `session_end` | Stop reason inspection needed: `end_turn` → normal completion, `requires_action` → paused for tool confirmation. |
| `session.status_terminated` | `error` (non-recoverable) | Session ended due to unrecoverable error. |
| `session.error` | `error` | Check `retry_status` — `retrying` means CMA is handling it internally, `done` means all retries exhausted. |
| `span.model_request_end` | (metadata) | Token counts for cost tracking. Maps to agent-fox's cost management. |
| `agent.thread_context_compacted` | (notification only) | No hook to inject context. The harness logs this event but cannot intervene. |

**Archetype mapping via separate CMA agents:**

CMA's tool enable/disable at agent creation maps naturally to archetype permission profiles:

| Archetype | CMA Agent Configuration |
|---|---|
| Coder | Full toolset enabled. Unrestricted networking (or limited with required domains). |
| Reviewer (pre-review) | Toolset with `bash` disabled, `write` disabled, `edit` disabled. Read-only file operations + web search. |
| Reviewer (drift/audit) | Toolset with `write` disabled, `edit` disabled. Bash enabled (read-only shell for empirical verification). |
| Verifier | Toolset with `write` disabled. Bash enabled (runs test commands). |
| Maintainer | Full toolset for knowledge extraction mode. Write disabled for analysis-only modes. |

Each archetype would be a separate CMA agent definition, referenced by ID when the engine dispatches sessions. Agent versioning provides audit trails for archetype configuration changes.

**Permission callback gap.** CMA's tool permissions are static (set at agent creation), not dynamic (decided per-call by a callback). agent-fox's `ClaudeCodeHarness` uses a permission callback that can make per-invocation decisions based on archetype, tool name, and arguments. CMA's model is coarser but still effective: disable the tools the archetype shouldn't use, and the agent never gets them. The gap is edge cases where the same tool should be allowed with some arguments and denied with others (e.g., bash allowed for `pytest` but denied for `rm -rf`). CMA's `always_ask` permission policy could handle this — the harness would implement an auto-approve/deny callback in the event loop — but this adds latency to every tool call.

**Pre-compact hook gap.** CMA compacts internally and emits `agent.thread_context_compacted` as a notification. The orchestrator cannot inject critical context before compaction. Mitigation: front-load all critical context into the system prompt (the stable prefix). For CMA sessions, the system prompt would include the task group description, unresolved findings, and relevant requirements — content that `ClaudeCodeHarness` injects dynamically via the hook. This works but makes the system prompt larger and less cacheable (the variable content that would normally be in the suffix moves into the prefix). For short sessions (< 50 turns), compaction is unlikely and the gap doesn't matter. For long sessions, the quality risk is real.

**Resume advantage.** CMA sessions are stateful server-side. Resume is native and free — no checkpoint files, no transcript replay. On retry, the orchestrator sends a new `user.message` with error context, and the session continues with full history. This is strictly better than `ClaudeCodeHarness`'s checkpoint-based resume for crash recovery. For retry-with-escalation, the gap is that CMA uses a fixed model per agent — escalating from Sonnet to Opus requires creating a new session with a different agent, losing the prior session's context. A workaround: create the new session and prepend the prior session's key findings as context.

### Outcomes and the Verifier Archetype

CMA's outcome system is architecturally similar to agent-fox's Verifier:

| Dimension | CMA Outcomes | agent-fox Verifier |
|---|---|---|
| **Input** | Description + markdown rubric | `test_spec.md` + `requirements.md` |
| **Evaluator** | Separate grader model (independent context window) | Verifier archetype session (separate from Coder) |
| **Output** | Per-criterion pass/fail + explanation | Pass/fail verdicts per requirement ID |
| **Iteration** | Agent revises and re-evaluates (up to 20 cycles) | Engine retries with error context (up to configured attempts per tier) |
| **Independence** | Grader has no access to agent's implementation reasoning | Verifier runs in separate session with its own context |

Key insight: CMA's grader runs in an independent context window, isolated from the agent's implementation choices. This prevents the "grading your own homework" problem. agent-fox's Verifier achieves the same isolation by running as a separate archetype session, but both the Coder and Verifier see the same codebase. CMA's approach is purer — the grader evaluates the artifact, not the code — but less practical for software verification where "does the code work" requires running tests.

The V3 spec should not adopt CMA's rubric model (agent-fox's spec-driven verification is deeper), but the independent-context-window pattern for the grader is worth noting. If agent-fox's Verifier ever produces biased verdicts (too lenient on code it has contextual sympathy for), the mitigation is the same: isolate the evaluator's context from the implementation context.

### Multi-Agent Validation

CMA's multi-agent pattern (coordinator delegates to specialized callable agents, shared filesystem, isolated context, one level of delegation) validates agent-fox's archetype model:

- **Shared filesystem, isolated context** — CMA callable agents share a container filesystem but have their own conversation history. This matches agent-fox's worktree model: all archetypes work on the same codebase, but each session has its own context.
- **Specialized agents** — CMA encourages creating focused agents for review, testing, research. This mirrors agent-fox's four archetypes with distinct permission profiles and system prompts.
- **Coordinator pattern** — CMA's coordinator decides at runtime what to delegate. agent-fox's engine decides at plan time based on the DAG. The planning-based approach is more predictable and auditable.

The difference: CMA's orchestration is emergent (the coordinator LLM decides), agent-fox's is deterministic (the planner decides). CMA's approach is simpler but less controllable. agent-fox's approach is more complex but produces reproducible execution plans.

One architectural gap: CMA limits delegation to one level (coordinator → agents, but agents cannot call agents). agent-fox has no such limitation in principle — the engine dispatches all sessions, and any archetype's output can feed into any other's input via the DAG. This is more flexible but requires the planning layer to manage the complexity.

### Memory Stores as Knowledge Bridge

CMA's memory stores share surface-level goals with agent-fox's DuckDB knowledge store (cross-session learning) but differ significantly in capability:

| Dimension | CMA Memory Stores | agent-fox Knowledge Store |
|---|---|---|
| **Storage** | Text documents (markdown) | Structured facts (statement, domain tags, confidence, provenance) |
| **Search** | Full-text search | Semantic search (embedding-based), full-text, filtered by domain/status |
| **Scoring** | None | Composite scoring: `similarity × confidence × recency` with per-type weights |
| **Extraction** | Agent-initiated (Claude decides what to write) | Pipeline-driven (Maintainer extracts from transcripts, structured output) |
| **Injection** | Automatic (agent checks stores before starting) | Token-budget-aware context assembly with relevance ranking |
| **Versioning** | Per-memory immutable versions with audit trails | Fact lifecycle (proposed → confirmed → deprecated, confidence decay) |
| **Concurrency** | Optimistic concurrency via content SHA-256 | Single-writer (one orchestrator process) |
| **Co-location** | Separate from execution | Facts, findings, session summaries, and work items in same store |

CMA memory stores could serve as an interchange format for Phase 5 knowledge sharing (ch 04, cq Protocol). Instead of DuckDB-to-DuckDB transfer between projects, agent-fox could export curated facts to a CMA memory store and attach it to CMA-hosted sessions. This enables mixed workflows: some agents run locally via `ClaudeCodeHarness` with full PuzzlePod isolation, others run in the cloud via `ManagedAgentHarness` with CMA memory stores as a shared knowledge layer.

The risk is impedance mismatch: agent-fox's structured facts (with confidence, domain tags, embeddings, and provenance) don't map cleanly to CMA's flat text documents. The export would necessarily lossy — confidence scores, embeddings, and provenance metadata would be serialized as markdown frontmatter or discarded. Import would require re-extraction and re-embedding. For cross-project knowledge sharing, this is acceptable (the receiving project re-evaluates facts in its own context anyway). For real-time knowledge synchronization within a single project's execution, it is not — the DuckDB store remains authoritative.

### What to Watch

1. **CMA planning features.** If Anthropic adds dependency-aware task decomposition or structured execution ordering to CMA, the overlap with agent-fox's engine grows significantly. Currently CMA is purely reactive (coordinator decides ad-hoc).
2. **CMA memory store enhancements.** Embeddings, semantic search, structured schemas, or confidence scoring would narrow the knowledge store differentiation.
3. **CMA outcome chaining.** Currently one outcome at a time, sequentially. If CMA adds parallel outcomes, dependency-aware evaluation chains, or rubric inheritance, it approaches the Verifier + assess/decide pipeline.
4. **CMA pricing model.** CMA's cost structure (tokens + container time) may differ significantly from local execution (tokens only). agent-fox's cost management (ch 04) would need to account for both pricing models if `ManagedAgentHarness` is adopted.
5. **CMA self-hosted option.** If Anthropic offers on-premises CMA deployment, the "can't send code to the cloud" objection disappears, and CMA becomes competitive with PuzzlePod for all deployment scenarios.

---

*Previous: [05 — Delivery Phases](./05-phases.md)*
*Next: [07 — Spec Breakdown & Implementation Guide](./07-spec-breakdown.md)*
