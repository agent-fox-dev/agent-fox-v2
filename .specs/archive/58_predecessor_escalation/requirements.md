# Requirements Document

## Introduction

This specification adds predecessor escalation to the orchestrator's
`retry_predecessor` mechanism. When a reviewer (Verifier, Auditor) repeatedly
fails and resets its predecessor to `pending`, the predecessor's escalation
ladder accumulates those failures. Once retries at the current tier are
exhausted, the predecessor escalates to a higher model tier. If all tiers are
exhausted, the predecessor blocks.

## Glossary

- **Predecessor**: The upstream node that a reviewer depends on, typically a
  Coder node. When a reviewer with `retry_predecessor=True` fails, the
  predecessor is reset to `pending` for re-execution.
- **Reviewer**: An archetype with `retry_predecessor=True` (Verifier, Auditor).
  When it fails, the predecessor is re-run instead of the reviewer itself.
- **Predecessor Ladder**: The escalation ladder associated with the predecessor
  node. Tracks both direct failures and reviewer-triggered resets.
- **Reviewer-Triggered Reset**: The act of setting a predecessor back to
  `pending` because a reviewer failed. This spec counts each such reset as a
  failure on the predecessor's escalation ladder.
- **Retry Budget**: The number of retries allowed at a given tier before
  escalation, controlled by `retries_before_escalation`.

## Requirements

### Requirement 1: Record Failure on Predecessor Ladder

**User Story:** As a project operator, I want reviewer-triggered resets to
count toward the predecessor's retry budget, so that the predecessor escalates
to a more capable model when repeated attempts at the current tier fail to
satisfy the reviewer.

#### Acceptance Criteria

1. [58-REQ-1.1] WHEN a reviewer with `retry_predecessor=True` fails AND the reviewer's ladder allows retry, THE system SHALL call `record_failure()` on the predecessor's escalation ladder.
2. [58-REQ-1.2] WHEN the predecessor's ladder is not exhausted after the recorded failure, THE system SHALL reset the predecessor to `pending` status.
3. [58-REQ-1.3] WHEN the predecessor's ladder escalates to a higher tier after the recorded failure, THE system SHALL reset the predecessor's retry counter at the new tier (built into `EscalationLadder`).

#### Edge Cases

1. [58-REQ-1.E1] IF the predecessor has no escalation ladder (e.g., assessment was skipped), THEN THE system SHALL create a ladder with the predecessor's archetype default tier as the starting tier and `ADVANCED` as the ceiling before recording the failure.

### Requirement 2: Block Predecessor on Exhaustion

**User Story:** As a project operator, I want the predecessor to block when
all tiers are exhausted, so that the system stops wasting resources on a task
that cannot be completed at any available model tier.

#### Acceptance Criteria

1. [58-REQ-2.1] WHEN the predecessor's ladder is exhausted after a reviewer-triggered failure, THE system SHALL block the predecessor and cascade-block its dependents.
2. [58-REQ-2.2] WHEN the predecessor is blocked due to ladder exhaustion, THE system SHALL record the outcome via `_record_node_outcome` with status `"failed"`.
3. [58-REQ-2.3] WHEN the predecessor is blocked, THE system SHALL NOT reset either the predecessor or the reviewer to `pending`.

#### Edge Cases

1. [58-REQ-2.E1] IF the predecessor is already at `ADVANCED` tier (ceiling) AND retries at `ADVANCED` are exhausted, THEN THE system SHALL block the predecessor.

### Requirement 3: Multiple Reviewers Share the Same Budget

**User Story:** As a project operator, I want failures from all reviewers
(Verifier, Auditor) to accumulate on the same predecessor ladder, so that the
escalation decision reflects the total signal, not just one reviewer.

#### Acceptance Criteria

1. [58-REQ-3.1] WHEN multiple reviewers with `retry_predecessor=True` fail for the same predecessor, THE system SHALL accumulate all failures on the same predecessor ladder.
2. [58-REQ-3.2] THE predecessor's escalation decision SHALL be based on the cumulative failure count, not per-reviewer counts.
