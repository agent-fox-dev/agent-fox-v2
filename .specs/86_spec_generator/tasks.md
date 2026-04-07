# Implementation Plan: Spec Generator

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The spec generator is implemented in six task groups. Group 1 writes all
failing tests. Group 2 adds platform extensions (new methods on
GitHubPlatform and PlatformProtocol). Group 3 adds config extensions and
state machine helpers. Group 4 builds the SpecGenerator core (analysis,
clarification, generation). Group 5 wires the SpecGeneratorStream and
landing workflow. Group 6 is wiring verification.

Ordering rationale: Platform extensions are leaf dependencies — the
generator needs `remove_label`, `list_issue_comments`, and `get_issue`
before any spec-gen logic can run. Config and state helpers are needed by
the generator core. The generator core must exist before the stream can
delegate to it. Landing is wired last because it depends on the full
generation pipeline.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/platform/test_platform_extensions.py tests/unit/nightshift/test_spec_gen.py tests/unit/nightshift/test_spec_gen_config.py tests/integration/test_spec_gen_lifecycle.py tests/property/test_spec_gen_props.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- Integration tests: `uv run pytest -q tests/integration/`
- All tests: `uv run pytest -q`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Set up test file structure
    - Create `tests/unit/platform/test_platform_extensions.py` — remove_label, list_issue_comments, get_issue, protocol tests
    - Create `tests/unit/nightshift/test_spec_gen.py` — SpecGenerator helper and core logic tests
    - Create `tests/unit/nightshift/test_spec_gen_config.py` — Config extension tests
    - Create `tests/integration/test_spec_gen_lifecycle.py` — Smoke tests
    - Create `tests/property/test_spec_gen_props.py` — Property tests
    - _Test Spec: TS-86-1 through TS-86-34, TS-86-E1 through TS-86-E18_

  - [x] 1.2 Translate acceptance-criterion tests
    - TS-86-1 through TS-86-34: one test function per entry
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-86-1 through TS-86-34_

  - [x] 1.3 Translate edge-case tests
    - TS-86-E1 through TS-86-E18: one test function per entry
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-86-E1 through TS-86-E18_

  - [x] 1.4 Translate property tests
    - TS-86-P1 through TS-86-P7: one property test per entry
    - Use Hypothesis with `suppress_health_check=[HealthCheck.function_scoped_fixture]`
    - _Test Spec: TS-86-P1 through TS-86-P7_

  - [x] 1.5 Translate integration smoke tests
    - TS-86-SMOKE-1 through TS-86-SMOKE-5: one smoke test per entry
    - Mark with `@pytest.mark.asyncio`
    - _Test Spec: TS-86-SMOKE-1 through TS-86-SMOKE-5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. Platform extensions: remove_label, list_issue_comments, get_issue
  - [x] 2.1 Add `IssueComment` dataclass to `platform/github.py`
    - Frozen dataclass with fields: `id: int`, `body: str`, `user: str`, `created_at: str`
    - _Requirements: 86-REQ-1.3_

  - [x] 2.2 Implement `GitHubPlatform.remove_label()`
    - DELETE to `/repos/{owner}/{repo}/issues/{issue_number}/labels/{label}`
    - URL-encode the label name (colons in `af:spec`)
    - 204: success. 404: succeed silently (idempotent). Other errors: raise `IntegrationError`
    - _Requirements: 86-REQ-1.1, 86-REQ-1.2, 86-REQ-1.E1_

  - [x] 2.3 Implement `GitHubPlatform.list_issue_comments()`
    - GET `/repos/{owner}/{repo}/issues/{issue_number}/comments`
    - Parse response into `list[IssueComment]` (chronological by default from API)
    - Return empty list for no comments. Raise `IntegrationError` on API error
    - _Requirements: 86-REQ-1.3, 86-REQ-1.E2_

  - [x] 2.4 Implement `GitHubPlatform.get_issue()`
    - GET `/repos/{owner}/{repo}/issues/{issue_number}`
    - Parse into `IssueResult`. Raise `IntegrationError` on 404 or other error
    - _Requirements: 86-REQ-1.4, 86-REQ-1.E3_

  - [x] 2.5 Extend `PlatformProtocol` with new method signatures
    - Add `remove_label`, `list_issue_comments`, `get_issue` to protocol
    - Verify `isinstance(GitHubPlatform(...), PlatformProtocol)` still passes
    - _Requirements: 86-REQ-1.5_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/platform/test_platform_extensions.py -k "TS_86_1 or TS_86_2 or TS_86_3 or TS_86_4 or TS_86_5 or E1 or E2 or E3"`
    - [-] Property tests pass: `uv run pytest -q tests/property/test_spec_gen_props.py -k "P5"`
    - [x] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 86-REQ-1.* met

- [x] 3. Config extensions, state machine helpers, and utility functions
  - [x] 3.1 Add new fields to `NightShiftConfig`
    - `max_clarification_rounds: int` (default 3, min 1 via validator)
    - `max_budget_usd: float` (default 2.0)
    - `spec_gen_model_tier: str` (default "ADVANCED")
    - Add field validator for clamping `max_clarification_rounds` to min 1
    - _Requirements: 86-REQ-9.1, 86-REQ-9.2, 86-REQ-9.3, 86-REQ-9.E1_

  - [x] 3.2 Create `nightshift/spec_gen.py` with data types and helpers
    - Define `SpecGenOutcome`, `SpecGenResult`, `AnalysisResult`, `DuplicateCheckResult`, `ReferencedIssue`, `SpecPackage` dataclasses
    - Define label constants: `LABEL_SPEC`, `LABEL_ANALYZING`, etc.
    - Implement `_is_fox_comment()`, `_count_clarification_rounds()`, `_has_new_human_comment()`
    - _Requirements: 86-REQ-5.1, 86-REQ-5.3, 86-REQ-2.3, 86-REQ-2.4_

  - [x] 3.3 Implement `_find_next_spec_number()` and `_spec_name_from_title()`
    - Scan `.specs/` for highest numeric prefix, increment
    - Derive snake_case slug from issue title, truncate to 40 chars
    - Handle empty `.specs/` (return 1)
    - _Requirements: 86-REQ-6.3, 86-REQ-6.E2_

  - [x] 3.4 Implement `_transition_label()` and `_format_*_comment()` helpers
    - `_transition_label`: assign new label, then remove old label
    - `_format_clarification_comment`: numbered questions, round counter
    - `_format_completion_comment`: spec folder, file list, commit hash
    - `_format_escalation_comment`: remaining questions, suggestion
    - `_format_budget_comment`: cost and limit
    - _Requirements: 86-REQ-3.1, 86-REQ-4.2, 86-REQ-5.2, 86-REQ-8.4, 86-REQ-10.2_

  - [x] 3.5 Implement `_harvest_references()`
    - Parse `#N` from body and comment bodies via regex
    - For each, call `platform.get_issue()` and `platform.list_issue_comments()`
    - On IntegrationError: log warning, skip reference
    - Return `list[ReferencedIssue]`
    - _Requirements: 86-REQ-4.3, 86-REQ-4.E1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest -q tests/unit/nightshift/test_spec_gen_config.py tests/unit/nightshift/test_spec_gen.py -k "TS_86_10 or TS_86_16 or TS_86_17 or TS_86_19 or TS_86_22 or TS_86_31 or E5 or E8 or E9 or E12 or E16 or E17"`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_spec_gen_props.py -k "P1 or P2 or P3 or P4 or P7"`
    - [-] All existing tests still pass: `make test`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 86-REQ-3.1, 86-REQ-4.3, 86-REQ-5.1, 86-REQ-5.3, 86-REQ-6.3, 86-REQ-9.* met

- [ ] 4. SpecGenerator core: analysis, clarification, generation, duplicates, cost
  - [ ] 4.1 Implement `SpecGenerator.__init__()` and `_resolve_model()`
    - Accept platform, config, repo_root
    - Create async Anthropic client via `create_async_anthropic_client()`
    - Resolve model from `spec_gen_model_tier` with fallback to ADVANCED
    - _Requirements: 86-REQ-6.4, 86-REQ-9.E2_

  - [ ] 4.2 Implement `_analyze_issue()`
    - Build prompt with issue body, comments, referenced issues, existing specs, steering
    - Call AI via `cached_messages_create()`
    - Parse response into `AnalysisResult(clear, questions, summary)`
    - Track cost from API response usage
    - _Requirements: 86-REQ-4.1, 86-REQ-4.E2_

  - [ ] 4.3 Implement `_check_duplicates()`
    - If no existing specs, return `DuplicateCheckResult(is_duplicate=False)` immediately
    - Build prompt with issue title/body and existing spec summaries
    - Call AI, parse response into `DuplicateCheckResult`
    - Track cost
    - _Requirements: 86-REQ-7.1, 86-REQ-7.E1_

  - [ ] 4.4 Implement `_generate_spec_package()`
    - Generate each document sequentially via AI calls following af-spec skill structure
    - Build PRD from issue body + clarification answers + `## Source` section
    - Pass previous documents as context for subsequent ones (requirements → design → test_spec → tasks)
    - Check cost after each call; abort if `max_budget_usd` exceeded
    - Return `SpecPackage` with all 5 files
    - _Requirements: 86-REQ-6.1, 86-REQ-6.2, 86-REQ-6.4, 86-REQ-10.1, 86-REQ-10.2_

  - [ ] 4.5 Implement `process_issue()` — full orchestration
    - Transition to analyzing
    - Fetch comments, harvest references, gather context
    - Check duplicates (if duplicate, post comment, transition pending, return)
    - Count rounds; if >= max, escalate
    - Analyze issue; if ambiguous, post clarification, transition pending
    - If clear, transition to generating, generate package, land, complete
    - Handle errors: catch exceptions, post error comment, transition to blocked
    - _Requirements: 86-REQ-3.2, 86-REQ-3.3, 86-REQ-3.4, 86-REQ-4.2, 86-REQ-5.2, 86-REQ-7.2, 86-REQ-7.3, 86-REQ-6.E1_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/nightshift/test_spec_gen.py -k "TS_86_6 or TS_86_7 or TS_86_8 or TS_86_9 or TS_86_11 or TS_86_12 or TS_86_13 or TS_86_14 or TS_86_15 or TS_86_18 or TS_86_20 or TS_86_21 or TS_86_23 or TS_86_24 or TS_86_25 or TS_86_26 or TS_86_32 or TS_86_33 or E4 or E6 or E7 or E10 or E11 or E13 or E18"`
    - [ ] Property tests pass: `uv run pytest -q tests/property/test_spec_gen_props.py -k "P2 or P6"`
    - [ ] All existing tests still pass: `make test`
    - [ ] No linter warnings introduced: `make lint`
    - [ ] Requirements 86-REQ-2.* through 86-REQ-7.*, 86-REQ-10.* met

- [ ] 5. SpecGeneratorStream wiring and landing workflow
  - [ ] 5.1 Implement `_land_spec()` in `SpecGenerator`
    - Create feature branch `spec/<spec_name>` from develop
    - Handle branch collision by appending `-2`, `-3`, etc.
    - Write all spec files to `.specs/<spec_name>/`
    - Commit with `feat(spec): generate <spec_name> from #<issue_number>`
    - If `merge_strategy == "direct"`: merge to develop, delete branch
    - If `merge_strategy == "pr"`: call `platform.create_pull_request()`
    - On failure: post comment with branch name, raise
    - Return commit hash
    - _Requirements: 86-REQ-8.1, 86-REQ-8.2, 86-REQ-8.3, 86-REQ-8.E1, 86-REQ-8.E2_

  - [ ] 5.2 Replace `SpecGeneratorStream` stub in `nightshift/streams.py`
    - Replace the no-op stub from spec 85 with real implementation
    - `run_once()`: poll for af:spec and af:spec-pending issues, handle crash recovery (stale labels), check staleness, process one issue, report cost
    - Wire `SpecGenerator` instantiation
    - _Requirements: 86-REQ-2.1, 86-REQ-2.2, 86-REQ-2.E1, 86-REQ-2.E2, 86-REQ-3.E1, 86-REQ-3.E2_

  - [ ] 5.3 Wire completion flow in `process_issue()`
    - After successful landing: post completion comment, transition to done, close issue
    - Report cost to result
    - _Requirements: 86-REQ-8.4, 86-REQ-10.3_

  - [ ] 5.4 Verify cost reporting to SharedBudget
    - `run_once()` calls `budget.add_cost(result.cost)` after processing
    - Cost is reported regardless of outcome (generated, blocked, etc.)
    - _Requirements: 86-REQ-10.3_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/nightshift/test_spec_gen.py -k "TS_86_27 or TS_86_28 or TS_86_29 or TS_86_30 or TS_86_34 or E14 or E15"`
    - [ ] Smoke tests pass: `uv run pytest -q tests/integration/test_spec_gen_lifecycle.py`
    - [ ] All existing tests still pass: `make test`
    - [ ] No linter warnings introduced: `make lint`
    - [ ] Requirements 86-REQ-8.*, 86-REQ-10.3 met

- [ ] 6. Wiring verification

  - [ ] 6.1 Trace every execution path from design.md end-to-end
    - Path 1 (happy path): stream.run_once → poll → process_issue → analyze → generate → land → close
    - Path 2 (clarification): stream.run_once → poll → process_issue → analyze → post questions → pending
    - Path 3 (re-analysis): stream.run_once → poll pending → detect new comment → transition → process_issue
    - Path 4 (escalation): process_issue → count rounds ≥ max → post escalation → blocked
    - Path 5 (cost cap): process_issue → generate → cost exceeded → abort → blocked
    - Confirm no function in any chain is a stub (`return []`, `return None`, `pass`, `raise NotImplementedError`) that was never replaced
    - _Requirements: all_

  - [ ] 6.2 Verify return values propagate correctly
    - `list_issue_comments()` → `list[IssueComment]` consumed by `_has_new_human_comment`, `_count_clarification_rounds`, `_analyze_issue`
    - `_analyze_issue()` → `AnalysisResult` consumed by `process_issue` branching logic
    - `_check_duplicates()` → `DuplicateCheckResult` consumed by `process_issue`
    - `_generate_spec_package()` → `SpecPackage` consumed by `_land_spec`
    - `_land_spec()` → `str` (commit hash) consumed by `_format_completion_comment`
    - `process_issue()` → `SpecGenResult` consumed by `SpecGeneratorStream.run_once()` for cost reporting
    - Grep for callers of each function; confirm none discards the return value
    - _Requirements: all_

  - [ ] 6.3 Run the integration smoke tests
    - All TS-86-SMOKE-1 through TS-86-SMOKE-5 pass using real components (no stub bypass)
    - `uv run pytest -q tests/integration/test_spec_gen_lifecycle.py -k SMOKE`
    - _Test Spec: TS-86-SMOKE-1 through TS-86-SMOKE-5_

  - [ ] 6.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale
    - _Requirements: all_

  - [ ] 6.V Verify wiring group
    - [ ] All smoke tests pass: `uv run pytest -q tests/integration/test_spec_gen_lifecycle.py`
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All existing tests still pass: `make check`

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 86-REQ-1.1 | TS-86-1 | 2.2 | tests/unit/platform/test_platform_extensions.py |
| 86-REQ-1.2 | TS-86-2 | 2.2 | tests/unit/platform/test_platform_extensions.py |
| 86-REQ-1.3 | TS-86-3 | 2.1, 2.3 | tests/unit/platform/test_platform_extensions.py |
| 86-REQ-1.4 | TS-86-4 | 2.4 | tests/unit/platform/test_platform_extensions.py |
| 86-REQ-1.5 | TS-86-5 | 2.5 | tests/unit/platform/test_platform_extensions.py |
| 86-REQ-1.E1 | TS-86-E1 | 2.2 | tests/unit/platform/test_platform_extensions.py |
| 86-REQ-1.E2 | TS-86-E2 | 2.3 | tests/unit/platform/test_platform_extensions.py |
| 86-REQ-1.E3 | TS-86-E3 | 2.4 | tests/unit/platform/test_platform_extensions.py |
| 86-REQ-2.1 | TS-86-6 | 5.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-2.2 | TS-86-7 | 5.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-2.3 | TS-86-8 | 3.2, 5.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-2.4 | TS-86-9 | 3.2, 5.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-2.E1 | TS-86-E4 | 5.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-2.E2 | TS-86-E5 | 5.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-3.1 | TS-86-10 | 3.4 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-3.2 | TS-86-11 | 4.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-3.3 | TS-86-12 | 4.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-3.4 | TS-86-13 | 4.5, 5.3 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-3.E1 | TS-86-E6 | 5.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-3.E2 | TS-86-E7 | 5.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-4.1 | TS-86-14 | 4.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-4.2 | TS-86-15 | 4.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-4.3 | TS-86-16 | 3.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-4.E1 | TS-86-E8 | 3.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-4.E2 | TS-86-E9 | 4.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-5.1 | TS-86-17 | 3.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-5.2 | TS-86-18 | 4.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-5.3 | TS-86-19 | 3.2 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-5.E1 | TS-86-E10 | 4.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-6.1 | TS-86-20 | 4.4 | tests/integration/test_spec_gen_lifecycle.py |
| 86-REQ-6.2 | TS-86-21 | 4.4 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-6.3 | TS-86-22 | 3.3 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-6.4 | TS-86-23 | 4.1, 4.4 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-6.E1 | TS-86-E11 | 4.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-6.E2 | TS-86-E12 | 3.3 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-7.1 | TS-86-24 | 4.3 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-7.2 | TS-86-25 | 4.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-7.3 | TS-86-26 | 4.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-7.E1 | TS-86-E13 | 4.3 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-8.1 | TS-86-27 | 5.1 | tests/integration/test_spec_gen_lifecycle.py |
| 86-REQ-8.2 | TS-86-28 | 5.1 | tests/integration/test_spec_gen_lifecycle.py |
| 86-REQ-8.3 | TS-86-29 | 5.1 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-8.4 | TS-86-30 | 5.3 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-8.E1 | TS-86-E14 | 5.1 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-8.E2 | TS-86-E15 | 5.1 | tests/integration/test_spec_gen_lifecycle.py |
| 86-REQ-9.1 | TS-86-31 | 3.1 | tests/unit/nightshift/test_spec_gen_config.py |
| 86-REQ-9.2 | TS-86-31 | 3.1 | tests/unit/nightshift/test_spec_gen_config.py |
| 86-REQ-9.3 | TS-86-31 | 3.1 | tests/unit/nightshift/test_spec_gen_config.py |
| 86-REQ-9.E1 | TS-86-E16 | 3.1 | tests/unit/nightshift/test_spec_gen_config.py |
| 86-REQ-9.E2 | TS-86-E17 | 4.1 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-10.1 | TS-86-32 | 4.4 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-10.2 | TS-86-33 | 4.4, 4.5 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-10.3 | TS-86-34 | 5.4 | tests/unit/nightshift/test_spec_gen.py |
| 86-REQ-10.E1 | TS-86-E18 | 4.4 | tests/unit/nightshift/test_spec_gen.py |
| Property 1 | TS-86-P1 | 3.4 | tests/property/test_spec_gen_props.py |
| Property 2 | TS-86-P2 | 3.2 | tests/property/test_spec_gen_props.py |
| Property 3 | TS-86-P3 | 3.2 | tests/property/test_spec_gen_props.py |
| Property 4 | TS-86-P4 | 3.3 | tests/property/test_spec_gen_props.py |
| Property 5 | TS-86-P5 | 2.2 | tests/property/test_spec_gen_props.py |
| Property 6 | TS-86-P6 | 4.4 | tests/property/test_spec_gen_props.py |
| Property 7 | TS-86-P7 | 3.3 | tests/property/test_spec_gen_props.py |

## Notes

- **Hypothesis:** Use `suppress_health_check=[HealthCheck.function_scoped_fixture]` in
  all property tests using pytest fixtures.
- **Async tests:** Mark with `@pytest.mark.asyncio` and use `AsyncMock` for
  async method mocks.
- **Spec 85 dependency:** This spec depends on the WorkStream protocol,
  SharedBudget, and config fields from spec 85 group 2. If spec 85 is not
  yet implemented, the SpecGeneratorStream stub must exist at minimum.
- **AI mocking:** All tests mock the Anthropic API client. No real API calls
  in tests. Mock responses should return structured JSON that the parser
  can extract.
- **Git operations in tests:** Integration tests (TS-86-27, TS-86-28,
  TS-86-SMOKE-1) use a real git repo in a temp directory. Use `tmp_path`
  fixture and `git init` in setup.
- **Label URL encoding:** GitHub API requires URL-encoding of label names
  in DELETE paths. Labels containing colons (`af:spec`) must be encoded
  as `af%3Aspec`.
