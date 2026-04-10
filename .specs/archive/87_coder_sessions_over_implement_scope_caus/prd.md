## Problem

Several coder sessions discovered that their assigned work was already implemented by a prior task group's coder:

- `04_cloud_gateway_client:3` — "Both validate_bearer_token() and validate_command_payload() were already implemented in src/command_validator.rs from a prior session" (1m 46s, verified tests pass, no new code)
- `04_cloud_gateway_client:4` — "The TelemetryState struct with new() and update() methods was already implemented in src/telemetry.rs from a prior session" (1m 29s, no new code)
- `04_cloud_gateway_client:5` — "No new commits on 'feature/04_cloud_gateway_client/5' relative to 'develop', skipping harvest" (3m 44s spent verifying)

The root cause: task group 1's coder (which wrote failing tests and stubs) actually implemented full working code for modules that were supposed to be stubs. Downstream task groups 3, 4, and 5 were assigned to implement those stubs but found them already done.

## Impact

- At least 3 sessions ($3-4 each) were wasted verifying already-complete work
- ~7 minutes of wall-clock time spent on no-ops
- The "no new commits" harvest skip confirms these sessions produced nothing

## Suggested Fix

1. **Add a pre-flight scope check** — before launching a coder session, compare the task group's expected deliverables against the current codebase state. If stub functions already have non-stub implementations, skip the task or reduce its scope.
2. **Enforce stub-only output for test-writing groups** — task group 1 (write failing tests) should be constrained to produce only type signatures and `todo!()`/`panic!("not implemented")` bodies. Add this as an archetype constraint.
3. **Add a "scope overlap" detection** at the graph level — if task group N's file list overlaps with task group M's, flag it for review
4. **Record "no-op" completions** distinctly in DuckDB — track how often sessions find their work already done, as a signal to improve task decomposition


## Source

Generated from: https://github.com/agent-fox-dev/agent-fox/issues/275
