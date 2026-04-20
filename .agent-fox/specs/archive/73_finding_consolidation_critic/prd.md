# Cross-Category Finding Consolidation Critic

## Problem Statement

Night-shift's hunt scanner runs 8 independent categories in parallel, each
producing findings with a `group_key` for within-category grouping. However,
there is no cross-category awareness: a linter-debt finding and a dead-code
finding that both flag the same unused function create two separate GitHub
issues. This produces noise, wastes fix-session budget on duplicate work, and
fragments context that would be more actionable as a single issue.

Separately, categories sometimes produce low-confidence findings with
insufficient evidence — static-tool output was empty, and the AI speculated.
These false positives erode trust in night-shift's issue stream.

## Solution

Replace the existing `consolidate_findings()` function with an AI-powered
**critic stage** that sits between category output and issue creation. The
critic receives the full batch of findings from all categories, and in a single
AI pass:

1. **Deduplicates** findings across categories that share the same root cause
   or affect the same code.
2. **Validates** each finding against its evidence, dropping those that lack
   concrete proof.
3. **Calibrates severity** holistically — overlapping signals from multiple
   categories may raise (or lower) the effective severity.
4. **Synthesises** merged findings into coherent issue descriptions that
   capture the full cross-category picture.

```
Categories (parallel)
  → flat list[Finding]
    → Critic stage (single AI call)
      → validated, deduplicated list[FindingGroup]
        → Issue creation
```

### Minimum-Threshold Skip

When a scan produces fewer than 3 findings, the critic stage is skipped
entirely to avoid wasting an AI call on a trivial batch. The findings pass
through to issue creation using mechanical grouping (each finding becomes its
own group).

### Transparency & Auditability

Every critic decision is logged:

- **Merged**: which findings were combined, from which categories, and why.
- **Dropped**: which findings were removed and the reason (e.g., "no concrete
  evidence", "speculative").
- **Severity changed**: original vs. final severity with justification.

Logs use the existing `logger` at INFO level for merges/drops and DEBUG for
full critic reasoning.

## Critic Prompt Design

The critic receives a JSON array of all findings and a system prompt
instructing it to:

- Group findings by root cause, ignoring category boundaries.
- For each finding, check whether `evidence` contains concrete proof (tool
  output, code snippets, line numbers). If evidence is empty or purely
  speculative ("might be", "could potentially"), drop the finding.
- When merging findings from different categories, pick the highest severity
  among the group, unless the combined context suggests otherwise.
- Output a JSON array of consolidated finding groups, each with: merged title,
  synthesised description, final severity, union of affected files, combined
  evidence, and a list of original finding indices that were merged.
- Output a separate JSON array of dropped findings with reasons.

## Configuration

No new configuration knobs. The critic stage always runs when the finding count
meets the minimum threshold (≥ 3). This keeps the config surface small and
avoids a toggle that most users would never change.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 61_night_shift | 3 | 1 | Uses Finding dataclass and hunt pipeline from group 3 |

## Clarifications

- **Q: Should the critic drop findings?** A: Yes — findings lacking concrete
  evidence are dropped, not just flagged.
- **Q: Config toggle for the critic?** A: No toggle. Always runs when ≥ 3
  findings.
- **Q: Minimum threshold?** A: Yes — skip critic when < 3 findings.
- **Q: Replace or layer on existing consolidation?** A: Replace
  `consolidate_findings()` entirely.
- **Q: Transparency?** A: Yes — all merge/drop/severity decisions logged at
  INFO level.
