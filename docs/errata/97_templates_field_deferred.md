# Errata: Spec 97 — ModeConfig.templates Field Temporarily Removed

**Spec:** 97_archetype_modes
**Section:** requirements.md (97-REQ-1.1), design.md (ModeConfig, ArchetypeEntry)

## Deviation (Now Resolved)

Spec 97 requires that `ModeConfig` have 8 optional override fields including
`templates` (97-REQ-1.1), and that `ArchetypeEntry` include a `templates`
field (design.md data types section).

A previous implementation pass (commit 9ae533a3) removed `templates` from
`ModeConfig` and never added it to `ArchetypeEntry`. This left `ModeConfig`
with 7 fields instead of the required 8, violating 97-REQ-1.1.

## Resolution

The `templates` field has been restored to both `ModeConfig` and
`ArchetypeEntry` with the correct defaults:

- `ModeConfig.templates: list[str] | None = None` — defaults to None (inherit)
- `ArchetypeEntry.templates: list[str] = field(default_factory=list)` — defaults to `[]`

`resolve_effective_config()` now applies the `templates` override when the
mode's `templates` is not None.

## Design Note: Profile Files vs. Embedded Templates

The `ArchetypeEntry.templates` field is **reserved for future use**. The
current mechanism for template loading uses **profile files** (spec 99):
markdown files in `.agent-fox/profiles/<archetype>.md` (project-level) or
package-embedded defaults. The embedded template list in `ArchetypeEntry` is
not consumed by any production code path at this time.

Future specs that implement mode-specific template overrides should use the
`templates` field in `ModeConfig` and `ArchetypeEntry.templates` to select
which profile variant to load, rather than adding new fields.

## Impact

- `ModeConfig` now has all 8 required fields per 97-REQ-1.1.
- `ArchetypeEntry` now has the `templates` field per the design document.
- All existing code is unaffected: `templates` defaults to an empty list in
  `ArchetypeEntry` and is unused by current production code.
- 97-REQ-1.1, 97-REQ-1.3, 97-REQ-1.5 are now fully satisfied.
