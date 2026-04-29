# PRD: Git Stack Hardening and Fail-Fast Workspace Validation

## Problem Statement

When the repository working tree contains untracked files that overlap with
files a coding session will produce, the harvest (squash-merge) step fails
after the session has already completed — wasting all tokens spent on the
coding work. The failure is non-recoverable through retries because the
workspace state doesn't change between attempts, yet the engine's escalation
ladder consumes all retry budget before finally blocking the node.

In a real-world incident (af-hub v3.5.2), this pattern caused:

- **$29.61 in wasted compute** across 5 failed sessions (all coding work
  succeeded, but every harvest failed).
- **21 of 23 nodes cascade-blocked** from a single harvest failure.
- **Futile retries** that repeated the identical failure 3 times per task.
- **A stale run** left in "running" status that was never properly terminated.
- **Noisy logs** with spurious "blocked -> blocked" transition warnings.

The root cause was untracked files left on disk after a manual repository reset
(`git rm --cached` style deletion). The harvest logic correctly detected the
divergent files and refused to overwrite them, but the engine had no mechanism
to (a) detect this before spending tokens, (b) classify the error as
non-retryable, or (c) offer automatic remediation.

## Goals

1. **Fail fast**: Detect workspace issues before dispatching coding sessions.
   Don't spend tokens on work that can't be harvested.
2. **Classify errors**: Distinguish workspace-state errors (non-retryable) from
   coding/merge errors (retryable). Route each to the correct handler.
3. **Auto-remediate**: Offer an opt-in `--force-clean` mode that cleans
   conflicting untracked files automatically.
4. **Harden the full git stack**: Improve develop sync observability, run
   lifecycle completeness, and cascade blocking robustness.
5. **Actionable diagnostics**: Every workspace error message tells the user
   exactly what's wrong and how to fix it.

## Non-Goals

- Changing the conservative default behavior of harvest (protecting local work
  when `--force-clean` is not enabled).
- Auto-resolving merge conflicts (already handled by merge_agent in spec 45).
- Modifying worktree isolation logic (already hardened in spec 80).
- Adding new git operations or changing branch naming conventions.

## Design Decisions

1. **Full git stack scope**: This spec covers harvest hardening, develop sync
   audit trail, run lifecycle cleanup, and cascade blocking improvements — not
   just the harvest path.
2. **Opt-in auto-clean via `--force-clean`**: The flag removes conflicting
   untracked files both at run startup (pre-run health check) and during
   harvest. Conservative (fail-and-report) remains the default.
3. **Minor fixes included**: Run lifecycle completeness (stale "running"
   detection) and idempotent cascade blocking (suppress blocked->blocked
   warnings) are in scope.

## Source

Source: Input provided by user via interactive prompt, informed by analysis of
af-hub v3.5.2 run log (`docs/audits/af-hub_3.5.2_1.log`) and knowledge database
(`.agent-fox/knowledge.duckdb`).
