# Integration Gap Analysis: The Wired-But-Never-Called Pattern

**Date:** 2026-04-03
**Scope:** Audit of specs 70–78 implementation
**Issues filed:** agent-fox-dev/agent-fox#226, #227, #228, #229

---

## Executive Summary

A manual audit of the code produced for specs 70–78 found four bugs, all sharing
the same structural pattern: a component is **correctly implemented**, **tested in
isolation**, and then **never connected to the execution path that should call it**.
The automated audit agent (which read files individually) rated the codebase
"95% production-ready" and missed all four. This document explains why the
pattern occurs, catalogues the specific instances, and proposes structural
changes to the spec process to prevent recurrence.

---

## The Four Bugs

### Bug 1 — Critical: `HuntScanner` never wired to `NightShiftEngine`

**File:** `agent_fox/nightshift/engine.py`

`NightShiftEngine._run_hunt_scan_inner()` is a stub that unconditionally
returns `[]`. The `HuntScanner` and `HuntCategoryRegistry` classes in
`agent_fox/nightshift/hunt.py` — including all eight built-in hunt categories —
are fully implemented and tested in isolation, but are never instantiated or
called from the engine. Every scheduled hunt scan runs, increments
`state.hunt_scans_completed`, and silently produces zero findings.

The stub's docstring reads: *"Override point for testing."* It was never
replaced with a real implementation.

**Spec refs:** 61-REQ-3.1 through 61-REQ-3.4

---

### Bug 2 — Critical: `--auto` flag creates duplicate issues

**File:** `agent_fox/nightshift/engine.py`, `agent_fox/nightshift/finding.py`

`_run_hunt_scan()` calls `create_issues_from_groups()` (which creates N
issues and returns `None`), then immediately iterates the same groups and
calls `platform.create_issue()` *again* inside the `if self._auto_fix:` block
in order to obtain issue numbers to label. The result: 2× issues per finding
group; the `af:fix` label lands on the duplicates, not the originals.

The root cause is that `create_issues_from_groups()` discards the created
issue numbers. Two separate passes — one to create, one to label — each
worked against the original `groups` list instead of passing results from
the first to the second.

**Spec refs:** 61-REQ-1.2, 61-REQ-5.2, 61-REQ-5.4

---

### Bug 3 — Critical: `check_staleness()` logic inverted

**File:** `agent_fox/nightshift/staleness.py`

`check_staleness()` runs an ADVANCED-tier AI call to identify which remaining
issues are now resolved by a fix, then uses a GitHub API re-fetch as
verification. However, step 3 of the function marks an issue as obsolete only
if it is *already closed on GitHub* — i.e., not present in
`still_open_numbers`. The AI recommendation is used only to populate the
rationale string; it has no effect on which issues get closed.

The correct logic should be the opposite: mark an issue as obsolete when the
AI says it should be closed **and** GitHub confirms it is still open (so
`close_issue()` is actually needed). As implemented, the function pays for
an ADVANCED-tier API call on every fix, ignores its answer, and then calls
`close_issue()` only on issues that are already closed elsewhere — a no-op.

**Spec refs:** 71-REQ-5.1, 71-REQ-5.2, 71-REQ-5.E1

---

### Bug 4 — Moderate: `triage.supersession_pairs` silently discarded

**File:** `agent_fox/nightshift/engine.py`

`run_batch_triage()` returns a `TriageResult` with three fields:
`processing_order`, `edges`, and `supersession_pairs`. The engine only
consumes `triage.edges` (to build the dependency graph); both `processing_order`
and `supersession_pairs` are discarded. AI-identified supersession candidates
are never skipped or closed; they are processed in full, wasting fix sessions.

**Spec refs:** 71-REQ-3.5

---

## Root Cause Analysis

All four bugs share the same three-part failure mode:

### 1. Task decomposition creates invisible seams

The spec workflow breaks implementation into task groups executed by separate
agent sessions. Group N builds a component; Group N+1 integrates it. The
Group N agent ships correct, tested code. The Group N+1 agent writes integration
code that *looks* connected — an override point, a caller that iterates the same
data — but the actual wire from caller to component is missing or logically
inverted. Neither group's session is responsible for verifying the seam.

### 2. Unit tests mock at the exact boundary where wiring was supposed to happen

Test-first discipline is followed rigorously. But when tests are written
component-by-component, each test mocks the boundary at exactly the place where
the real wiring was supposed to exist:

- `HuntScanner` tests test the scanner directly, never through the engine.
- Engine tests mock `_run_hunt_scan_inner`, so a stub returning `[]` passes.
- Staleness tests verify parsing logic; they don't trace the call from
  the engine through to actual issue closures.

Green tests provide no signal about missing wires because the mocks sit at the
missing connection point.

### 3. Requirements describe actions, not data contracts

EARS syntax captures *what the system does* but not *what functions return*.
"Create one issue per group" is satisfied by calling `create_issue`. A separate
requirement "assign `af:fix` label" is satisfied by calling `assign_label`.
When two agent sessions implement these independently, both work against the
original input (`groups`), and the return value that should flow from the first
to the second is never defined or enforced.

---

## Why the Automated Audit Agent Missed These

The audit agent read files individually and assessed each component against its
spec. Every component was correctly implemented in isolation. The agent's
methodology had no step that traced the execution path end-to-end from the CLI
entry point to the expected side effect. It could see that `HuntScanner` existed
and matched the spec; it could not see that nothing called it.

This is a fundamental limitation of component-level auditing: it can verify that
pieces exist, but not that they are connected.

---

## Proposed Mitigations

See the updated `af-spec` skill for concrete changes. In summary:

| Gap | Mitigation |
|-----|-----------|
| Missing end-to-end call paths | Require an **Execution Path** section in `design.md` tracing every user-visible feature from entry point to side effect |
| Return values not specified | Require **return type contracts** in `requirements.md` for any function whose output is consumed by a caller |
| Unit tests mock integration boundaries | Require at least one **integration smoke test** per feature path in `test_spec.md` that cannot be satisfied by mocking the missing component |
| Stubs never replaced | Require a **wiring checklist** in `tasks.md` that audits every stub, `return []`, and `pass` in touched files |
| Audit agent reads components, not paths | The `af-spec-audit` skill should include a step that traces execution paths, not just reads files |

---

## Pattern Recognition Heuristics

When reviewing AI-generated code, these signals indicate an integration gap may
be present:

- A method named `_inner`, `_impl`, or prefixed with an underscore returns a
  trivial default (`[]`, `None`, `0`, `""`) with a docstring mentioning
  "override" or "testing hook"
- A function's return type is `None` but a caller later iterates data that
  logically should have come from that function
- A component has thorough unit tests but no test that instantiates it via its
  natural caller
- A data structure field is populated by parsing logic but grep finds no call
  site that reads that field downstream
- An AI API call's result is used only to populate a rationale/metadata field,
  never to make a control-flow decision
