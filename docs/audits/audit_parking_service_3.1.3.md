Analysis of agent-fox 3.1.3 Run (parking-fee-service)

Run stats: 83 sessions, 9 specs, $147.36 cost, 4h13m wall time, 35 merges to develop.

---
1. Anomalies

Agent trace file missing on EVERY session — This is the most glaring issue. The warning Agent trace file not found: .agent-fox/audit/agent_20260421_155837_af2c18.jsonl, falling back to alternative transcript source fires after every single one of 83 sessions. The file for the run ID is never written. Knowledge
extraction falls back to an alternative source (likely the raw Claude Code transcript), meaning the trace-based extraction path is dead code in practice. This should be investigated — the agent_trace.py module has a bug or a missing prerequisite that prevents the JSONL file from being created.

Event loop shutdown crash — Two RuntimeError: Event loop is closed tracebacks from httpx AsyncClient.aclose() at the very end of the run (lines 1583-1642). This is a cleanup ordering issue: the asyncio event loop is closed before the httpx connection pools are drained. Harmless to the run output but indicates the
shutdown sequence in the engine isn't awaiting all HTTP clients before closing the loop.

Embedder absent during consolidation — 12 consolidated facts stored without embeddings (No embedder configured; consolidated fact ... stored without embedding). The embedder was available during the run itself (629 embeddings exist, vector retrieval was active for all 83 sessions), but was somehow gone by the time
end-of-run consolidation runs. These 12 facts are invisible to vector search until re-embedded. This suggests the embedder lifecycle is tied to something that gets cleaned up before consolidation.

Double git ingestion — At the end of the run, commits are ingested twice: 117 commits, then 112 commits (lines 1568, 1671). This looks like a redundant second pass, possibly a bug where end-of-run cleanup re-runs the same ingestion pipeline.

Steering file permanently skipped — Every session logs Steering file contains only placeholder content, skipping. The steering mechanism is a dead feature for this run — no project-level directives were ever applied.

---
2. Archetype Effectiveness

Reviewer — genuinely working. 18 sessions at $8.49 total. Produced 372 review findings (41 critical, 69 major, 33 minor, 229 observation). The findings are substantive: the audit-reviewer caught that no test executed skeleton binaries, that make check used --no-run (compile-only) instead of running real tests, that
spec image versions contradicted each other. The pre-reviewer flagged a knowledge base fact that was actively wrong (exit code 0 vs 1 for mock sensors). One spec (05_parking_fee_service) got a clean PASS verdict, showing the reviewer can give a green light when warranted. The reviewer archetype is the clearest win.

Coder — working, but with efficiency overhead. 56 sessions at $132.05 (89.6% of total cost). All 56 produced commits. Evidence of real work: fixed binary exit codes, rewrote Makefile targets, fixed integration test polling loops, added hundreds of tests, created errata for spec/implementation divergences. However, a
large number of sessions report "was already fully implemented" and then just verify + make minor additions. The task-group-per-session model means coder sessions must re-orient themselves to code that's already done, spending $2-5 each to re-read and confirm. This is the cost of the sequential task-group approach.

Verifier — working, honest. 9 sessions at $6.82 total. Produced 298 verification results (293 PASS, 5 FAIL). The 5 failures are real: Go binaries printing usage instead of version, Rust sensor binaries exiting code 2 instead of 0, proto generated code not importable by Go modules. The verifier isn't rubber-stamping
— it's catching real gaps that coders missed or accepted.

Blocking system — untested. Only 3 blocking evaluations occurred, none triggered (threshold of 3 critical findings never reached). The blocking mechanism didn't influence the run.

---
3. Knowledge System — Mostly Theater

The retrieval is indiscriminate. Every single one of 83 sessions received exactly 50 facts. This is a hard cap, not intelligent selection. Whether the session is implementing a Rust CLI sensor or a Go HTTP gateway, it gets the same fixed-size injection of 50 facts. There's no evidence that retrieval quality varies
by session — it's "top-50 by vector similarity, always."

The facts are mostly generic wisdom. 340 of 603 active facts (56%) are category "git" with no spec association. Content like "use exponential backoff for external service connections" or "serialize parallel test execution that mutates env vars using a global mutex." These are things any competent model would derive
from reading the code. They don't carry genuine cross-session intelligence — they're restating patterns already visible in the codebase.

The entity graph is structurally empty. 2,116 entities with 1,996 edges, but every single edge has relationship type "contains." No call-graph edges, no dependency edges, no "uses" or "implements" relationships. It's a flat parent→child index from static analysis — a glorified file/symbol listing. The graph
machinery exists but the analysis doesn't produce meaningful relationships.

Review insights are discarded. Knowledge extraction is skipped for all reviewer and verifier sessions (Skipping LLM knowledge extraction for reviewer archetype). This means the reviewer's most valuable observations (missing test coverage, spec contradictions, incorrect behaviors) are NOT fed into the knowledge base.
The coder in a subsequent session doesn't benefit from the reviewer's findings through the knowledge system — it only sees them through the review findings table, which is a separate mechanism.

Where it provides genuine value. A handful of "gotcha" and "decision" facts are legitimately useful across sessions:
- Clap exits code 2 for validation errors, not code 1 as specs require
- make proto needs mkdir -p gen before protoc
- make check should run actual tests, not compile-only checks
- When specs conflict across task groups, the foundational spec takes precedence

These ~20 facts could be a simple list in a markdown file. The elaborate infrastructure (384-dimensional embeddings, vector similarity search, causal chains, contradiction detection, dedup lifecycle, compaction) is engineering sophistication that doesn't produce proportionally better outcomes. The contradiction
detector fired twice in the entire run. The dedup rate is 6% (38/641). The causal chains (206 entries) are tracked but there's no evidence they influence agent behavior.

Bottom line: The knowledge system functions correctly as machinery — embeddings work, retrieval works, dedup works, contradiction detection works. But the content is mostly noise: generic patterns that don't tell agents anything they couldn't derive from reading the current code. The few genuinely
cross-session-valuable insights (~5% of facts) are drowned in a fixed blob of 50 facts injected indiscriminately into every session.

---

Archetype Session Overview (v3.1.3 run)

┌───────────┬───────────────────┬──────────┬──────────────┬───────────────┬──────────────┬────────────┬──────────────────┬────────────┬──────────────────┐
│ Archetype │       Model       │ Sessions │ Input Tokens │ Output Tokens │ Total Tokens │ Total Cost │ Avg Cost/Session │ Total Time │ Avg Time/Session │
├───────────┼───────────────────┼──────────┼──────────────┼───────────────┼──────────────┼────────────┼──────────────────┼────────────┼──────────────────┤
│ coder     │ claude-opus-4-6   │ 56       │ 414,331      │ 860,612       │ 1,274,943    │ $132.05    │ $2.36            │ 438.5 min  │ 7m 50s           │
├───────────┼───────────────────┼──────────┼──────────────┼───────────────┼──────────────┼────────────┼──────────────────┼────────────┼──────────────────┤
│ reviewer  │ claude-sonnet-4-6 │ 18       │ 51,121       │ 208,651       │ 259,772      │ $8.49      │ $0.47            │ 79.6 min   │ 4m 25s           │
├───────────┼───────────────────┼──────────┼──────────────┼───────────────┼──────────────┼────────────┼──────────────────┼────────────┼──────────────────┤
│ verifier  │ claude-sonnet-4-6 │ 9        │ 43,805       │ 92,617        │ 136,422      │ $6.82      │ $0.76            │ 48.4 min   │ 5m 23s           │
├───────────┼───────────────────┼──────────┼──────────────┼───────────────┼──────────────┼────────────┼──────────────────┼────────────┼──────────────────┤
│ Total     │                   │ 83       │ 509,257      │ 1,161,880     │ 1,671,137    │ $147.36    │ $1.78            │ 566.5 min  │ 6m 49s           │
└───────────┴───────────────────┴──────────┴──────────────┴───────────────┴──────────────┴────────────┴──────────────────┴────────────┴──────────────────┘

Key observations:

- Coder dominates: 89.6% of cost, 76.3% of tokens, 67.5% of sessions. It runs on Opus (the most expensive model) while reviewer and verifier run on Sonnet.
- Output-heavy: Output tokens outnumber input tokens 2.3:1 overall, and 2.1:1 for coders. The agents are writing a lot of code and explanations.
- Reviewer is the cheapest archetype: $0.47/session average — high value relative to the critical/major findings it produces.
- Auxiliary costs not tracked in session table: The haiku-4-5 token usage for knowledge extraction, fact dedup, causal link analysis, consolidation, and git ingestion is separate and not individually attributed to sessions. From the log, these calls are roughly 600K-800K additional tokens across the run.

---

The Verify-Only Problem

21 of 56 coder sessions (37.5%) touched no files. They consumed $35.94 — 27.2% of total coder spend — just to read the codebase and conclude everything was
already done.

The verify-only rate rises sharply with task group position:

┌───────────────┬─────────┬─────────────┬──────────┐
│  Task Group   │ Changed │ Verify-Only │ % Verify │
├───────────────┼─────────┼─────────────┼──────────┤
│ TG 1 (tests)  │ 8       │ 1           │ 11%      │
├───────────────┼─────────┼─────────────┼──────────┤
│ TG 2          │ 6       │ 3           │ 33%      │
├───────────────┼─────────┼─────────────┼──────────┤
│ TG 3          │ 4       │ 5           │ 56%      │
├───────────────┼─────────┼─────────────┼──────────┤
│ TG 5 (wiring) │ 3       │ 6           │ 67%      │
└───────────────┴─────────┴─────────────┴──────────┘

Two distinct causes

1. Earlier task groups over-implement. Look at 01_project_setup: TG 1-3 made changes, then TG 4 through TG 7 were all verify-only ($7.39 wasted). The TG 1
coder ("write failing spec tests") didn't just write failing tests — it implemented the full solution. Everything after that was re-orientation for nothing.

Similarly, 05_parking_fee_service TG 1 changed code, then TG 2 (model/config/store) and TG 3 (geo module) found everything done. Prior sessions had
implemented the lot.

2. "Wiring verification" TGs are coders running on Opus. These are pure verification by design — their job is to confirm all requirements are met and all
tests pass. But the engine treats them identically to implementation task groups: same archetype (coder), same model (Opus), same $8 budget. There are 9
"wiring verification" + 1 "checkpoint" TGs across the specs, costing $29.58 total.

Is this the cost of quality?

Partly, but it's over-priced quality. The data shows that 6 of 13 wiring/verification TGs did make small changes (tasks.md updates, errata docs, minor test
fixes). So there IS a quality tail from running these sessions. But:

- The same verification work is already being done by the verifier archetype (Sonnet, $0.76/session average). The verifier found 5 genuine FAIL verdicts.
- The same verification work is being done by the reviewer archetype (Sonnet, $0.47/session average). The reviewer found 41 critical and 69 major findings.
- The coder-on-Opus is the most expensive way to verify ($1.71/session average for verify-only sessions vs $0.76 for a verifier).

The engine architecture drives this

From the source code (explored in engine/engine.py, engine/session_lifecycle.py, engine/graph_sync.py):

- No pre-flight check exists. The _check_launch() function checks cost limits and retry limits, but never checks whether a task group's work is already done.
Every pending node whose dependencies are completed gets launched unconditionally.
- No post-harvest skip. After a coder session produces no changes, the system still runs knowledge extraction, causal link analysis, and records the session
at full cost.
- Wiring verification nodes are indistinguishable from implementation nodes in the plan graph. They use archetype coder with no mode flag. The title contains
"Wiring verification" but that's not used for routing decisions.

What could be changed

Three interventions, from easiest to hardest:

A. Route "wiring verification" TGs to verifier archetype (Sonnet). The plan graph title already identifies them. A simple heuristic during plan generation or
graph injection — if the last TG for a spec is titled "Wiring verification" or "Checkpoint," assign archetype=verifier instead of coder. Savings: ~$19.70
(13.3% of total run cost). This is actually already happening in this run for some specs — the verifier sessions at the end are exactly this role, they just
run in addition to the coder wiring verification.

B. Add a lightweight pre-flight check before launching coder sessions. Before launching an Opus session, run a Haiku-tier check (~$0.02):
- Are all subtask checkboxes for this task group already marked complete in tasks.md?
- Do the related tests pass? (a make test or targeted test command)
- Are there unresolved critical/major review findings for this specific task group?

If checkboxes are done AND tests pass AND no unresolved findings → skip the coder session entirely, or downgrade to a verifier session. This would catch most
of the 21 verify-only sessions.

C. Tighter scoping in prompts for early TGs. The TG 1 prompt ("write failing spec tests") should be more constrained to prevent the coder from writing full
implementations. This is a prompt engineering issue rather than an engine issue, but it's the root cause of why later TGs find everything done. The tradeoff:
if TG 1 is forced to only write failing tests, total session count might stay the same but each session does real work instead of re-orientation.

Combined impact estimate: Interventions A+B together would reduce the $35.94 verify-only waste to roughly $3-5 (a few Haiku pre-flight checks + Sonnet
verifier sessions for wiring TGs), saving ~$30 or ~20% of total run cost.

  ---