# Errata: Triage Archetype Absorption (Spec 100)

## Affected Specs
- Spec 82 (`82_triage_archetype`) — triage archetype registration
- Spec 57 (`57_archetype_model_tiers`) — archetype model tier defaults
- Spec 100 (`100_maintainer_archetype`) — maintainer archetype definition

## Divergence 1: Model Tier Downgrade (ADVANCED → STANDARD)

**Spec 82 (82-REQ-1.1)** defined the triage archetype with `default_model_tier="ADVANCED"`.

**Spec 100 (100-REQ-1.2)** defines `maintainer:hunt` with `default_model_tier="STANDARD"`.

This is a deliberate functional change: triage AI calls will use the STANDARD
model tier instead of ADVANCED. The Skeptic review flagged this as a potential
quality degradation (see memory facts). The implementation follows the spec as
written; a future spec may re-evaluate the tier choice if triage quality is
impacted.

**Impact:** Tests in `test_archetype_registry_82.py` and
`test_archetype_tiers_props.py` have been updated to reflect STANDARD tier for
maintainer:hunt.

## Divergence 2: Triage Removed from ARCHETYPE_REGISTRY

**Spec 82 (82-REQ-1.1)** required `"triage"` to be present in
`ARCHETYPE_REGISTRY`.

**Spec 100 (100-REQ-2.1)** requires `"triage"` NOT to be present in
`ARCHETYPE_REGISTRY`.

Spec 100 supersedes spec 82 on this point. The `get_archetype("triage")`
fallback behavior (100-REQ-1.E1) ensures callers using the old archetype name
gracefully fall back to `"coder"` with a warning.

**Impact:** `tests/unit/test_archetype_registry_82.py` updated to verify the
migration (triage absent, maintainer present). `tests/unit/session/test_archetypes.py`
and `tests/property/test_archetype_tiers_props.py` updated accordingly.

## Divergence 3: _ADVANCED_ARCHETYPES Set in Spec 57 Tests

**Spec 57** property tests assumed `_ADVANCED_ARCHETYPES = {"triage"}`.

After triage removal, `_ADVANCED_ARCHETYPES = set()`. The maintainer archetype
uses STANDARD tier, so it belongs in `_STANDARD_ARCHETYPES`.
