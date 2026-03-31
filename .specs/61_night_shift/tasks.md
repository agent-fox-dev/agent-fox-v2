# Implementation Plan: Night Shift -- Autonomous Maintenance Mode

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Night Shift is a large feature spanning nine modules. The implementation is
ordered so that foundational types (findings, config, platform protocol) are
built first, followed by the hunt system, then the fix pipeline, and finally
the CLI entry point that wires everything together. Each task group targets a
coherent set of requirements and makes the corresponding spec tests pass.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/nightshift/ tests/integration/nightshift/ tests/property/nightshift/`
- Unit tests: `uv run pytest -q tests/unit/nightshift/`
- Property tests: `uv run pytest -q tests/property/nightshift/`
- Integration tests: `uv run pytest -q tests/integration/nightshift/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Set up test file structure
    - Create `tests/unit/nightshift/` with `__init__.py`
    - Create `tests/integration/nightshift/` with `__init__.py`
    - Create `tests/property/nightshift/` with `__init__.py`
    - _Test Spec: TS-61-1 through TS-61-28, TS-61-E1 through TS-61-E12, TS-61-P1 through TS-61-P8_

  - [x] 1.2 Write unit tests for config and data types
    - `tests/unit/nightshift/test_config.py`: TS-61-26, TS-61-27, TS-61-E12
    - `tests/unit/nightshift/test_finding.py`: TS-61-9, TS-61-13, TS-61-15
    - `tests/unit/nightshift/test_platform.py`: TS-61-23, TS-61-24, TS-61-25, TS-61-E1, TS-61-E11
    - _Test Spec: TS-61-9, TS-61-13, TS-61-15, TS-61-23 through TS-61-27, TS-61-E1, TS-61-E11, TS-61-E12_

  - [x] 1.3 Write unit tests for scheduling and hunt system
    - `tests/unit/nightshift/test_scheduler.py`: TS-61-4, TS-61-5, TS-61-6, TS-61-E4
    - `tests/unit/nightshift/test_hunt.py`: TS-61-7, TS-61-8, TS-61-11, TS-61-12
    - `tests/unit/nightshift/test_fix_pipeline.py`: TS-61-2, TS-61-16, TS-61-17, TS-61-21, TS-61-E2, TS-61-E6, TS-61-E9
    - _Test Spec: TS-61-2, TS-61-4 through TS-61-8, TS-61-11, TS-61-12, TS-61-16, TS-61-17, TS-61-21, TS-61-E2, TS-61-E4, TS-61-E6, TS-61-E9_

  - [x] 1.4 Write integration tests
    - `tests/integration/nightshift/test_engine.py`: TS-61-1, TS-61-3, TS-61-28
    - `tests/integration/nightshift/test_hunt_scan.py`: TS-61-10, TS-61-14, TS-61-E3, TS-61-E5, TS-61-E7
    - `tests/integration/nightshift/test_fix_flow.py`: TS-61-18, TS-61-19, TS-61-20, TS-61-22, TS-61-E8, TS-61-E10
    - _Test Spec: TS-61-1, TS-61-3, TS-61-10, TS-61-14, TS-61-18 through TS-61-20, TS-61-22, TS-61-28, TS-61-E3, TS-61-E5, TS-61-E7, TS-61-E8, TS-61-E10_

  - [x] 1.5 Write property tests
    - `tests/property/nightshift/test_nightshift_props.py`: TS-61-P1 through TS-61-P8
    - _Test Spec: TS-61-P1 through TS-61-P8_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/nightshift/ tests/integration/nightshift/ tests/property/nightshift/`

- [ ] 2. Core data types, config, and platform protocol
  - [ ] 2.1 Implement Finding dataclass and FindingGroup
    - Create `agent_fox/nightshift/__init__.py`
    - Create `agent_fox/nightshift/finding.py` with `Finding`, `FindingGroup`
    - Implement `consolidate_findings()` grouping logic
    - _Requirements: 3.3, 5.1_

  - [ ] 2.2 Implement NightShiftConfig
    - Add `NightShiftConfig` and `NightShiftCategoryConfig` to `agent_fox/core/config.py`
    - Add `night_shift` field to `AgentFoxConfig`
    - Implement interval clamping (min 60s) with warning
    - _Requirements: 9.1, 9.2, 9.E1_

  - [ ] 2.3 Implement PlatformProtocol
    - Create `agent_fox/platform/protocol.py` with `PlatformProtocol`
    - Define all required methods: `create_issue`, `list_issues_by_label`, `add_issue_comment`, `assign_label`, `create_pr`, `close`
    - _Requirements: 8.1_

  - [ ] 2.4 Extend GitHubPlatform to implement PlatformProtocol
    - Add `list_issues_by_label()` and `assign_label()` to `agent_fox/platform/github.py`
    - Ensure runtime isinstance check passes
    - Implement `create_platform()` factory function
    - _Requirements: 8.2, 8.3, 8.E1_

  - [ ] 2.5 Implement NightShiftState and InMemorySpec
    - Create `agent_fox/nightshift/state.py` with `NightShiftState`
    - Create `agent_fox/nightshift/spec_builder.py` with `InMemorySpec` and `build_in_memory_spec()`
    - Implement `sanitise_branch_name()` utility
    - _Requirements: 6.1, 6.2_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/nightshift/test_config.py tests/unit/nightshift/test_finding.py tests/unit/nightshift/test_platform.py tests/unit/nightshift/test_fix_pipeline.py::TestInMemorySpec tests/unit/nightshift/test_fix_pipeline.py::TestBranchNaming`
    - [ ] Property tests pass: `uv run pytest -q tests/property/nightshift/test_nightshift_props.py::test_finding_format_universality`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/nightshift/ agent_fox/platform/ agent_fox/core/config.py`
    - [ ] Requirements 3.3, 5.1, 6.1, 6.2, 8.1, 8.2, 8.3, 9.1, 9.2 acceptance criteria met

- [ ] 3. Checkpoint -- Core Types Complete
  - Ensure all tests pass, ask the user if questions arise.
  - Verify platform protocol is implementable and config is loadable.

- [ ] 4. Scheduling and hunt category system
  - [ ] 4.1 Implement Scheduler
    - Create `agent_fox/nightshift/scheduler.py`
    - Implement timed callbacks for issue check and hunt scan
    - Implement overlap prevention (skip if scan in progress)
    - Implement initial-run-on-startup behaviour
    - _Requirements: 2.1, 2.2, 2.3, 2.E2_

  - [ ] 4.2 Implement HuntCategory protocol and registry
    - Create `agent_fox/nightshift/hunt.py` with `HuntCategory` protocol
    - Implement `HuntCategoryRegistry` with registration and lookup
    - Implement parallel category dispatch via `asyncio.gather`
    - Implement per-category error isolation (catch + log + continue)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.E1_

  - [ ] 4.3 Implement built-in hunt categories (batch 1)
    - Create `agent_fox/nightshift/categories/__init__.py`
    - Implement `dependency_freshness`, `todo_fixme`, `linter_debt`
    - Each category: static tool phase + AI agent phase
    - Each category has a distinct prompt template
    - _Requirements: 3.1, 4.1, 4.2, 4.3, 4.E1_

  - [ ] 4.4 Implement built-in hunt categories (batch 2)
    - Implement `test_coverage`, `deprecated_api`, `dead_code`, `documentation_drift`
    - Same two-phase pattern as batch 1
    - _Requirements: 3.1, 4.1, 4.2, 4.3_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/nightshift/test_scheduler.py tests/unit/nightshift/test_hunt.py`
    - [ ] Property tests pass: `uv run pytest -q tests/property/nightshift/test_nightshift_props.py::test_schedule_interval_compliance tests/property/nightshift/test_nightshift_props.py::test_category_isolation`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/nightshift/`
    - [ ] Requirements 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3 acceptance criteria met

- [ ] 5. Finding consolidation and issue creation
  - [ ] 5.1 Implement finding-to-issue pipeline
    - Implement `build_issue_body()` in `agent_fox/nightshift/finding.py`
    - Include category, severity, affected files, suggested fix in issue body
    - Implement `create_issues_from_groups()` with per-issue error isolation
    - _Requirements: 5.2, 5.3, 5.E1_

  - [ ] 5.2 Implement auto-label assignment
    - Wire `--auto` flag through to issue creation
    - Call `platform.assign_label()` after issue creation when auto is True
    - _Requirements: 1.2, 5.4_

  - [ ] 5.3 Implement PR body builder
    - Create `build_pr_body()` in `agent_fox/nightshift/fix_pipeline.py`
    - Include issue reference (Fixes #N) and summary
    - _Requirements: 7.2_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/nightshift/test_finding.py::TestIssueBody tests/unit/nightshift/test_fix_pipeline.py::TestPRBody tests/integration/nightshift/test_hunt_scan.py::TestIssueCreation`
    - [ ] Property tests pass: `uv run pytest -q tests/property/nightshift/test_nightshift_props.py::test_issue_finding_bijection`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/nightshift/`
    - [ ] Requirements 1.2, 5.1, 5.2, 5.3, 5.4, 7.2 acceptance criteria met

- [ ] 6. Fix pipeline
  - [ ] 6.1 Implement FixPipeline class
    - Create `agent_fox/nightshift/fix_pipeline.py`
    - Implement `process_issue()`: create branch, build spec, run sessions, create PR
    - Implement issue commenting for progress updates
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 6.2 Implement archetype pipeline integration
    - Wire skeptic -> coder -> verifier pipeline using existing `NodeSessionRunner`
    - Adapt session runner for issue-driven (non-spec) execution
    - Handle fix failure: comment on issue, continue
    - _Requirements: 6.3, 6.E1_

  - [ ] 6.3 Implement PR creation and issue linking
    - Create PR via platform after successful fix
    - Post comment on issue with PR link
    - Handle PR creation failure: log + comment with branch name
    - Handle empty issue body: comment requesting detail + skip
    - _Requirements: 7.1, 7.3, 7.E1, 6.E2_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/nightshift/test_fix_pipeline.py tests/integration/nightshift/test_fix_flow.py`
    - [ ] Property tests pass: `uv run pytest -q tests/property/nightshift/test_nightshift_props.py::test_fix_pipeline_completeness`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/nightshift/`
    - [ ] Requirements 6.1, 6.2, 6.3, 6.4, 7.1, 7.3 acceptance criteria met

- [ ] 7. Checkpoint -- Hunt + Fix Complete
  - Ensure all unit, integration, and property tests pass.
  - Review finding format, platform protocol, and fix pipeline for consistency.

- [ ] 8. Night-shift engine and CLI
  - [ ] 8.1 Implement NightShiftEngine
    - Create `agent_fox/nightshift/engine.py`
    - Implement `run()`: startup validation, event loop, graceful shutdown
    - Wire issue check and hunt scan via Scheduler
    - Wire fix pipeline for `af:fix` issues
    - Implement cost limit checking against `orchestrator.max_cost`
    - _Requirements: 1.1, 1.3, 1.4, 1.E1, 1.E2, 9.3_

  - [ ] 8.2 Implement platform validation
    - Validate platform is configured and token is available on startup
    - Abort with descriptive error if not
    - _Requirements: 1.E1_

  - [ ] 8.3 Implement CLI command
    - Register `night-shift` command in `agent_fox/cli/app.py`
    - Create `agent_fox/cli/nightshift.py` with Click command
    - Wire `--auto` flag, config loading, platform instantiation
    - Wire SIGINT handler (single = graceful, double = immediate)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 8.4 Wire audit events
    - Emit `NIGHT_SHIFT_START`, `HUNT_SCAN_COMPLETE`, `ISSUE_CREATED`, `FIX_START`, `FIX_COMPLETE`, `FIX_FAILED` events
    - Use existing `SinkDispatcher` infrastructure
    - _Requirements: (observability, cross-cutting)_

  - [ ] 8.V Verify task group 8
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/integration/nightshift/test_engine.py`
    - [ ] Property tests pass: `uv run pytest -q tests/property/nightshift/test_nightshift_props.py::test_cost_monotonicity tests/property/nightshift/test_nightshift_props.py::test_graceful_shutdown_completeness tests/property/nightshift/test_nightshift_props.py::test_platform_protocol_substitutability`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/nightshift/ agent_fox/cli/`
    - [ ] Requirements 1.1, 1.2, 1.3, 1.4, 9.3 acceptance criteria met

- [ ] 9. Documentation and final verification
  - [ ] 9.1 Update CLI reference
    - Add `night-shift` command to `docs/cli-reference.md`
    - Document `--auto` flag and exit codes

  - [ ] 9.2 Update configuration docs
    - Add `[night_shift]` section to `docs/configuration.md`
    - Document all category toggles and interval settings

  - [ ] 9.3 Update README
    - Add night-shift to the quick-start section
    - Brief description of the feature

  - [ ] 9.V Verify task group 9
    - [ ] All spec tests pass: `uv run pytest -q tests/unit/nightshift/ tests/integration/nightshift/ tests/property/nightshift/`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Documentation updated: cli-reference.md, configuration.md, README.md

## Traceability

| Requirement  | Test Spec Entry | Implemented By Task | Verified By Test                                          |
| ------------ | --------------- | ------------------- | --------------------------------------------------------- |
| 61-REQ-1.1   | TS-61-1         | 8.1, 8.3            | tests/integration/nightshift/test_engine.py               |
| 61-REQ-1.2   | TS-61-2         | 5.2, 8.3            | tests/unit/nightshift/test_fix_pipeline.py                |
| 61-REQ-1.3   | TS-61-3         | 8.1, 8.3            | tests/integration/nightshift/test_engine.py               |
| 61-REQ-1.4   | TS-61-3         | 8.1, 8.3            | tests/integration/nightshift/test_engine.py               |
| 61-REQ-1.E1  | TS-61-E1        | 8.2                 | tests/unit/nightshift/test_platform.py                    |
| 61-REQ-1.E2  | TS-61-E2        | 8.1                 | tests/unit/nightshift/test_fix_pipeline.py                |
| 61-REQ-2.1   | TS-61-4         | 4.1                 | tests/unit/nightshift/test_scheduler.py                   |
| 61-REQ-2.2   | TS-61-5         | 4.1                 | tests/unit/nightshift/test_scheduler.py                   |
| 61-REQ-2.3   | TS-61-6         | 4.1                 | tests/unit/nightshift/test_scheduler.py                   |
| 61-REQ-2.E1  | TS-61-E3        | 8.1                 | tests/integration/nightshift/test_hunt_scan.py            |
| 61-REQ-2.E2  | TS-61-E4        | 4.1                 | tests/unit/nightshift/test_scheduler.py                   |
| 61-REQ-3.1   | TS-61-7         | 4.2, 4.3, 4.4       | tests/unit/nightshift/test_hunt.py                        |
| 61-REQ-3.2   | TS-61-8         | 4.2                 | tests/unit/nightshift/test_hunt.py                        |
| 61-REQ-3.3   | TS-61-9         | 2.1, 4.2            | tests/unit/nightshift/test_finding.py                     |
| 61-REQ-3.4   | TS-61-10        | 4.2                 | tests/integration/nightshift/test_hunt_scan.py            |
| 61-REQ-3.E1  | TS-61-E5        | 4.2                 | tests/integration/nightshift/test_hunt_scan.py            |
| 61-REQ-4.1   | TS-61-11        | 4.3, 4.4            | tests/unit/nightshift/test_hunt.py                        |
| 61-REQ-4.2   | TS-61-11        | 4.3, 4.4            | tests/unit/nightshift/test_hunt.py                        |
| 61-REQ-4.3   | TS-61-12        | 4.3, 4.4            | tests/unit/nightshift/test_hunt.py                        |
| 61-REQ-4.E1  | TS-61-E6        | 4.3                 | tests/unit/nightshift/test_hunt.py                        |
| 61-REQ-5.1   | TS-61-13        | 2.1                 | tests/unit/nightshift/test_finding.py                     |
| 61-REQ-5.2   | TS-61-14        | 5.1                 | tests/integration/nightshift/test_hunt_scan.py            |
| 61-REQ-5.3   | TS-61-15        | 5.1                 | tests/unit/nightshift/test_finding.py                     |
| 61-REQ-5.4   | TS-61-2         | 5.2                 | tests/unit/nightshift/test_fix_pipeline.py                |
| 61-REQ-5.E1  | TS-61-E7        | 5.1                 | tests/integration/nightshift/test_hunt_scan.py            |
| 61-REQ-6.1   | TS-61-16        | 2.5, 6.1            | tests/unit/nightshift/test_fix_pipeline.py                |
| 61-REQ-6.2   | TS-61-17        | 2.5, 6.1            | tests/unit/nightshift/test_fix_pipeline.py                |
| 61-REQ-6.3   | TS-61-18        | 6.2                 | tests/integration/nightshift/test_fix_flow.py             |
| 61-REQ-6.4   | TS-61-19        | 6.1                 | tests/integration/nightshift/test_fix_flow.py             |
| 61-REQ-6.E1  | TS-61-E8        | 6.2                 | tests/integration/nightshift/test_fix_flow.py             |
| 61-REQ-6.E2  | TS-61-E9        | 6.3                 | tests/unit/nightshift/test_fix_pipeline.py                |
| 61-REQ-7.1   | TS-61-20        | 6.3                 | tests/integration/nightshift/test_fix_flow.py             |
| 61-REQ-7.2   | TS-61-21        | 5.3                 | tests/unit/nightshift/test_fix_pipeline.py                |
| 61-REQ-7.3   | TS-61-22        | 6.3                 | tests/integration/nightshift/test_fix_flow.py             |
| 61-REQ-7.E1  | TS-61-E10       | 6.3                 | tests/integration/nightshift/test_fix_flow.py             |
| 61-REQ-8.1   | TS-61-23        | 2.3                 | tests/unit/nightshift/test_platform.py                    |
| 61-REQ-8.2   | TS-61-24        | 2.4                 | tests/unit/nightshift/test_platform.py                    |
| 61-REQ-8.3   | TS-61-25        | 2.4                 | tests/unit/nightshift/test_platform.py                    |
| 61-REQ-8.E1  | TS-61-E11       | 2.4                 | tests/unit/nightshift/test_platform.py                    |
| 61-REQ-9.1   | TS-61-26        | 2.2                 | tests/unit/nightshift/test_config.py                      |
| 61-REQ-9.2   | TS-61-27        | 2.2                 | tests/unit/nightshift/test_config.py                      |
| 61-REQ-9.3   | TS-61-28        | 8.1                 | tests/integration/nightshift/test_engine.py               |
| 61-REQ-9.E1  | TS-61-E12       | 2.2                 | tests/unit/nightshift/test_config.py                      |
| Property 1   | TS-61-P1        | 2.1                 | tests/property/nightshift/test_nightshift_props.py        |
| Property 2   | TS-61-P2        | 4.1                 | tests/property/nightshift/test_nightshift_props.py        |
| Property 3   | TS-61-P3        | 2.1, 5.1            | tests/property/nightshift/test_nightshift_props.py        |
| Property 4   | TS-61-P4        | 6.1, 6.3            | tests/property/nightshift/test_nightshift_props.py        |
| Property 5   | TS-61-P5        | 8.1                 | tests/property/nightshift/test_nightshift_props.py        |
| Property 6   | TS-61-P6        | 8.1, 8.3            | tests/property/nightshift/test_nightshift_props.py        |
| Property 7   | TS-61-P7        | 4.2                 | tests/property/nightshift/test_nightshift_props.py        |
| Property 8   | TS-61-P8        | 2.3, 2.4            | tests/property/nightshift/test_nightshift_props.py        |

## Notes

- The seven hunt categories each need a prompt template in `agent_fox/_templates/` or inline.
- The fix pipeline reuses `NodeSessionRunner` from the existing session lifecycle but adapts it for issue-driven (non-spec-file) execution.
- Platform protocol is designed for future GitLab/Gitea implementations -- keep the interface minimal and REST-only.
- Cost control reuses existing `orchestrator.max_cost` / `max_sessions` -- no new budget mechanism needed.
- Audit events use existing `AuditEventType` enum and `SinkDispatcher` -- new event types need to be registered.
