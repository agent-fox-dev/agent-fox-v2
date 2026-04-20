# Errata 112: Budget Exhaustion Semantics

**Spec:** 112_sleep_time_compute
**Date:** 2026-04-20

## Discrepancy

`112-REQ-2.4` states:

> IF the remaining budget drops to zero or below before a task begins, THEN
> THE system SHALL skip that task and record a `"budget_exhausted"` entry in
> the error list.

`TS-112-9` contradicts this:

> task_a costs 0.9, task_b costs 0.5; budget = 1.0 → task_b skipped.

After task_a (cost 0.9) runs, remaining budget = 0.1, which is **above zero**.
Per REQ-2.4, task_b should NOT be skipped. Yet TS-112-9 asserts task_b IS
skipped.

## Resolution

The test spec (TS-112-9) implies the `SleepComputer` checks each task's
**estimated cost** against the remaining budget before running it, not simply
whether the remaining budget is zero. If `task.cost_estimate > remaining`, the
task is skipped.

The `SleepTask` mock in the tests exposes a `cost_estimate: float` attribute.
The implementation in Group 2 MUST add a `cost_estimate` property to the
`SleepTask` protocol so `SleepComputer` can skip tasks whose estimated cost
exceeds the remaining budget.

## Impact

- Group 2 (task 2.3): Add `cost_estimate: float` to `SleepTask` protocol.
- `SleepComputer.run()`: Skip task if `task.cost_estimate > budget_remaining`,
  not only when `budget_remaining <= 0`.
- `SleepContext.budget_remaining` should reflect `min(ctx.budget_remaining,
  config.max_cost)` at the start of `SleepComputer.run()`.
- The `112-REQ-2.4` wording "drops to zero or below" should be interpreted as
  the effective pre-task budget check: skip when remaining < task estimate.

## Test Impact

`test_budget_exhaustion` (TS-112-9) and `test_all_tasks_budget_exhausted`
(TS-112-E9) encode the intended behavior as per the test spec. They will pass
once the implementation uses `cost_estimate`-based skipping.
