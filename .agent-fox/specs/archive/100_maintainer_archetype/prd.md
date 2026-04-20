# PRD: Maintainer Archetype

## Problem Statement

The v2 architecture has no formal "maintainer" archetype. Analysis tasks are
split across ad-hoc mechanisms:

- **Triage** is a standalone archetype used in the nightshift pipeline to
  order and prioritize issues. It has no conceptual relationship to the other
  archetypes despite being analysis-focused.
- **Hunt scanning** runs through `HuntScanner` with hardcoded categories,
  producing findings that flow to the critic and then to GitHub issues. The
  hunt phase has no archetype — it runs programmatically.
- **Knowledge extraction** does not exist as an archetype-driven process.
  Audit events flow to `SinkDispatcher` for reporting but no LLM-driven
  fact extraction happens post-session.

The v3 architecture consolidates these into a single **Maintainer** archetype
with two modes:

- **Hunt mode**: Read-only analysis producing structured work items. Absorbs
  the conceptual role of the triage archetype and provides an archetype
  identity for the nightshift analysis phase.
- **Knowledge extraction mode**: Post-session fact extraction from session
  transcripts into the knowledge store.

## Goals

1. Define a `maintainer` archetype in the registry with `hunt` and
   `extraction` modes.
2. Absorb the `triage` archetype into `maintainer:hunt` mode.
3. Wire the nightshift hunt phase to use the `maintainer:hunt` archetype
   identity for session execution (triage AI calls).
4. Stub the `extraction` mode with a well-defined interface for future
   implementation of LLM-driven knowledge extraction.
5. Define appropriate permissions per mode (read-only + shell for hunt,
   no filesystem access for extraction).
6. Remove the `triage` archetype from the registry.

## Non-Goals

- Implementing the full knowledge extraction pipeline (session transcript
  parsing, fact extraction, knowledge store writes). This spec defines the
  archetype and interface; the actual extraction logic is future work.
- Modifying the HuntScanner categories or critic logic.
- Changing the fix pipeline (which uses coder:fix from Spec 98).

## Design Decisions

1. **Hunt mode absorbs triage.** The triage archetype's template, allowlist,
   and model tier configuration become the hunt mode's configuration.
   The `run_batch_triage()` function is updated to reference
   `maintainer:hunt` instead of `triage`.
2. **Extraction mode is stubbed.** The mode is defined in the registry with
   the correct permissions, and `load_profile("maintainer")` includes
   extraction guidance, but the actual extraction pipeline (reading session
   transcripts, calling the LLM, writing facts) is not implemented. The
   stub is documented and tracked.
3. **Hunt mode permissions: read-only + shell.** Matches the current triage
   allowlist (ls, cat, git, wc, head, tail) plus static analysis tools.
4. **Extraction mode permissions: no filesystem, no shell.** Extraction
   reads transcripts via the orchestrator API (not filesystem) and writes
   facts via the knowledge store API. The archetype has no tool access
   in the sandbox.
5. **Default STANDARD model tier** for both modes. Hunt analysis and
   knowledge extraction are structured tasks that don't require ADVANCED.
   The triage archetype was ADVANCED but that was inherited from v2's
   conservative defaults.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 97_archetype_modes | 2 | 2 | Uses ModeConfig and ArchetypeEntry.modes for mode definitions |
| 98_reviewer_consolidation | 2 | 2 | Triage removal depends on registry cleanup pattern established in Spec 98 |
