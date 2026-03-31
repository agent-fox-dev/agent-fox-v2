# Night Hunting -- Autonomous Maintenance Mode

## Problem Statement

Small teams have zero bandwidth for maintenance. Dependencies rot. TODOs pile
up. Deprecation warnings accumulate silently. Test coverage erodes on the code
that was changed last week. No tool currently does proactive, scheduled,
autonomous maintenance that covers everything -- not just dependency bumps.

## Solution

Night Shift mode -- a continuously-running autonomous maintenance daemon that
scans the codebase on a timed schedule, identifies maintenance issues using both
static tooling and AI-powered analysis, creates platform issues for each
finding, and optionally auto-fixes them using the full archetype pipeline.

```
# Run night-shift (runs continuously until interrupted)
agent-fox night-shift

# Run with auto-fix (auto-assigns af:fix label to discovered issues)
agent-fox night-shift --auto
```

## Hunt Categories

All categories are active from v1. The system is pluggable -- each category is
a dedicated agent with a configurable prompt, producing findings in a
standardised output format. New categories can be added by defining a prompt
template and validation agent.

| Category              | What It Does                                                                 |
| --------------------- | ---------------------------------------------------------------------------- |
| Dependency freshness  | Detects outdated dependencies; generates update findings with test validation |
| TODO/FIXME resolution | Clusters related TODOs and generates findings to address them                |
| Test coverage gaps    | Identifies files changed recently with declining test coverage               |
| Deprecated API usage  | Detects use of deprecated functions/methods and generates migration findings  |
| Linter debt           | Batches lint warnings into addressable groups                                |
| Dead code detection   | Identifies unreachable code and generates cleanup findings                    |
| Documentation drift   | Detects functions/modules changed since their docstrings were written         |

### Detection Approach

Each hunt category uses a two-phase detection approach:

1. **Static tooling**: Execute tests, run linters, static analysis tools if
   configured or available in the project.
2. **AI-powered analysis**: Dedicated Claude agents analyse code for deeper
   issues beyond what static tools can catch.

Categories can execute in parallel where independent.

## Workflow

### Continuous Loop

Night-shift runs continuously until interrupted (SIGINT). On startup it
validates that the platform is configured and access tokens are available;
it aborts if not.

Two timed activities run on configurable intervals:

- **Issue check** (default every 15 min): poll the platform for open issues
  with the `af:fix` label and queue them for fixing.
- **Hunt scan** (default every 4 h): run all enabled hunt categories against
  the codebase, consolidate findings, and create platform issues.

### Discovery Flow

1. Run all enabled hunt categories (parallel where possible).
2. Each category produces findings in the standardised finding format.
3. Group findings by root cause, then by category. When in doubt, create one
   issue per finding.
4. For each finding/group, create a platform issue with detailed analysis and
   suggested fix.
5. If `--auto` is set, automatically assign the `af:fix` label to the created
   issue.

### Fix Flow

For each issue with the `af:fix` label:

1. Document implementation details as comments on the issue.
2. Create a feature branch: `fix/{descriptive-name}`.
3. Build a lightweight in-memory spec (enough for the fix engine, aligned with
   the normal coding process where possible).
4. Execute fix using the full archetype pipeline (skeptic -> coder -> verifier).
5. Create one PR per fix, linked to the issue.
6. Update the issue with links to the branch and PR.

## Engine

A new dedicated engine handles the night-shift loop, borrowing from the
existing `fix` command implementation where sensible. The existing `fix`
command's quick-repair feature is replaced by an investigation agent that
creates a proper issue and allows for orderly fixing.

Processing of discovered issues and `af:fix`-labelled issues uses the same fix
pipeline for consistency.

## Platform Abstraction

- GitHub support in v1.
- API abstraction layer (protocol) that allows adding GitLab, Gitea, and other
  platforms later.
- Use only the platform's REST APIs -- no local tools or MCP servers.
- Platform must be configured with a valid access token; abort if not.

## Configuration

Night-shift honours the existing `max_cost` and `max_sessions` orchestrator
config for cost control. New configuration options:

```toml
[night_shift]
issue_check_interval = 900      # seconds (default 15 min)
hunt_scan_interval = 14400      # seconds (default 4 h)

[night_shift.categories]
dependency_freshness = true
todo_fixme = true
test_coverage = true
deprecated_api = true
linter_debt = true
dead_code = true
documentation_drift = true
```

## Branch & PR Strategy

- One feature branch per fix: `fix/{descriptive-name}`.
- One PR per fix, linked to the originating issue.
- Full archetype pipeline for each fix.

## Lifecycle

- Runs continuously until interrupted (SIGINT).
- Graceful shutdown: completes the current operation, then exits.
- Exit code 0 on graceful shutdown, 130 on interrupt.
