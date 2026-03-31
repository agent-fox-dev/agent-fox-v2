# PRD: Claude SDK Feature Adoption

## Problem Statement

Agent-Fox uses the `claude_code_sdk` for all coding sessions but only exercises
a subset of its capabilities. Several SDK features would improve reliability,
cost control, and output quality:

- **No turn limits** — runaway sessions burn tokens until the timeout kills them.
- **No budget caps** — cost is calculated post-hoc; there is no pre-emptive
  spend limit.
- **No fallback model** — if the primary model is rate-limited or unavailable,
  the session fails outright.
- **No extended thinking** — complex implementation tasks don't benefit from
  the model's chain-of-thought reasoning mode.

## Goals

1. **Turn limits** — Configure `max_turns` per archetype so read-only agents
   (oracle, skeptic) use fewer turns than coders.
2. **Budget caps** — Configure `max_budget_usd` per session to prevent
   runaway spend.
3. **Fallback model** — Configure a fallback model so sessions degrade
   gracefully when the primary model is unavailable.
4. **Extended thinking** — Enable extended thinking for the coder archetype
   (where deep reasoning helps most) and make it configurable per archetype.

## Non-Goals

- **`interrupt()` replacement for timeout** — deferred to a follow-up spec.
  The current `asyncio.wait_for` approach works; `interrupt()` is a
  refinement.
- **Structured outputs for verifier/auditor** — deferred. Requires defining
  JSON schemas for each archetype's findings format, which is a separate
  design effort.
- **`add_dirs` for multi-directory access** — deferred. Current worktree
  isolation is sufficient.
- **Native `allowed_tools`/`disallowed_tools`** — deferred. The custom
  permission callback provides more flexibility than SDK-side filtering.

## Clarifications

- **Q: Should extended thinking be always-on for coder?**
  A: Configurable via `config.toml`. Default to `adaptive` for coder (model
  decides when to think deeply), `disabled` for all others.
- **Q: What should `max_turns` default to per archetype?**
  A: Coder: 200, oracle/skeptic/auditor: 50, verifier: 75,
  librarian/cartographer: 100, coordinator: 30.
- **Q: What should `max_budget_usd` default to?**
  A: Configurable per-session, default $2.00. This is a safety net, not a
  tight constraint.
- **Q: What fallback model should be used?**
  A: Default fallback is `claude-sonnet-4-6` (STANDARD tier). Only applies
  when the primary model is unavailable.
- **Q: How does `max_budget_usd` interact with the existing cost calculation?**
  A: They are independent. `max_budget_usd` is SDK-enforced during execution;
  `calculate_cost()` produces post-hoc metrics for reporting.
