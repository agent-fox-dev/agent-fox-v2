# Night-Shift Mode

## Purpose and Placement

Night-shift is an autonomous maintenance daemon that runs continuously,
discovering technical debt and fixing it without human intervention. While the
spec-driven pipeline ([Parts 1–3](01-spec-authoring.md)) implements features
from authored specifications, night-shift operates in the opposite direction:
it finds problems in the existing codebase and generates the specifications
needed to fix them.

The two modes are complementary. The spec pipeline builds new capabilities
by executing a human-authored plan. Night-shift maintains the codebase by
detecting degradation (stale dependencies, dead code, linter violations,
test coverage gaps) and either filing issues for human triage or autonomously
fixing them. The fix pipeline reuses the same session infrastructure — Claude
agents in isolated workspaces — but with automatically generated specs rather
than human-authored ones.

---

## Conceptual Model

Night-shift operates as a two-phase loop:

1. **Hunt**: Scan the codebase for problems across multiple categories, filter
   and consolidate findings with an LLM critic, deduplicate against known
   issues, and create GitHub issues for novel findings.

2. **Fix**: Pick up issues labelled for automatic repair, determine a safe
   processing order using dependency analysis, and execute a three-agent
   pipeline (Skeptic → Coder → Verifier) for each issue.

These two phases run on independent timers. The hunt scan runs less frequently
(default: every four hours) because it is expensive — it executes static
analysis tools and calls an LLM for consolidation. The issue check runs more
frequently (default: every fifteen minutes) because it is cheap — it queries
GitHub for labelled issues and dispatches fix pipelines.

Both phases fire immediately on startup (so the first scan and fix attempt
happen without waiting for the timer interval) and then repeat at their
configured intervals.

---

## The Hunt Phase

### Categories

A hunt scan dispatches multiple independent category scanners in parallel.
Each category knows how to find a specific class of problem:

| Category | What It Finds |
|---|---|
| Linter Debt | Ruff, mypy, and other linter warnings that have accumulated |
| Dead Code | Unreachable functions, unused imports, classes with no callers |
| Test Coverage | Modules, functions, and code paths lacking adequate tests |
| Dependency Freshness | Outdated packages, known vulnerabilities, stale pins |
| Deprecated API | Usage of deprecated functions, classes, or patterns |
| Documentation Drift | Stale docstrings, inaccurate README sections, missing API docs |
| TODO/FIXME | Comments flagged as temporary that have become permanent |
| Quality Gate | Failing project checks (tests, linters, type checkers, builds) |

Categories share a common structure: they execute static analysis tools against
the codebase, then pass the raw output to an LLM for interpretation and
classification. The LLM transforms tool output into structured findings with
titles, descriptions, severity levels, affected files, suggested fixes, and
supporting evidence.

The Quality Gate category is the most sophisticated. It discovers available
checks from project configuration files (test suites, linters, type checkers,
build commands), executes each one with a per-check timeout, and routes
failures through an LLM for root-cause analysis. If the LLM is unavailable,
it falls back to mechanical findings derived directly from the tool output.

All categories are enabled by default and can be individually disabled via
configuration.

### The Critic

Raw category output can be noisy — multiple findings may stem from the same
root cause, evidence may be insufficient, or severity may be miscalibrated.
The critic is an LLM-powered consolidation stage that addresses this.

For small batches (one or two findings), the critic is bypassed and each
finding becomes its own group. For larger batches, the critic receives all
findings and performs four operations:

- **Grouping**: Findings with a common root cause are merged into a single
  group. A cluster of "unused import" findings across related modules becomes
  one issue rather than twenty.
- **Validation**: Findings with insufficient evidence are dropped. The critic
  requires concrete proof (tool output, code snippets, metrics) — speculation
  is rejected.
- **Calibration**: Severity is adjusted based on combined context. A single
  minor linter warning stays minor; twenty of them in the same module may
  indicate a systemic problem worth escalating.
- **Accounting**: Every input finding must appear in exactly one output group
  or in the explicit "dropped" list with a reason. The critic cannot silently
  lose findings.

If the LLM call fails or returns malformed output, the critic falls back to
mechanical grouping: each finding becomes its own group with no consolidation.
This fail-open design ensures that findings are never silently discarded due
to infrastructure problems.

### Deduplication

Before creating issues, the system checks whether each finding group has
already been reported. Deduplication uses a fingerprint — a truncated SHA-256
hash computed from the category name and the sorted list of affected files.
The fingerprint is deterministic: the same problem in the same files always
produces the same hash, even across different scan runs.

Fingerprints are embedded as HTML comments in issue bodies. To check for
duplicates, the system fetches all open issues with the `af:hunt` label,
extracts fingerprints from their bodies, and filters out finding groups whose
fingerprint matches an existing issue.

This approach is intentionally coarse. Two findings that affect the same files
in the same category are considered duplicates even if their descriptions
differ. This is a tradeoff: it risks occasional false deduplication (two
genuinely different problems in the same files) in exchange for avoiding
duplicate issues, which are more disruptive to triage workflows.

If the platform API is unavailable, deduplication is skipped and all findings
are reported. This fail-open behavior prefers noise over silence.

### Issue Creation

Each surviving finding group becomes a GitHub issue with the `af:hunt` label.
The issue body contains a synthesized title, a markdown description, the list
of affected files, and the embedded fingerprint. The title comes from the
critic's consolidation; the body aggregates evidence from all findings in the
group.

---

## The Fix Phase

### Issue Selection and Triage

The fix phase queries GitHub for open issues with the `af:fix` label. In
`--auto` mode, every `af:hunt` issue is automatically labelled `af:fix`,
creating a fully autonomous discover-and-fix loop. Without `--auto`, a human
must review hunt issues and apply the `af:fix` label to approve automated
repair.

When three or more fixable issues exist, the system performs batch triage
using an LLM. The triage analysis serves three purposes:

**Dependency detection.** Some issues depend on others — fixing a type error
may require first fixing the deprecated API usage that introduced it. The
triage stage identifies these edges from three sources: explicit text references
in issue bodies ("depends on," "blocked by," "after," "requires"), GitHub
cross-references from the timeline API, and LLM-inferred dependencies based
on the issue descriptions.

**Supersession detection.** Some issues become obsolete when another is fixed.
The triage stage identifies these pairs and closes the obsolete issue before
processing begins, preventing wasted work.

**Processing order.** The dependencies form a graph. Kahn's topological sort
(with tie-breaking by issue number) produces a safe processing order that
respects dependencies. If the dependency graph contains cycles, the system
breaks them before sorting.

For fewer than three issues, triage is skipped and issues are processed in
creation-date order.

### The Fix Pipeline

Each issue passes through a three-stage pipeline:

1. **Skeptic review.** A Skeptic agent reads the issue body and assesses
   whether the fix is feasible, whether there are hidden risks, and whether
   the scope is well-defined.

2. **Coder implementation.** A Coder agent implements the fix on an isolated
   branch. The branch name is derived from the issue title
   (`fix/{sanitized-slug}`). The system prompt contains the full issue body;
   the task prompt directs the agent to fix the described problem.

3. **Verifier validation.** A Verifier agent confirms that the fix resolves
   the issue without introducing regressions.

All three sessions share the same fix branch, which is created from the
current `develop` HEAD. After the pipeline completes successfully, the fix
branch is harvested into `develop` using the same merge cascade as the
spec-driven pipeline (fast-forward, rebase, merge commit, merge agent).
The originating issue is then closed with a comment pointing to the fix branch.

If any stage fails, the issue receives a failure comment with the branch name
for manual recovery. The branch is preserved — the work done before the
failure is not discarded.

### Spec Construction

The fix pipeline generates a lightweight in-memory spec from the issue rather
than writing spec files to disk. This spec contains a task prompt (assembled
from the issue title and body), system context (the full issue body for
reference), and the fix branch name. This avoids polluting `.specs/` with
ephemeral repair specifications that do not represent lasting feature work.

---

## Engine Lifecycle

### Startup

On startup, the engine validates that a platform is configured (GitHub is
required for issue management), initializes the platform client, and runs both
the hunt scan and issue check immediately. This ensures that the first
maintenance cycle happens without waiting for the timer interval.

### Event Loop

The engine runs a one-second tick loop. On each tick, it accumulates elapsed
time for both the hunt timer and the issue-check timer. When a timer exceeds
its configured interval, the corresponding phase fires and the timer resets.
This is simpler and more predictable than a scheduler-based approach — the
engine always knows exactly when the next phase will fire.

### Cost and Session Limits

Night-shift enforces its own cost ceiling, set conservatively at 50% of the
configured maximum. This headroom accounts for the unpredictability of
autonomous operation — a hunt scan that discovers many issues could trigger
a cascade of fix pipelines, each consuming tokens. The 50% threshold provides
a safety margin.

Session limits are also enforced. Both limits trigger graceful shutdown:
the engine finishes any in-flight work, emits final statistics, and exits.

### Graceful Shutdown

The engine responds to SIGINT and SIGTERM. The first signal sets a shutdown
flag that prevents new phases from starting and allows in-flight work to
complete. A second signal exits immediately with code 130. This matches the
two-stage shutdown behavior of the spec-driven orchestrator.

### State

The engine maintains runtime state: cumulative cost, session count, issues
created, issues fixed, and hunt scans completed. This state is transient —
it exists only for the lifetime of the daemon process. Persistent state lives
in the platform (GitHub issues with labels and fingerprints) and the
repository (code changes on `develop`).

---

## Staleness Detection

After completing a round of fixes, the engine checks whether any remaining
open `af:hunt` issues have become stale. A fix to one issue may resolve
problems reported in another — for example, fixing a deprecated API usage
might also resolve the linter warning that flagged it. Staleness detection
re-evaluates open issues against the current codebase state and closes those
that no longer apply.

---

## Interaction with the Spec Pipeline

Night-shift and the spec pipeline are designed to coexist but not to run
simultaneously. Night-shift operates on `develop` and creates fix branches
that merge back into `develop`. The spec pipeline also targets `develop`.
Running both concurrently would create merge contention.

The intended workflow is:

- During active development: run the spec pipeline (`agent-fox code`) to
  implement features.
- During off-hours: run night-shift (`agent-fox night-shift`) to maintain
  code health.
- The merge lock ensures that if both do run concurrently, they serialize
  their merge operations rather than corrupting the branch.

Night-shift issues are visible in GitHub alongside human-filed issues. A human
reviewing the repository sees a unified view of both feature work (from specs)
and maintenance work (from night-shift), with clear labels (`af:hunt` for
discovered issues, `af:fix` for approved repairs) distinguishing the two.

---

*Previous: [Execution and Archetypes](03-execution-and-archetypes.md)*
