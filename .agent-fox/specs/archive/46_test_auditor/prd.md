# PRD: Test Auditor Archetype

## Summary

Add a new **auditor** agent archetype that validates test code against
`test_spec.md` contracts before implementation begins. The auditor slots into
the task graph after test-writing groups and before implementation groups,
acting as a quality gate that ensures tests are complete, meaningful, and
strong enough to catch wrong implementations.

## Motivation

The current spec-driven workflow has the coder archetype write tests in task
group 1 and then implement code in subsequent groups. Because the same
archetype writes both tests and implementation, there is a subtle incentive
alignment problem: tests may be unconsciously shaped to be easy to pass rather
than to rigorously validate the specification.

The auditor archetype introduces adversarial separation between test writing
and test validation, catching weak, missing, or misaligned tests before
implementation begins.

## Core Capabilities

### 1. Test Quality Audit

The auditor reads `test_spec.md` and the actual test files, then evaluates
each test case entry across five dimensions:

1. **Coverage** -- Does every TS entry have a corresponding test function?
2. **Assertion Strength** -- Would a plausible but incorrect implementation
   fail? (The most important dimension.)
3. **Precondition Fidelity** -- Does the test setup match the TS entry's
   preconditions and pseudocode?
4. **Edge Case Rigor** -- Are boundary values and error paths tested?
5. **Independence** -- Can each test pass/fail independently?

### 2. Test Group Detection

The auditor does not hardcode "group 1." Instead, it detects test-writing
groups by analyzing group descriptions for patterns like "Write failing spec
tests", "Create unit test file", etc. Normally this is group 1, but the
auditor can also target other groups whose description indicates test writing.

### 3. Auto-Mid Injection

A new injection mode `auto_mid` inserts the auditor node into the task graph
between a detected test-writing group and the next implementation group.
Injection only occurs when:

- The auditor archetype is enabled in config.
- A test-writing group is detected.
- The spec has at least `auditor_min_ts_entries` test spec entries (configurable).

### 4. Retry Loop with Circuit Breaker

If the auditor verdict is FAIL, the test-writing coder is retried via the
existing retry-predecessor mechanism, with the auditor's findings as error
context. After retry, the auditor re-runs to validate the revised tests.

A circuit breaker aborts the loop after `auditor_max_retries` iterations
(configurable, default 2) to prevent infinite loops. When the circuit breaker
trips, the pipeline **halts** for this spec — the auditor node is marked as
blocked, preventing downstream implementation groups from executing. This is
intentional: if the coder cannot produce adequate tests after multiple retries,
it indicates a problem with the specification itself that requires human
attention. A GitHub issue is filed with the circuit breaker details.

### 5. Output Persistence

- The auditor writes its findings to `.specs/{spec_name}/audit.md` (similar
  to the skeptic's `review.md`).
- Retry events are captured in the audit event stream.
- On FAIL, a GitHub issue is filed (search-before-create idempotency, same
  pattern as skeptic/verifier).

### 6. Conservative Convergence

When running multiple auditor instances, convergence uses **union** (not
majority gate): if any instance flags a test as WEAK, MISSING, or MISALIGNED,
it is flagged in the merged result. This is intentionally conservative --
false negatives (missing a weak test) are worse than false positives.

## Non-Goals

- The auditor does NOT write or fix tests. It only reads and renders a verdict.
- The auditor does NOT receive skeptic findings. It operates independently.
- The auditor does NOT review implementation code. It only reviews test code.

## Configuration

```toml
[archetypes]
auditor = false  # opt-in, disabled by default

[archetypes.instances]
auditor = 1

[archetypes.auditor_config]
min_ts_entries = 5       # skip audit for small specs
max_retries = 2          # circuit breaker for retry loop

[archetypes.models]
auditor = "STANDARD"

[archetypes.allowlists]
auditor = ["ls", "cat", "git", "grep", "find", "head", "tail", "wc", "uv"]
```

## Clarifications

1. **Test group detection**: The auditor detects test-writing groups by
   description pattern matching (e.g., "write failing spec tests", "create
   unit test file"), not by hardcoding group number 1. Normally group 1 is
   the test-writing group per convention, but the mechanism is generic.

2. **Injection trigger**: The auditor only injects when a test-writing group
   is detected. If no group matches the test-writing pattern, no auditor
   node is added.

3. **Re-run after retry**: The auditor always re-runs after the coder retries.
   A circuit breaker (`auditor_max_retries`) aborts the loop after N
   iterations. When the circuit breaker trips, the pipeline halts for this
   spec (auditor node blocked) and a GitHub issue is filed.

4. **Minimum TS entries**: Configurable via `auditor_config.min_ts_entries`.
   Specs with fewer entries skip the auditor.

5. **Output persistence**: Findings are written to `audit.md` (like the
   skeptic's `review.md`). Retry events are captured in the audit event
   stream.

6. **GitHub issues**: Filed on FAIL using the same search-before-create
   pattern as the skeptic/verifier.

7. **Test runner access**: The auditor can run `pytest --collect-only` and
   `pytest <file> -q` to verify tests are discoverable and actually fail.
   The `uv` command is included in the allowlist.

8. **No skeptic interaction**: The auditor does not receive or depend on
   skeptic findings. They operate independently.
