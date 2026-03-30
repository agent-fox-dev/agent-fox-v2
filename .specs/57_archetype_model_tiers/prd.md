# PRD: Archetype Model Tier Defaults

## Problem

The current archetype model tier defaults are inverted relative to actual
complexity needs. The Coder archetype defaults to `ADVANCED` (Opus) while
review archetypes (Skeptic, Oracle, Verifier) default to `STANDARD` (Sonnet).
In practice, review archetypes perform more nuanced analysis — finding
architectural flaws, validating correctness properties, verifying test
coverage — and benefit more from the most capable model. Coders execute
well-defined task groups with concrete instructions and perform well with
the standard model.

Additionally, the escalation ladder's `tier_ceiling` is currently derived
from the archetype's `default_model_tier`, which means archetypes starting
at `STANDARD` cannot escalate on retry. The ceiling must always be `ADVANCED`
so that any archetype can escalate when retries are exhausted at the current
tier.

## Requirements

1. **Change registry defaults**: Update `ARCHETYPE_REGISTRY` so that Skeptic,
   Oracle, and Verifier default to `ADVANCED`. Change Coder to `STANDARD`.
   All other archetypes (Auditor, Librarian, Cartographer, Coordinator) remain
   at `STANDARD`.

2. **Fix tier ceiling**: The escalation ladder's `tier_ceiling` must always be
   `ADVANCED`, regardless of the archetype's starting tier. This ensures that
   `STANDARD`-starting archetypes (now including Coder) can escalate to
   `ADVANCED` on repeated failures.

3. **Preserve configurability**: Per-archetype model tier overrides via
   `config.archetypes.models` must continue to work. Config overrides take
   precedence over registry defaults. Document the new defaults.

4. **Retry-then-escalate for STANDARD agents**: When a `STANDARD`-tier agent
   fails, the existing `EscalationLadder` mechanism retries N times at
   `STANDARD`, then escalates to `ADVANCED`. This behavior is already
   implemented; the spec must verify it works correctly with the new defaults.

5. **No escalation beyond ADVANCED**: Archetypes starting at `ADVANCED`
   (Skeptic, Oracle, Verifier) retry at the same tier and then block. There is
   no tier above `ADVANCED` to escalate to. This is the existing behavior and
   must be verified.

## Clarifications

- **Q: Tier ceiling for STANDARD agents?** Always `ADVANCED`.
- **Q: ADVANCED agents that fail?** Retry at `ADVANCED`, then block.
- **Q: Auditor/Coordinator/Librarian/Cartographer?** Stay at `STANDARD`.
- **Q: Registry change vs config change?** Registry change (code), overridable
  via `config.toml`.
- **Q: Should `tier_ceiling` be configurable?** No. Always `ADVANCED`.
