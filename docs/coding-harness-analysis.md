# Coding Harness Analysis: agent-fox vs. Raschka's Framework

> Analysis date: 2026-04-05
> Reference: "Components of a Coding Agent" — Sebastian Raschka

## Raschka's 6 Components of a Coding Harness

| # | Component | Key Functions |
|---|-----------|---------------|
| 1 | **Live Repo Context** | `WorkspaceContext` — tracks live state of the repo being modified |
| 2 | **Prompt Shape & Cache Reuse** | `build_prefix`, `memory_text`, `prompt` — constructs prompts and exploits KV-cache with stable prefixes |
| 3 | **Structured Tools, Validation & Permissions** | `build_tools`, `run_tool`, `validate_tool`, `approve`, `parse` — defines tool schemas, validates calls, enforces access control |
| 4 | **Context Reduction & Output Management** | `clip`, `history_text` — truncates/clips context to stay within token limits during a session |
| 5 | **Transcripts, Memory & Resumption** | `SessionStore`, `record`, `note_tool`, `ask`, `reset` — persists transcripts, enables resume, in-session note-taking |
| 6 | **Delegation & Bounded Subagents** | `tool_delegate` — lets a session spawn sub-agents with limited scope from within the session |

---

## Where agent-fox Is Strong

### Component 1 — Live Repo Context
agent-fox goes further than a shared mutable workspace: every session gets an **isolated git worktree**. Concurrent sessions can't interfere with each other, and merge conflicts surface at a well-defined boundary (post-session harvest).

### Component 3 — Permissions
The async `permission_callback` per tool call plus per-archetype bash allowlists is solid. Each archetype (Skeptic, Auditor, etc.) gets exactly the tools it needs and no more.

### Component 5 — Memory
The DuckDB knowledge store with semantic search (sentence-transformers embeddings), confidence scoring, supersession chains, and causal extraction is more sophisticated than a simple session transcript store.

### Beyond the 6 Components

agent-fox has capabilities the harness framework doesn't describe:

- **Spec-driven workflow**: PRD → 5-artifact spec package → task dependency graph → execution
- **Multi-archetype quality gates**: Skeptic (pre-review), Auditor (mid-review), Verifier (post-review), Oracle (drift detection)
- **Adaptive multi-tier model routing**: SIMPLE → STANDARD → ADVANCED with statistical feedback loop
- **Parallel execution**: Up to 8 concurrent sessions with topological dependency ordering
- **Full git lifecycle**: Worktrees, harvest, merge, cascade blocking on failure

---

## Where agent-fox Lacks

### Gap 1 — Prompt Cache Reuse (Component 2)

**What's missing:** Raschka explicitly designs prompts to maximise KV-cache hits by keeping a stable prefix. agent-fox builds prompts by interpolating templates at execution time with no separation between the immutable part (system prompt + spec documents) and the variable part (prior findings + current task body + retry context).

**Impact:** Every session pays full prefill cost, even when running multiple sessions against the same spec. With Anthropic's prompt caching (`cache_control: {type: "ephemeral"}`), a 10k-token system prompt could be cached — for a spec with 8 sessions (5 task groups + Skeptic/Auditor/Verifier), that's 7 free cache hits.

**Fix:** Split `session/prompt.py` into `build_prefix()` (stable) and `build_suffix()` (variable), and annotate the prefix boundary with `cache_control`.

---

### Gap 2 — In-Session Context Reduction (Component 4)

**What's missing:** No `clip()` / `history_text()` equivalent within a session. There is no mechanism to summarise or drop old turns as a session approaches its turn budget. Context fills with raw bash output, full file reads, and redundant tool results.

**Impact:** Long sessions (300-turn Coder on ADVANCED) degrade in quality as early context is pushed out of the window, and costs rise non-linearly with turn count.

**Fix:** In `session_lifecycle.py`, after each N turns (e.g. 70% of `max_turns`), inject a compacted summary of the preceding exchange and truncate raw history. The SDK's `conversation` parameter can be pre-processed before the next turn.

---

### Gap 3 — In-Session Delegation (Component 6)

**What's missing:** `tool_delegate` — a tool callable from within a session that spawns a bounded sub-agent. In agent-fox, all delegation is **pre-planned** by the orchestrator. A Coder cannot decide mid-task to ask the Oracle to verify an assumption.

**Impact:** Agents can't respond dynamically to uncertainty. A Coder that discovers a spec ambiguity can only guess or stall — it cannot delegate a targeted question to a smarter model.

**Fix:** Expose an optional `delegate` tool (allowlisted per archetype) that the harness intercepts. On interception, spin up a lightweight Oracle/Skeptic sub-session, await the result, and inject it as a tool response back into the Coder's conversation.

---

### Gap 4 — Session Resume (Component 5, partial)

**What's missing:** If a session crashes mid-way (network error, timeout, hard SIGINT), all progress is lost. Sessions restart fresh from the initial prompt. There is no transcript checkpoint that allows a session to resume from the last committed state.

**Impact:** Expensive long-running ADVANCED-tier sessions (200+ turns) are fully re-billed on retry.

**Fix:** Write a `{node_id}.checkpoint.jsonl` file, appending each `AssistantMessage` / `ToolUseMessage` as the session progresses. On retry, detect the checkpoint and reconstruct the conversation history, resuming from where the session stopped.

---

### Gap 5 — Tool Output Validation (Component 3, partial)

**What's missing:** By removing fox tools (ADR-02) and deferring to Claude's built-in tools, agent-fox lost the ability to validate tool **outputs** before feeding them back to the model. Raschka's `parse` and `validate_tool` functions check that tool results are in expected shape.

**Impact:** Large, noisy bash outputs (full `pytest` logs, verbose `ruff` output) are fed raw into context. The model must parse them itself, wasting tokens and occasionally misreading results.

**Fix:** Even without custom tools, the permission callback (or a post-processing hook) could parse known bash output patterns — `pytest` → extract pass/fail/error counts, `ruff` → extract violation counts — and inject a structured summary in addition to (or instead of) raw stdout.

---

## Prioritised Improvements

| Priority | Change | Effort | Impact |
|----------|--------|--------|--------|
| High | Prompt prefix caching (`cache_control` on spec docs) | Low | Cost reduction on multi-session specs |
| High | Tool output summarisation (pytest, ruff, git) | Medium | Context quality + token savings |
| Medium | In-session context clipping at 70% turn budget | Medium | Long-session quality + cost |
| Medium | Session checkpoint + resume on retry | Medium | Cost recovery on timeout/crash |
| Low | In-session `delegate` tool for dynamic sub-agents | High | Adaptability to spec ambiguity |

---

## Summary

agent-fox is architecturally more ambitious than Raschka's harness framework — it is an orchestration layer built on top of the harness, not just the harness itself. Its spec-driven workflow, quality-gate archetypes, knowledge graph, and adaptive model routing are real differentiators absent from the reference framework.

The gaps are mostly at the **within-session** level: prompt cache optimisation, context lifecycle management, and dynamic delegation. Closing those gaps would reduce cost, improve long-session output quality, and make individual agents more capable of handling ambiguity without requiring every decision path to be pre-planned by the orchestrator.
