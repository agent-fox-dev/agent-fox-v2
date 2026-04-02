# PRD: Fix Issue Ordering and Dependency Detection

## Summary

The night-shift fix pipeline currently processes `af:fix`-labeled issues in
whatever order the GitHub API returns them (newest first by default), with no
awareness of dependencies between issues. This leads to wasted work: fixing
issue #C might make issue #A obsolete, or issue #B might depend on a change
introduced by fixing #A first.

This spec adds intelligent ordering and dependency detection to the fix
pipeline using a three-tier approach:

1. **AI batch triage** (primary): Before processing any fixes, pass all
   `af:fix` issue descriptions to an ADVANCED-tier LLM that analyzes
   relationships and returns a recommended processing order with dependency
   edges and supersession candidates.
2. **Post-fix staleness check**: After completing each fix, re-evaluate
   remaining issues via an AI call and GitHub API verification to detect
   issues that became obsolete or were resolved as a side effect.
3. **Explicit reference parsing** (fallback): Parse issue bodies and GitHub
   relationship metadata (parent, blocks, is-blocked-by) for dependency
   signals. Used as a fallback when AI triage fails.

The base ordering (when no dependency information is available) is ascending
issue number — oldest issues first.

## Current Behavior

- `list_issues_by_label("af:fix")` returns issues in GitHub's default order
  (`sort=created`, `direction=desc` — newest first).
- Issues are processed sequentially in the returned order with no dependency
  analysis.
- No check is performed after fixing one issue to see if remaining issues
  are still relevant.

## Expected Behavior

### Phase 1: Issue Fetching

Issues are fetched with `sort=created&direction=asc` so the base ordering is
oldest-first (lowest issue number first).

### Phase 2: Dependency Resolution

Before processing any fixes, the engine builds a dependency graph:

1. **Explicit references**: Parse all issue bodies for textual dependency
   hints (`depends on #X`, `blocked by #X`, `after #X`, etc.) and query
   GitHub's relationship metadata (parent issues, blocks/is-blocked-by
   links) via the API.
2. **AI batch triage**: Send all issue titles, bodies, and explicit
   dependency edges to an ADVANCED-tier LLM. The LLM returns:
   - A recommended processing order (list of issue numbers)
   - Dependency edges with rationale
   - Supersession candidates (issues likely addressing the same root cause)
3. **Merge**: Combine explicit and AI-detected edges into a single
   dependency graph, then topologically sort. Explicit edges take precedence
   on conflict.

### Phase 3: Processing

Issues are processed in the resolved order (topological sort of dependency
graph, ties broken by issue number ascending).

### Phase 4: Post-Fix Staleness Check

After each fix completes:

1. Re-evaluate remaining unprocessed issues via an AI call: "Given the diff
   from fixing issue #C, are any of these remaining issues resolved or
   obsolete?"
2. Verify with the GitHub API: re-fetch remaining issues to check if any
   were closed or had labels removed.
3. For issues identified as obsolete: close them on GitHub with a comment
   explaining they were resolved by the fix for issue #C.
4. Remove obsolete issues from the processing queue.

### Fallback Chain

If AI triage fails (API error, timeout, unparseable response):
- Fall back to explicit-reference parsing for dependency edges.
- If no explicit references exist, process in issue-number order (ascending).

### Minimum Batch Size

AI triage is skipped when the batch contains fewer than 3 issues. For 1-2
issues, the overhead of an AI call outweighs the benefit — process in
issue-number order with explicit-reference parsing only.

## Scope

- **Engine layer**: Modify `_run_issue_check()` to build a dependency graph
  and process issues in resolved order.
- **Triage module**: New module for AI batch triage (prompt construction,
  response parsing, graph building).
- **Staleness module**: New module for post-fix staleness evaluation.
- **Reference parser**: New module for parsing explicit dependency references
  from issue text and GitHub metadata.
- **Platform layer**: Add `sort` and `direction` params to
  `list_issues_by_label()`. Add method to query GitHub issue relationships
  if available.
- **Config**: Triage-related settings (enable/disable, model tier).

## Clarifications

1. **AI model tier**: The batch triage step uses ADVANCED tier for reliable
   inter-issue reasoning.
2. **Triage output**: The AI suggests a concrete processing order (not just
   edges). The engine uses this order, validated against explicit edges.
3. **Staleness check**: Uses an AI call to re-evaluate remaining issues
   against the fix diff, plus GitHub API verification (re-fetch to check
   closed/label-removed state).
4. **Obsolete issue handling**: Close the issue on GitHub with a comment
   explaining which fix resolved it.
5. **Dependency syntax**: Parse textual hints broadly (not just exact
   patterns) and also use GitHub's relationship metadata (parent, blocks,
   is-blocked-by) when available via the API.
6. **Triage failure**: Falls back to explicit-reference edges, then to
   issue-number ordering. Never blocks processing entirely.
7. **Cycle detection**: If dependencies form a cycle, break it by starting
   with the oldest issue (lowest number) in the cycle, then re-evaluate.
8. **Minimum batch size**: Skip AI triage for batches of fewer than 3 issues.
   Use explicit-reference parsing + issue-number order instead.
