Branch Lineage (Important Context)

The three branches are not independent rewrites — they share a common lineage:

baseline (specs only, no code)
└─→ [shared implementation: specs 01-09, ~123 commits]
        └─→ common ancestor (cee50d3)
            ├─→ version_6  (+38 commits: review hardening)
            └─→ version_7  (+61 commits: re-implementation of specs 02-08)
                    └─→ version_8  (+36 commits: race fixes, API migration, deeper testing)

- version_7 builds on the shared ancestor, re-implementing several specs from scratch with a cleaner task-group workflow
- version_8 builds directly on version_7's code, then adds hardening fixes
- version_6 branches off the same shared ancestor but takes its own hardening path
- The version_7 branch tip was then reset (code deleted) for a fresh agent-fox v3.3.1 test — its code lives at commit b7766bc

Quantitative Comparison

┌────────────────────────────────┬─────────────────┬───────────────────────┬─────────────────┐
│             Metric             │    version_6    │ version_7 (pre-reset) │    version_8    │
├────────────────────────────────┼─────────────────┼───────────────────────┼─────────────────┤
│ Files                          │ 255             │ 221                   │ 254             │
├────────────────────────────────┼─────────────────┼───────────────────────┼─────────────────┤
│ Total insertions               │ 53,061          │ 43,315                │ 52,421          │
├────────────────────────────────┼─────────────────┼───────────────────────┼─────────────────┤
│ Unique commits (from baseline) │ 161             │ 184                   │ 220             │
├────────────────────────────────┼─────────────────┼───────────────────────┼─────────────────┤
│ Fix commits                    │ 15              │ 4                     │ 26              │
├────────────────────────────────┼─────────────────┼───────────────────────┼─────────────────┤
│ Test commits                   │ 36              │ 36                    │ 46              │
├────────────────────────────────┼─────────────────┼───────────────────────┼─────────────────┤
│ Errata documents               │ 14              │ 0                     │ 11              │
├────────────────────────────────┼─────────────────┼───────────────────────┼─────────────────┤
│ Rust LOC (services)            │ ~9,078          │ ~8,607                │ ~9,716          │
├────────────────────────────────┼─────────────────┼───────────────────────┼─────────────────┤
│ Task completion                │ 481/505 (95.2%) │ 464/505 (91.9%)       │ 481/506 (95.1%) │
└────────────────────────────────┴─────────────────┴───────────────────────┴─────────────────┘

What Changed Version to Version

version_6 (earliest agent-fox)

Approach: Shared implementation + 38 review-fix commits. Heavy focus on "address review findings" and "strengthen test assertions."

Character:
- Lots of fix(...): address review findings and test(...): strengthen commits — suggests a workflow where an external reviewer (likely a human or review skill) flagged issues that the agent then fixed iteratively
- 14 errata documents produced — the agent documented spec divergences thoroughly
- Resubscription logic, startup ordering fixes, and property test bodies all added as afterthoughts
- Code comments tend toward documenting how, not just why

Weaknesses:
- Uses Kuksa v1 API exclusively (no v2 migration)
- Signal handler in locking-service uses raw tokio::select! — susceptible to signal loss during command processing (the v8 race condition)
- distanceToSegment in geo.go does apply cos(lat) correction — but this was present from the shared ancestor, not a v6 innovation
- No TOCTOU fix in update-service's container monitor

version_7 (middle agent-fox)

Approach: Re-implemented specs 02-08 from the common ancestor with a clean, incremental "task group" workflow (feat → test → wiring verification per spec).

Character:
- Much cleaner commit narrative: feat(07): implement config and adapter modules (task group 2), feat(07): implement state manager (task group 3), etc.
- Systematic progression through task groups rather than fix-it-after-review cycles
- Only 4 fix commits vs 15 (v6) or 26 (v8) — got things more right the first time
- Zero errata documents — did not document spec divergences
- Memory.md accumulated useful gotchas (tracing defaults to stdout, skeleton test expectations)

Weaknesses:
- Fewer edge-case tests (no property test bodies for many TS-XX-PY cases)
- distanceToSegment lacks cos(lat) correction — a genuine geometric bug at Munich's latitude (~33% distance overestimation on diagonal edges)
- Same signal handler race as v6 (no watch channel pattern)
- Same TOCTOU vulnerability in container monitor
- Lower task completion rate (91.9% vs 95.2%)
- The branch was ultimately reset/abandoned — the code at the tip is just specs with no implementation

version_8 (latest agent-fox)

Approach: Builds on version_7's code, then adds 36 commits of deep hardening and API migration.

Character:
- The most fix-commits (26) — but these are proactive race-condition and correctness fixes, not review-response patches
- Migrated cloud-gateway-client and parking-operator-adaptor to Kuksa v2 API
- Signal handler race fix: Uses tokio::sync::watch channel so SIGTERM during command processing is never lost — a subtle and important correctness improvement
- TOCTOU fix in update-service: transition_from() atomically validates expected state before transitioning
- cos(lat) correction added to distanceToSegment — fixes the geometric bug from v7
- Signal handler pre-creation: Creates signal handlers before server bind to prevent SIGTERM-arrival race
- 11 errata documents with detailed technical rationale

Improvements over prior versions:
1. Race condition prevention (watch channels, atomic transitions, pre-bound signal handlers)
2. API modernization (Kuksa v2)
3. More thorough test coverage (46 test commits, parameterized property tests for sensors)
4. Content-Type verification on error responses (401/403)
5. Store timeout race condition fix in cloud-gateway
6. Spurious telemetry suppression on duplicate signal values

Qualitative Assessment

Did code quality improve?

Yes, measurably. The progression is:

┌───────────────────────────────┬────────────────────────────────────┬─────────────────────────────┬────────────────────────────────────────────┐
│           Dimension           │                 v6                 │             v7              │                     v8                     │
├───────────────────────────────┼────────────────────────────────────┼─────────────────────────────┼────────────────────────────────────────────┤
│ Correctness (race conditions) │ Has signal loss bug, no TOCTOU fix │ Same bugs                   │ Both fixed                                 │
├───────────────────────────────┼────────────────────────────────────┼─────────────────────────────┼────────────────────────────────────────────┤
│ API currency                  │ Kuksa v1 only                      │ Kuksa v1 only               │ v1 + v2 migration                          │
├───────────────────────────────┼────────────────────────────────────┼─────────────────────────────┼────────────────────────────────────────────┤
│ Geometric accuracy            │ cos(lat) present (from ancestor)   │ Bug: missing cos(lat)       │ Fixed properly                             │
├───────────────────────────────┼────────────────────────────────────┼─────────────────────────────┼────────────────────────────────────────────┤
│ Test sophistication           │ Review-driven strengthening        │ Clean but shallower         │ Proactive property tests, wire-level tests │
├───────────────────────────────┼────────────────────────────────────┼─────────────────────────────┼────────────────────────────────────────────┤
│ Documentation                 │ 14 errata (thorough)               │ 0 errata (gap)              │ 11 errata (thorough)                       │
├───────────────────────────────┼────────────────────────────────────┼─────────────────────────────┼────────────────────────────────────────────┤
│ Commit discipline             │ Reactive (fix review findings)     │ Proactive (task-group flow) │ Proactive (targeted fixes)                 │
└───────────────────────────────┴────────────────────────────────────┴─────────────────────────────┴────────────────────────────────────────────┘

The real story

The evolution shows agent-fox learning from each iteration:

- v6 produced working code but needed many review-driven corrections. The agent was reactive — it built, got feedback, fixed. The code works but has known race conditions.
- v7 showed improved workflow discipline (clean task-group progression, fewer fixes needed), but cut corners on edge-case testing and spec documentation. It was also the version that got abandoned — the codebase was reset, suggesting the approach wasn't satisfactory enough to continue.
- v8 represents the most mature agent. It inherited v7's clean architecture, then proactively identified and fixed subtle concurrency bugs that neither v6 nor v7 caught. The signal handler watch-channel pattern, the TOCTOU atomic transition, and the Kuksa v2 migration show an agent that reasons about failure modes rather than just implementing features. The errata documentation returned, and the test coverage is the deepest of the three.

Bottom line: v8 is the clear winner — not just in quantity but in the kind of work it does. It finds and fixes bugs that the earlier agents didn't even recognize as problems.