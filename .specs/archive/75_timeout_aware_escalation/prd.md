# PRD: Timeout-Aware Escalation

## Problem Statement

The escalation ladder treats timeout failures (exit code 143 / SIGTERM)
identically to logical failures. When a session times out, the system
escalates to a more expensive model tier (Sonnet → Opus), but a smarter model
doesn't help when the problem is running out of time. Data from 14 runs shows
3 of 8 escalations were for timeouts — all failed after escalation too,
wasting Opus-tier budget.

**Data source:** `docs/archetype-effectiveness-assessment.md`, Section 4c.

## Goals

1. **Distinguish timeout from logical failure** in the escalation ladder.
2. On timeout: **retry at the same model tier** with increased `max_turns`
   and extended session timeout, rather than escalating to a more expensive
   model.
3. Track timeout retries with a **separate counter** from failure retries,
   so timeout retries don't consume the failure retry budget (and vice versa).
4. Share the existing `max_budget_usd` — no separate timeout budget.

## Non-Goals

- Automated task group splitting (too complex, out of scope).
- Handling non-timeout failure types differently (SDK errors, context length
  exceeded, etc.).
- Adding new configuration knobs for timeout retry limits beyond a simple
  max count.

## Approach

### Timeout Detection

The session runner already sets `status = "timeout"` on `TimeoutError`. The
result handler checks `record.status == "completed"` for success, else
failure. We add a branch: if `record.status == "timeout"`, handle via
timeout-specific retry logic instead of the escalation ladder.

### Timeout Retry Behavior

When a session times out:

1. **Increment timeout retry counter** (separate from the escalation
   ladder's failure counter).
2. If timeout retries are not exhausted (max 2 timeout retries):
   - Retry at the **same model tier** (no escalation).
   - Increase `max_turns` by a configurable multiplier (default 1.5x,
     rounded up).
   - Increase `session_timeout` for this node by the same multiplier.
   - Cap extended timeout at 2x the original configured timeout.
3. If timeout retries ARE exhausted:
   - Fall through to the normal escalation ladder (record a failure,
     potentially escalate to a higher tier).

### Integration with Existing Budget

Timeout retries share the existing `max_budget_usd`. No separate budget
pool. The extended session simply consumes more of the shared budget.

### Configuration

- `max_timeout_retries`: Maximum number of same-tier timeout retries before
  falling through to the escalation ladder. Default: 2.
- `timeout_multiplier`: Factor by which to increase max_turns and session
  timeout on each timeout retry. Default: 1.5.
- `timeout_ceiling_factor`: Maximum multiplier for timeout extension
  relative to the original configured timeout. Default: 2.0.

These are added to `RoutingConfig` alongside `retries_before_escalation`.

## Clarifications

- **Separate counters:** Timeout retries do NOT count toward
  `retries_before_escalation`. A node can exhaust all timeout retries and
  then still get `retries_before_escalation` attempts at each tier via the
  normal escalation ladder.
- **Budget sharing:** Extended timeouts cost more but share the existing
  `max_budget_usd`. No new budget mechanism.
- **Scope:** Only `session_timeout` (asyncio.wait_for TimeoutError) triggers
  timeout-specific handling. SDK streaming errors, API errors, etc. continue
  to use the normal escalation ladder.
- **max_turns increase:** When max_turns is None (unlimited), no increase
  is applied — only session_timeout is extended.
