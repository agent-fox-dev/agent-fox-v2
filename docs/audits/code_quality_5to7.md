Agent-Fox Evolution: version_5 → version_6 → version_7

At a Glance

┌────────────────────────────────────────────────────────────────┬──────────┬──────────────────────────┬───────────────────────────────┐
│                             Metric                             │    v5    │            v6            │              v7               │
├────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────┼───────────────────────────────┤
│ Unique commits                                                 │ 57       │ 100                      │ 123                           │
├────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────┼───────────────────────────────┤
│ Rust #[test] functions                                         │ 98       │ 118                      │ 94                            │
├────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────┼───────────────────────────────┤
│ Go test files                                                  │ 46       │ 53                       │ 43                            │
├────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────┼───────────────────────────────┤
│ Errata documented                                              │ 10       │ 14                       │ 6                             │
├────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────┼───────────────────────────────┤
│ Net code vs v5                                                 │ baseline │ +7K lines                │ -3K lines                     │
├────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────┼───────────────────────────────┤
│ Specs fully complete                                           │ 9/9      │ 8/9 (spec 06 tests stub) │ 8/9 (spec 06 tests unchecked) │
├────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────┼───────────────────────────────┤
│ All three branches compile, and core make test passes on each. │          │                          │                               │
└────────────────────────────────────────────────────────────────┴──────────┴──────────────────────────┴───────────────────────────────┘

The Qualitative Story

version_6 is the highest-quality implementation. version_5 has the most complete architecture in a few areas, and version_7 — despite being "latest" — introduces several regressions.

---
What v6 Got Right (That Others Didn't)

1. Most thorough testing. v6 has 20+ more Rust tests than v7 and 7 more Go test files. Crucially, v6 added broker error path tests in safety.rs (what happens when the DATA_BROKER call itself fails), plus boundary tests (speed = 0.99). v5 and v7 trust the unwrap_or chain works but never test it.
2. State machine transition validation. v6's update-service StateManager includes an is_valid_transition() function that rejects illegal state moves (e.g., RUNNING → DOWNLOADING). v5 and v7 accept any transition — and v7 even has a dead InvalidTransition error variant with no validation code behind it.
3. Review-driven quality cycle. v6's commit history shows fix(07): address review findings for concurrent installs, fix(08): strengthen integration tests — evidence of a review/QA loop that v5 and v7 lack. This explains the extra errata files (14 vs 6–10) and the higher test count.
4. Modern Go idioms. v6 uses strings.CutPrefix, typed context keys with accessor functions (TokenFromContext()), and json.NewEncoder — cleaner API surface than v5's manual string splitting or v7's exported constant keys.
5. Better mock design. v6's test mocks capture actual arguments (vehicle_id, zone_id, session_id), allowing tests to verify correct data propagation. v5 and v7 only capture call counts.

---
What v5 Got Right (That Others Lost)

1. Complete event loop architecture. v5 is the only branch with a SessionCommand enum + run_event_loop() function in the parking-operator-adaptor. This provides the serialized event processing guarantee required by spec 08 (REQ-9.1/9.2). v6 and v7 implement individual processing functions without the coordinating
loop.
2. Most complete proto definition. v5's kuksa/val.proto most closely matches the real Kuksa Databroker v1 API — includes GetServerInfo, array types, ValueRestriction, and full metadata. v6 switched to a radically simplified v2-style proto (only Subscribe + PublishValue RPCs), and v7 uses a trimmed v1.
3. Defensive Makefile. v5 uses foreach loops with explicit module lists, making test scope clearly auditable. v6's cargo test --workspace (no exclusions) risks running stub tests; v7 takes the middle ground with surgical --exclude flags.
4. Geofence accuracy. v5's distanceToSegment applies cos(midLat) scaling to longitude when projecting points onto polygon edges — correct geodetic math. v6 also does this. v7 omits the cosine correction entirely, projecting in raw degrees — a real accuracy bug at non-equatorial latitudes.

---
version_7 Regressions

Despite being the latest agent-fox output, v7 has concrete regressions:

┌────────────────────────────────┬──────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│             Issue              │   Severity   │                                                                                      Detail                                                                                       │
├────────────────────────────────┼──────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ /health requires auth          │ Bug          │ v7's auth middleware has no health-endpoint bypass — /health returns 401. v5 and v6 correctly skip auth for it.                                                                   │
├────────────────────────────────┼──────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ No lon/lat scaling in geofence │ Bug          │ distanceToSegment projects in raw degrees. At Munich's latitude (~48°N), 1° longitude ≈ 75 km vs 1° latitude ≈ 111 km. Proximity matching will over-report lon distances by ~48%. │
├────────────────────────────────┼──────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Fewest tests                   │ Quality gap  │ 94 Rust tests vs v6's 118. No error-path testing in safety validation. Only 5 safety tests vs v6's 11.                                                                            │
├────────────────────────────────┼──────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Dead code in state manager     │ Design smell │ StateError::InvalidTransition variant exists, but transition() accepts anything. Misleading API.                                                                                  │
├────────────────────────────────┼──────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Spec 06 TG1 skipped            │ Process gap  │ Task checkboxes all unchecked — the test-first step was skipped for cloud-gateway.                                                                                                │
├────────────────────────────────┼──────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ No run_event_loop              │ Spec gap     │ No serialized event processing function in parking-operator-adaptor (was present in v5).                                                                                          │
├────────────────────────────────┼──────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Fewest errata                  │ Doc gap      │ Only 6 errata files vs v6's 14 — fewer known issues documented, not fewer issues existing.                                                                                        │
└────────────────────────────────┴──────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

---
What Improved Consistently v5 → v6 → v7

- Go module paths converged from github.com/sdv-demo/... (v5) to github.com/rhadp/... (v6, v7).
- Proto file organization moved from flat (proto/kuksa/val.proto) to versioned dirs (proto/kuksa/val/v1/).
- Test module organization in Rust improved — v7 extracts mocks into shared testing modules instead of inline definitions, reducing test duplication.
- Makefile proto generation improved — v7 uses --go_opt=module=... for proper module-aware paths.

---
Comparative Verdict

┌───────────────────────────────────┬──────┬───────────┬─────────┐
│             Dimension             │ Best │ Runner-up │ Weakest │
├───────────────────────────────────┼──────┼───────────┼─────────┤
│ Test coverage & rigor             │ v6   │ v5        │ v7      │
├───────────────────────────────────┼──────┼───────────┼─────────┤
│ Spec compliance tracking (errata) │ v6   │ v5        │ v7      │
├───────────────────────────────────┼──────┼───────────┼─────────┤
│ Architectural completeness        │ v5   │ v6        │ v7      │
├───────────────────────────────────┼──────┼───────────┼─────────┤
│ Code correctness (bugs)           │ v6   │ v5        │ v7      │
├───────────────────────────────────┼──────┼───────────┼─────────┤
│ Code conciseness / leanness       │ v7   │ v6        │ v5      │
├───────────────────────────────────┼──────┼───────────┼─────────┤
│ Modern idioms                     │ v6   │ v7        │ v5      │
├───────────────────────────────────┼──────┼───────────┼─────────┤
│ State machine rigor               │ v6   │ v5        │ v7      │
└───────────────────────────────────┴──────┴───────────┴─────────┘

Bottom line: Agent-fox v6 produced the most robust, well-tested, well-documented implementation. v5 was more architecturally complete in specific areas (event loop, proto fidelity). v7 is the leanest but traded quality for brevity — it introduced two real bugs (auth bypass, geofence accuracy), dropped significant
test coverage, and skipped process steps. The evolution from v5→v6 was a clear improvement; v6→v7 was a regression in quality despite being the newest agent version.