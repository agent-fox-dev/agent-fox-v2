# Implementation Plan: Install Claude Code Skills via `init --skills`

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Three task groups: (1) write failing tests, (2) update bundled templates with
frontmatter and implement `_install_skills()` + CLI flag, (3) checkpoint with
docs.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/cli/test_init_skills.py tests/integration/test_init_skills.py tests/property/cli/test_init_skills_props.py`
- Unit tests: `uv run pytest -q tests/unit/cli/test_init_skills.py`
- Property tests: `uv run pytest -q tests/property/cli/test_init_skills_props.py`
- Integration tests: `uv run pytest -q tests/integration/test_init_skills.py`
- All tests: `uv run pytest -q`
- Linter: `ruff check agent_fox/ tests/ && ruff format --check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/cli/test_init_skills.py`
    - Test `_install_skills()` function in isolation
    - TS-47-E1: unreadable template skipped
    - TS-47-E2: empty templates directory returns 0
    - TS-47-E3: permission error handled gracefully
    - _Test Spec: TS-47-E1, TS-47-E2, TS-47-E3_

  - [x] 1.2 Create property test file `tests/property/cli/test_init_skills_props.py`
    - TS-47-P1: bundled templates have valid frontmatter (name, description)
    - TS-47-P2: installation bijection (one SKILL.md per template, identical content)
    - TS-47-P3: count accuracy (return value matches files written)
    - _Test Spec: TS-47-P1, TS-47-P2, TS-47-P3_

  - [x] 1.3 Create integration test file `tests/integration/test_init_skills.py`
    - TS-47-1: skills installed to correct paths
    - TS-47-2: no skills without flag
    - TS-47-3: skills overwrite on re-run
    - TS-47-4: output reports skill count
    - TS-47-5: JSON output includes skills_installed
    - TS-47-6: JSON output excludes skills_installed without flag
    - TS-47-7: skills work on re-init
    - _Test Spec: TS-47-1 through TS-47-7_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `ruff check tests/unit/cli/test_init_skills.py tests/property/cli/test_init_skills_props.py tests/integration/test_init_skills.py`

- [x] 2. Implement skill installation
  - [x] 2.1 Update bundled templates with YAML frontmatter
    - Add `---` delimited frontmatter to each file in `agent_fox/_templates/skills/`
    - Frontmatter fields: `name`, `description`, and `argument-hint` (where applicable)
    - Match metadata from `skills/*/SKILL.md` (the repo-root source of truth)
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 2.2 Implement `_install_skills()` function in `agent_fox/cli/init.py`
    - Add `_SKILLS_DIR` constant pointing to `_TEMPLATES_DIR / "skills"`
    - Discover all non-hidden files in `_SKILLS_DIR`
    - Create `.claude/skills/{name}/SKILL.md` for each, overwriting if exists
    - Handle errors per requirements (skip unreadable, handle empty dir, catch permission errors)
    - Return integer count of skills installed
    - _Requirements: 2.1, 2.3, 2.4, 1.E1, 2.E1, 2.E2_

  - [x] 2.3 Add `--skills` flag to `init_cmd`
    - Add `@click.option("--skills", ...)` boolean flag
    - Call `_install_skills()` when flag is set, in both fresh and re-init paths
    - Report count in human-readable output
    - Include `skills_installed` in JSON output when flag is set
    - _Requirements: 2.2, 2.5, 3.1, 3.2, 4.1, 4.2_

  - [x] 2.V Verify task group 2
    - [x] All spec tests pass: `uv run pytest -q tests/unit/cli/test_init_skills.py tests/integration/test_init_skills.py tests/property/cli/test_init_skills_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `ruff check agent_fox/cli/init.py && ruff format --check agent_fox/cli/init.py`
    - [x] Requirements 1.1–1.3, 1.E1, 2.1–2.5, 2.E1–2.E2, 3.1–3.2, 4.1–4.2 acceptance criteria met

- [ ] 3. Checkpoint — feature complete
  - [ ] All tests pass: `make check`
  - [ ] Update `docs/cli-reference.md` with `--skills` flag documentation
  - [ ] Update `docs/skills.md` to mention `init --skills` as installation method
  - [ ] Update `README.md` quick-start if appropriate

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 47-REQ-1.1 | TS-47-P1 | 2.1 | `test_init_skills_props.py::test_bundled_templates_have_valid_frontmatter` |
| 47-REQ-1.2 | TS-47-P1 | 2.1 | `test_init_skills_props.py::test_bundled_templates_have_valid_frontmatter` |
| 47-REQ-1.3 | TS-47-P1 | 2.1 | `test_init_skills_props.py::test_bundled_templates_have_valid_frontmatter` |
| 47-REQ-1.E1 | TS-47-E1 | 2.2 | `test_init_skills.py::test_unreadable_template_skipped` |
| 47-REQ-2.1 | TS-47-1, TS-47-P2 | 2.2, 2.3 | `test_init_skills.py::test_skills_installed_to_correct_paths` |
| 47-REQ-2.2 | TS-47-2 | 2.3 | `test_init_skills.py::test_no_skills_without_flag` |
| 47-REQ-2.3 | TS-47-P2 | 2.2 | `test_init_skills_props.py::test_installation_bijection` |
| 47-REQ-2.4 | TS-47-3 | 2.2 | `test_init_skills.py::test_skills_overwrite_on_rerun` |
| 47-REQ-2.5 | TS-47-4, TS-47-P3 | 2.3 | `test_init_skills.py::test_output_reports_skill_count` |
| 47-REQ-2.E1 | TS-47-E2 | 2.2 | `test_init_skills.py::test_empty_templates_directory` |
| 47-REQ-2.E2 | TS-47-E3 | 2.2 | `test_init_skills.py::test_permission_error_handled` |
| 47-REQ-3.1 | TS-47-5 | 2.3 | `test_init_skills.py::test_json_includes_skills_installed` |
| 47-REQ-3.2 | TS-47-6 | 2.3 | `test_init_skills.py::test_json_excludes_skills_installed` |
| 47-REQ-4.1 | TS-47-1 | 2.3 | `test_init_skills.py::test_skills_installed_to_correct_paths` |
| 47-REQ-4.2 | TS-47-7 | 2.3 | `test_init_skills.py::test_skills_work_on_reinit` |
