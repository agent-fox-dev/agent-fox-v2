# Implementation Plan: Archetype Profiles

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan adds archetype profiles and 3-layer prompt assembly in six task
groups. Group 1 writes failing tests. Group 2 creates the profile loading
module. Group 3 creates default profiles. Group 4 updates prompt assembly.
Group 5 adds custom archetype support and init --profiles. Group 6 verifies
wiring.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/session/test_profiles.py tests/unit/session/test_prompt_layers.py tests/unit/cli/test_init_profiles.py tests/property/test_profile_properties.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/session/test_profiles.py`
    - Profile loading tests: project override, default fallback, frontmatter stripping (TS-99-2, TS-99-3, TS-99-11, TS-99-12)
    - Edge cases: missing profile, None project_dir (TS-99-E2, TS-99-E6)
    - _Test Spec: TS-99-2, TS-99-3, TS-99-11, TS-99-12, TS-99-E2, TS-99-E6_

  - [x] 1.2 Create `tests/unit/session/test_prompt_layers.py`
    - 3-layer assembly tests: order, missing CLAUDE.md (TS-99-1, TS-99-E1)
    - _Test Spec: TS-99-1, TS-99-E1_

  - [x] 1.3 Create `tests/unit/templates/test_default_profiles.py`
    - Default profile existence and structure (TS-99-4, TS-99-5)
    - _Test Spec: TS-99-4, TS-99-5_

  - [x] 1.4 Create `tests/unit/cli/test_init_profiles.py`
    - Init creates files, preserves existing, creates dirs (TS-99-6, TS-99-7, TS-99-E3)
    - _Test Spec: TS-99-6, TS-99-7, TS-99-E3_

  - [x] 1.5 Create `tests/unit/core/test_custom_archetypes.py`
    - Custom archetype detection, permission preset, task group, edge cases (TS-99-8, TS-99-9, TS-99-10, TS-99-E4, TS-99-E5)
    - _Test Spec: TS-99-8, TS-99-9, TS-99-10, TS-99-E4, TS-99-E5_

  - [x] 1.6 Create `tests/property/test_profile_properties.py`
    - Property tests: layer order, override precedence, completeness, idempotence, permission inheritance (TS-99-P1 through TS-99-P5)
    - _Test Spec: TS-99-P1 through TS-99-P5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Implement profile loading module
  - [x] 2.1 Create `agent_fox/session/profiles.py`
    - `load_profile(archetype, project_dir)` function
    - Check project dir first, package default second
    - Strip YAML frontmatter
    - Log warning for missing profiles
    - `has_custom_profile(name, project_dir)` function
    - _Requirements: 99-REQ-5.1, 99-REQ-5.2, 99-REQ-5.3, 99-REQ-5.E1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/session/test_profiles.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/session/profiles.py`

- [x] 3. Create default profiles
  - [x] 3.1 Create `agent_fox/_templates/profiles/` directory
    - _Requirements: 99-REQ-2.1_

  - [x] 3.2 Create default profile for coder
    - 4 sections: Identity, Rules, Focus areas, Output format
    - Incorporate content from current coding.md template
    - _Requirements: 99-REQ-2.2, 99-REQ-2.3_

  - [x] 3.3 Create default profile for reviewer
    - 4 sections with mode-specific guidance noted
    - Incorporate content from current reviewer.md template
    - _Requirements: 99-REQ-2.2, 99-REQ-2.3_

  - [x] 3.4 Create default profiles for verifier and maintainer
    - 4 sections each
    - Verifier from current verifier.md template
    - Maintainer as new profile (placeholder until Spec 100)
    - _Requirements: 99-REQ-2.2, 99-REQ-2.3_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest -q tests/unit/templates/test_default_profiles.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`

- [x] 4. Update prompt assembly to 3-layer
  - [x] 4.1 Update `build_system_prompt()` in `session/prompt.py`
    - Accept `project_dir` parameter
    - Layer 1: Load CLAUDE.md (omit if missing)
    - Layer 2: Load profile via `load_profile()`
    - Layer 3: Assemble task context (spec artifacts, knowledge, findings)
    - Concatenate with clear delineation
    - _Requirements: 99-REQ-1.1, 99-REQ-1.2, 99-REQ-1.3, 99-REQ-1.E1, 99-REQ-1.E2_

  - [x] 4.2 Update `NodeSessionRunner._build_prompts()` to pass project_dir
    - Thread repo_root as project_dir to build_system_prompt
    - _Requirements: 99-REQ-1.1_

  - [x] 4.V Verify task group 4
    - [x] Spec tests pass: `uv run pytest -q tests/unit/session/test_prompt_layers.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/session/`

- [x] 5. Custom archetypes and init --profiles
  - [x] 5.1 Add `CustomArchetypeConfig` to config schema
    - `permissions: str` field with validation
    - `archetypes.custom` dict in ArchetypesConfig
    - _Requirements: 99-REQ-4.2_

  - [x] 5.2 Update `get_archetype()` for custom archetype fallback
    - Accept optional project_dir and config parameters
    - Check ARCHETYPE_REGISTRY first
    - Check for custom profile + permission preset
    - Default to coder permissions if no preset
    - Raise error for invalid preset
    - _Requirements: 99-REQ-4.1, 99-REQ-4.3, 99-REQ-4.4, 99-REQ-4.E1, 99-REQ-4.E2_

  - [x] 5.3 Implement `init_profiles()` function
    - Copy default profiles to `.agent-fox/profiles/`
    - Create directory structure if needed
    - Skip existing files
    - Return list of created paths
    - _Requirements: 99-REQ-3.1, 99-REQ-3.2, 99-REQ-3.3, 99-REQ-3.E1_

  - [x] 5.4 Add `--profiles` flag to `init` CLI command
    - Wire init_profiles to CLI
    - _Requirements: 99-REQ-3.1_

  - [x] 5.V Verify task group 5
    - [x] Spec tests pass: `uv run pytest -q tests/unit/core/test_custom_archetypes.py tests/unit/cli/test_init_profiles.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/`

- [x] 6. Wiring verification

  - [x] 6.1 Trace every execution path from design.md end-to-end
    - Path 1: Prompt with project profile
    - Path 2: Prompt with default profile fallback
    - Path 3: Custom archetype session
    - Path 4: Init --profiles
    - Confirm no stub functions in the chain
    - _Requirements: all_

  - [x] 6.2 Verify return values propagate correctly
    - load_profile returns string consumed by build_system_prompt
    - init_profiles returns list of paths
    - get_archetype returns ArchetypeEntry used by session runner
    - _Requirements: all_

  - [x] 6.3 Run the integration smoke tests
    - TS-99-SMOKE-1: Prompt with project profile
    - TS-99-SMOKE-2: Custom archetype session
    - TS-99-SMOKE-3: Init then load
    - _Test Spec: TS-99-SMOKE-1 through TS-99-SMOKE-3_

  - [x] 6.4 Stub / dead-code audit
    - Search touched files for stubs and TODO markers
    - Verify old template loading code is removed or adapted
    - _Requirements: all_

  - [x] 6.5 Cross-spec entry point verification
    - Verify build_system_prompt is called with project_dir from session_lifecycle
    - Verify get_archetype accepts project_dir from callers
    - _Requirements: all_

  - [x] 6.V Verify wiring group
    - [x] All smoke tests pass
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live (traceable in code)
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ tests/`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 99-REQ-1.1 | TS-99-1 | 4.1 | test_prompt_layers.py::test_3_layer_order |
| 99-REQ-1.2 | TS-99-2, TS-99-3 | 4.1 | test_profiles.py::test_project_override, test_default_fallback |
| 99-REQ-1.3 | TS-99-2 | 4.1 | test_profiles.py::test_project_override |
| 99-REQ-1.E1 | TS-99-E1 | 4.1 | test_prompt_layers.py::test_missing_claude_md |
| 99-REQ-1.E2 | TS-99-E2 | 2.1 | test_profiles.py::test_missing_profile |
| 99-REQ-2.1 | TS-99-4 | 3.1-3.4 | test_default_profiles.py::test_defaults_exist |
| 99-REQ-2.2 | TS-99-5 | 3.2-3.4 | test_default_profiles.py::test_profile_structure |
| 99-REQ-2.3 | TS-99-4 | 3.2-3.4 | test_default_profiles.py::test_defaults_exist |
| 99-REQ-3.1 | TS-99-6 | 5.3 | test_init_profiles.py::test_init_creates_files |
| 99-REQ-3.2 | TS-99-7 | 5.3 | test_init_profiles.py::test_init_preserves_existing |
| 99-REQ-3.3 | TS-99-6 | 5.3 | test_init_profiles.py::test_init_creates_files |
| 99-REQ-3.E1 | TS-99-E3 | 5.3 | test_init_profiles.py::test_init_creates_dirs |
| 99-REQ-4.1 | TS-99-8 | 5.2 | test_custom_archetypes.py::test_custom_profile |
| 99-REQ-4.2 | TS-99-9 | 5.1, 5.2 | test_custom_archetypes.py::test_permission_preset |
| 99-REQ-4.3 | TS-99-10 | 5.2 | test_custom_archetypes.py::test_custom_in_task |
| 99-REQ-4.4 | TS-99-9 | 5.2 | test_custom_archetypes.py::test_get_archetype_custom |
| 99-REQ-4.E1 | TS-99-E4 | 5.2 | test_custom_archetypes.py::test_no_preset |
| 99-REQ-4.E2 | TS-99-E5 | 5.2 | test_custom_archetypes.py::test_invalid_preset |
| 99-REQ-5.1 | TS-99-12 | 2.1 | test_profiles.py::test_load_profile_signature |
| 99-REQ-5.2 | TS-99-12 | 2.1 | test_profiles.py::test_load_profile_signature |
| 99-REQ-5.3 | TS-99-11 | 2.1 | test_profiles.py::test_frontmatter_stripping |
| 99-REQ-5.E1 | TS-99-E6 | 2.1 | test_profiles.py::test_none_project_dir |
| Property 1 | TS-99-P1 | 4.1 | test_profile_properties.py::test_layer_order |
| Property 2 | TS-99-P2 | 2.1, 4.1 | test_profile_properties.py::test_override_precedence |
| Property 3 | TS-99-P3 | 3.1-3.4 | test_profile_properties.py::test_default_completeness |
| Property 4 | TS-99-P4 | 5.3 | test_profile_properties.py::test_init_idempotence |
| Property 5 | TS-99-P5 | 5.2 | test_profile_properties.py::test_permission_inheritance |
