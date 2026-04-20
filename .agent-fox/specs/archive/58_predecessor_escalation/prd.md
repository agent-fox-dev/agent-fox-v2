# PRD: Predecessor Escalation on Reviewer-Triggered Retries

## Problem

When an archetype with `retry_predecessor=True` (Verifier, Auditor) fails, it
resets its predecessor (typically the Coder) back to `pending`. The Coder
re-runs, but always at its original model tier — its escalation ladder is never
touched. This means:

1. The Coder runs at STANDARD and succeeds.
2. The Verifier runs, finds the output insufficient, and fails.
3. `retry_predecessor` resets the Coder to `pending`.
4. The Coder runs again at STANDARD (same tier), produces similar output.
5. The Verifier fails again.
6. Repeat until the **Verifier's** ladder exhausts → Verifier blocks.

The Coder never escalates because from its ladder's perspective, it never
failed. The reviewer is the one failing, but the root cause is the Coder's
output quality. The Verifier eventually blocks, and the task is stuck — despite
there being a higher-capability model available.

## Solution

When `retry_predecessor` fires, record a failure on the **predecessor's**
escalation ladder. This way:

- Each reviewer-triggered reset counts toward the Coder's retry budget.
- After `retries_before_escalation` resets at the current tier, the Coder
  escalates to the next tier (e.g., STANDARD → ADVANCED).
- The retry counter resets after escalation (built into `EscalationLadder`).
- If the Coder exhausts all tiers (ADVANCED ceiling), it blocks.

Multiple reviewers (Verifier + Auditor) accumulate on the same predecessor
ladder, using the same `retries_before_escalation` budget.

## Clarifications

- **Q: Same or separate retry budget?** Same `retries_before_escalation` value.
- **Q: Multiple reviewers accumulate?** Yes, on the same predecessor ladder.
- **Q: Coder at ADVANCED ceiling, still failing?** Coder blocks after retries
  exhausted at ADVANCED.
- **Q: Predecessor ladder doesn't exist?** Create one defensively with the
  predecessor's archetype default as starting tier and ADVANCED ceiling.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 57_archetype_model_tiers | 2 | 2 | Tier ceiling always ADVANCED (from task group 2 which implements the ceiling fix in `_assess_node`) |
