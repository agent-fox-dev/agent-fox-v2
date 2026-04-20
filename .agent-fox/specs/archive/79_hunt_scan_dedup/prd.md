# PRD: Cross-Iteration Hunt Scan Deduplication

## Problem

Night-shift runs hunt scans on a timed interval (default: every 4 hours). Each
scan independently detects maintenance issues, consolidates them into
FindingGroups, and creates one GitHub issue per group. If a finding from
iteration N remains unfixed at iteration N+1, the same finding is detected again
and a **duplicate issue is created**. There is no mechanism to detect that an
equivalent open issue already exists.

Over a weekend with no human intervention, the same unfixed problem could
produce 12+ duplicate issues (one per 4-hour scan across 48 hours).

## Solution

Before creating issues from hunt scan findings, compute a **deterministic
fingerprint** for each FindingGroup, check it against fingerprints embedded in
existing open issues previously created by night-shift, and skip creation if a
match is found.

### Key Design Decisions

1. **Matching via fingerprint hash**: Each FindingGroup receives a SHA-256
   fingerprint computed from its `category` and sorted `affected_files`. The
   fingerprint is embedded in the issue body as an HTML comment so it survives
   round-trips through the platform API.

2. **Only open issues created by night-shift**: Hunt-created issues are tagged
   with an `af:hunt` label. The dedup gate fetches only open `af:hunt` issues,
   ignoring manually created issues and closed issues. This means a
   fix-then-regress scenario correctly creates a new issue (the old one is
   closed, so its fingerprint is not in the candidate set).

3. **Platform-agnostic**: The dedup logic operates through the existing
   `PlatformProtocol` interface (`list_issues_by_label`, `create_issue`). No
   platform-specific code is added.

4. **Fetch-once, match in-memory**: At the start of each issue-creation phase,
   all open `af:hunt` issues are fetched in a single API call. Fingerprints are
   extracted from their bodies and collected into a set. Each FindingGroup's
   fingerprint is checked against this set in O(1) time.

5. **Silent skip with logging**: When a duplicate is detected, the system logs
   the skip at INFO level (group title, matching issue number). No comments are
   posted on the existing issue.

## Clarifications

- **Fingerprint stability**: The fingerprint is derived from `category` (fixed
  per hunt category) and `sorted(affected_files)` (deterministic from static
  tooling). AI-generated fields like `title` and `description` are excluded
  because they are non-deterministic across runs. If the set of affected files
  changes between scans (e.g., a file is deleted), the fingerprint changes and a
  new issue is created — this is correct because the problem scope has changed.

- **Critic grouping variance**: The AI critic may group findings differently
  across runs. If the critic produces different groupings, the affected_files
  sets differ, and the fingerprints differ. This may produce a partial duplicate
  in rare cases. This is acceptable — it is better to occasionally create a
  near-duplicate than to suppress a legitimate new finding.

- **No retroactive tagging**: Existing hunt-created issues (created before this
  feature) will not have the `af:hunt` label or embedded fingerprint. The dedup
  gate will not match them. This is acceptable — the first scan after deployment
  may create duplicates of pre-existing issues, but subsequent scans will be
  deduplicated.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 61_night_shift | 5 | 2 | Uses `create_issues_from_groups()` and `build_issue_body()` from group 5 which first implements issue creation |
| 73_finding_consolidation_critic | 4 | 2 | Uses `consolidate_findings()` integrated in group 4 which wires the critic into the engine |
