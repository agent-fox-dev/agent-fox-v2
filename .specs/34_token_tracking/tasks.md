# Implementation Plan: Comprehensive Token Tracking

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in five groups: (1) write failing tests, (2) token
accumulator and pricing config, (3) integrate accumulator into state and
update cost calculation, (4) per-archetype and per-spec reporting, (5)
instrument auxiliary call sites and verify end-to-end.

The ordering ensures the foundation (accumulator, pricing) is built first,
then wired into the state system, then surfaced in reporting, and finally
the call sites are instrumented — each group building on the previous.

## Test Commands

- Spec tests: `uv run pytest tests/unit/core/test_token_tracker.py tests/unit/core/test_pricing.py tests/unit/reporting/test_cost_reporting.py -v`
- Property tests: `uv run pytest tests/property/core/test_token_tracking_props.py -v`
- All tests: `uv run pytest -x -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/core/test_token_tracker.py`
    - Test class `TestTokenAccumulator` with TS-34-1, TS-34-2
    - Test class `TestAccumulatorEdgeCases` with TS-34-E1, TS-34-E2
    - _Test Spec: TS-34-1, TS-34-2, TS-34-E1, TS-34-E2_

  - [x] 1.2 Create `tests/unit/core/test_pricing.py`
    - Test class `TestPricingConfig` with TS-34-6, TS-34-7, TS-34-8
    - Test class `TestPricingEdgeCases` with TS-34-E3, TS-34-E4
    - Test class `TestModelEntryCleanup` with TS-34-14
    - _Test Spec: TS-34-6, TS-34-7, TS-34-8, TS-34-14, TS-34-E3, TS-34-E4_

  - [x] 1.3 Create `tests/unit/reporting/test_cost_reporting.py`
    - Test class `TestAuxiliaryIntegration` with TS-34-3, TS-34-4
    - Test class `TestArchetypeTracking` with TS-34-9, TS-34-10, TS-34-11
    - Test class `TestPerSpecCost` with TS-34-12, TS-34-13
    - Test class `TestCallSiteInstrumentation` with TS-34-5
    - Test class `TestBackwardCompat` with TS-34-E5, TS-34-E6
    - _Test Spec: TS-34-3 through TS-34-13, TS-34-E5, TS-34-E6_

  - [x] 1.4 Create `tests/property/core/test_token_tracking_props.py`
    - Property tests TS-34-P1 through TS-34-P6
    - _Test Spec: TS-34-P1 through TS-34-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings: `uv run ruff check tests/unit/core/test_token_tracker.py tests/unit/core/test_pricing.py tests/unit/reporting/test_cost_reporting.py tests/property/core/test_token_tracking_props.py`

- [x] 2. Token accumulator and pricing config
  - [x] 2.1 Create `agent_fox/core/token_tracker.py`
    - `TokenUsage` dataclass
    - `TokenAccumulator` class with `record()`, `flush()`, `total()`, `reset()`
    - Thread-safe via `threading.Lock`
    - Module-level singleton and convenience functions: `record_auxiliary_usage()`,
      `flush_auxiliary_usage()`, `get_auxiliary_totals()`
    - _Requirements: 34-REQ-1.1, 34-REQ-1.2_

  - [x] 2.2 Add `PricingConfig` and `ModelPricing` to `agent_fox/core/config.py`
    - `ModelPricing` with `input_price_per_m` and `output_price_per_m` fields
    - Clamping validator for negative values (clamp to 0, log warning)
    - `PricingConfig` with `models: dict[str, ModelPricing]` and factory default
      containing current Claude pricing for haiku, sonnet, opus
    - Add `pricing: PricingConfig` field to `AgentFoxConfig`
    - _Requirements: 34-REQ-2.1, 34-REQ-2.2, 34-REQ-2.E1, 34-REQ-2.E2_

  - [x] 2.3 Update `calculate_cost()` in `agent_fox/core/models.py`
    - Change signature to accept `model_id: str` and `pricing: PricingConfig`
      instead of `model: ModelEntry`
    - Look up model in pricing config, fall back to zero with warning
    - Remove `input_price_per_m` and `output_price_per_m` from `ModelEntry`
    - Update `MODEL_REGISTRY` entries to remove pricing fields
    - _Requirements: 34-REQ-2.3, 34-REQ-2.4, 34-REQ-5.1, 34-REQ-5.2_

  - [x] 2.4 Update all callers of `calculate_cost()`
    - `agent_fox/engine/session_lifecycle.py` — pass pricing config
    - `agent_fox/reporting/standup.py` — pass pricing config (if it calls calculate_cost)
    - Any other callers found via grep
    - _Requirements: 34-REQ-2.3_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest tests/unit/core/test_token_tracker.py tests/unit/core/test_pricing.py -v`
    - [-] Property tests pass: `uv run pytest tests/property/core/test_token_tracking_props.py::TestAccumulatorCompleteness tests/property/core/test_token_tracking_props.py::TestPricingConfigPrecedence tests/property/core/test_token_tracking_props.py::TestPricingDefaultsPresent -v`
    - [x] All existing tests still pass: `uv run pytest -x -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/core/token_tracker.py agent_fox/core/config.py agent_fox/core/models.py`
    - [x] Requirements 34-REQ-1.1, 34-REQ-1.2, 34-REQ-2.* met

- [x] 3. Integrate accumulator into state and add archetype
  - [x] 3.1 Add `archetype` field to `SessionRecord` in `agent_fox/engine/state.py`
    - Default value `"coder"` for backward compatibility
    - Update `from_dict()` to handle missing `archetype` key
    - Update `to_dict()` / serialization to include `archetype`
    - _Requirements: 34-REQ-3.1, 34-REQ-3.E1_

  - [x] 3.2 Populate archetype in `NodeSessionRunner`
    - In `_run_and_harvest()` when creating `SessionRecord`, pass
      `archetype=self._archetype`
    - In the exception handler in `execute()`, pass `archetype=self._archetype`
    - _Requirements: 34-REQ-3.2_

  - [x] 3.3 Integrate accumulator flush into `ExecutionState`
    - In `add_session_record()`, call `flush_auxiliary_usage()` to get
      auxiliary entries since last flush
    - Calculate auxiliary cost using `calculate_cost()` for each entry
    - Add auxiliary tokens and cost to the running totals
    - _Requirements: 34-REQ-1.3, 34-REQ-1.4_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest tests/unit/reporting/test_cost_reporting.py::TestAuxiliaryIntegration tests/unit/reporting/test_cost_reporting.py::TestArchetypeTracking tests/unit/reporting/test_cost_reporting.py::TestBackwardCompat -v`
    - [x] Property tests pass: `uv run pytest tests/property/core/test_token_tracking_props.py::TestTokenConservation tests/property/core/test_token_tracking_props.py::TestArchetypePreserved -v`
    - [x] All existing tests still pass: `uv run pytest -x -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/engine/state.py agent_fox/engine/session_lifecycle.py`
    - [x] Requirements 34-REQ-1.3, 34-REQ-1.4, 34-REQ-3.* met

- [x] 4. Per-archetype and per-spec reporting
  - [x] 4.1 Add per-archetype cost aggregation to `StatusReport`
    - Add `cost_by_archetype: dict[str, float]` field
    - Aggregate from `session_history` grouped by `record.archetype`
    - _Requirements: 34-REQ-3.3_

  - [x] 4.2 Add per-spec cost aggregation to `StatusReport`
    - Add `cost_by_spec: dict[str, float]` field
    - Extract spec name from `node_id` (prefix before last colon)
    - Aggregate from `session_history` grouped by spec name
    - _Requirements: 34-REQ-4.1, 34-REQ-4.2, 34-REQ-4.E1_

  - [x] 4.3 Update formatters to render new breakdowns
    - Add per-archetype cost table to `format_status_report()`
    - Add per-spec cost table to `format_status_report()`
    - _Requirements: 34-REQ-3.3, 34-REQ-4.1_

  - [x] 4.V Verify task group 4
    - [x] Spec tests pass: `uv run pytest tests/unit/reporting/test_cost_reporting.py::TestPerSpecCost -v`
    - [x] All existing tests still pass: `uv run pytest -x -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/reporting/status.py agent_fox/reporting/formatters.py`
    - [x] Requirements 34-REQ-3.3, 34-REQ-4.* met

- [x] 5. Instrument auxiliary call sites and checkpoint
  - [x] 5.1 Instrument memory fact extraction
    - Add `record_auxiliary_usage()` call after `client.messages.create()`
      in `agent_fox/memory/extraction.py`
    - Handle missing `usage` attribute gracefully
    - _Requirements: 34-REQ-1.5, 34-REQ-1.E1, 34-REQ-1.E2_

  - [x] 5.2 Instrument causal link extraction
    - Add `record_auxiliary_usage()` call after `client.messages.create()`
      in `agent_fox/engine/knowledge_harvest.py`
    - _Requirements: 34-REQ-1.5_

  - [x] 5.3 Instrument remaining call sites
    - `agent_fox/spec/ai_validation.py` (4 call sites)
    - `agent_fox/fix/clusterer.py` (1 call site)
    - `agent_fox/routing/assessor.py` (1 call site)
    - `agent_fox/knowledge/query.py` (1 call site)
    - _Requirements: 34-REQ-1.5_

  - [x] 5.4 Verify all call sites instrumented (TS-34-5)
    - Grep all six files for `record_auxiliary_usage`
    - _Test Spec: TS-34-5_

  - [x] 5.5 Update documentation
    - Update `docs/cli-reference.md` for new `status` output format
    - Document `[pricing]` config section
    - _Requirements: documentation_

  - [x] 5.V Verify task group 5
    - [x] All spec tests pass: `uv run pytest tests/unit/core/test_token_tracker.py tests/unit/core/test_pricing.py tests/unit/reporting/test_cost_reporting.py tests/property/core/test_token_tracking_props.py -v`
    - [x] Full test suite passes: `uv run pytest -x -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [x] All 34-REQ-* acceptance criteria met

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 34-REQ-1.1 | TS-34-1 | 2.1 | `test_token_tracker.py::TestTokenAccumulator::test_records_usage` |
| 34-REQ-1.2 | TS-34-2 | 2.1 | `test_token_tracker.py::TestTokenAccumulator::test_reports_immediately` |
| 34-REQ-1.3 | TS-34-3 | 3.3 | `test_cost_reporting.py::TestAuxiliaryIntegration::test_aux_tokens_in_state` |
| 34-REQ-1.4 | TS-34-4 | 3.3 | `test_cost_reporting.py::TestAuxiliaryIntegration::test_aux_cost_in_state` |
| 34-REQ-1.5 | TS-34-5 | 5.1-5.3 | `test_cost_reporting.py::TestCallSiteInstrumentation::test_all_sites` |
| 34-REQ-1.E1 | TS-34-E1 | 2.1 | `test_token_tracker.py::TestAccumulatorEdgeCases::test_failed_call` |
| 34-REQ-1.E2 | TS-34-E2 | 5.1 | `test_token_tracker.py::TestAccumulatorEdgeCases::test_missing_usage` |
| 34-REQ-2.1 | TS-34-6 | 2.2 | `test_pricing.py::TestPricingConfig::test_defaults` |
| 34-REQ-2.2 | TS-34-6 | 2.2 | `test_pricing.py::TestPricingConfig::test_defaults` |
| 34-REQ-2.3 | TS-34-7 | 2.3 | `test_pricing.py::TestPricingConfig::test_cost_uses_config` |
| 34-REQ-2.4 | TS-34-8 | 2.3 | `test_pricing.py::TestPricingConfig::test_unknown_model_zero` |
| 34-REQ-2.E1 | TS-34-E3 | 2.2 | `test_pricing.py::TestPricingEdgeCases::test_missing_section` |
| 34-REQ-2.E2 | TS-34-E4 | 2.2 | `test_pricing.py::TestPricingEdgeCases::test_negative_clamped` |
| 34-REQ-3.1 | TS-34-9 | 3.1 | `test_cost_reporting.py::TestArchetypeTracking::test_default_archetype` |
| 34-REQ-3.2 | TS-34-10 | 3.2 | `test_cost_reporting.py::TestArchetypeTracking::test_archetype_from_runner` |
| 34-REQ-3.3 | TS-34-11 | 4.1 | `test_cost_reporting.py::TestArchetypeTracking::test_status_per_archetype` |
| 34-REQ-3.E1 | TS-34-E5 | 3.1 | `test_cost_reporting.py::TestBackwardCompat::test_old_record_no_archetype` |
| 34-REQ-4.1 | TS-34-12 | 4.2 | `test_cost_reporting.py::TestPerSpecCost::test_status_per_spec` |
| 34-REQ-4.2 | TS-34-13 | 4.2 | `test_cost_reporting.py::TestPerSpecCost::test_spec_name_extraction` |
| 34-REQ-4.E1 | TS-34-E6 | 4.2 | `test_cost_reporting.py::TestBackwardCompat::test_node_id_no_colon` |
| 34-REQ-5.1 | TS-34-6 | 2.2 | `test_pricing.py::TestPricingConfig::test_defaults` |
| 34-REQ-5.2 | TS-34-14 | 2.3 | `test_pricing.py::TestModelEntryCleanup::test_no_pricing_fields` |
| Property 1 | TS-34-P1 | 2.1 | `test_token_tracking_props.py::TestAccumulatorCompleteness` |
| Property 2 | TS-34-P2 | 3.3 | `test_token_tracking_props.py::TestTokenConservation` |
| Property 3 | TS-34-P3 | 2.3 | `test_token_tracking_props.py::TestPricingConfigPrecedence` |
| Property 4 | TS-34-P4 | 2.2 | `test_token_tracking_props.py::TestPricingDefaultsPresent` |
| Property 5 | TS-34-P5 | 3.1 | `test_token_tracking_props.py::TestArchetypePreserved` |
| Property 6 | TS-34-P6 | 4.2 | `test_token_tracking_props.py::TestPerSpecAggregation` |

## Notes

- The token accumulator is a process-level singleton. In parallel execution,
  multiple sessions share the same accumulator. The `threading.Lock` ensures
  thread safety. The `flush()` at session boundaries collects ALL auxiliary
  tokens since the last flush — this is acceptable because auxiliary calls
  are tied to the session that triggered them.
- When updating `calculate_cost()` signature, grep for all callers to avoid
  breaking existing code. Key callers: `session_lifecycle.py:370`,
  `standup.py` (cost breakdown), and tests.
- The `ModelEntry` dataclass changes are breaking — existing tests that
  construct `ModelEntry(...)` with pricing args will need updating.
- Existing `state.jsonl` files with `SessionRecord` entries lacking
  `archetype` are handled by defaulting to `"coder"` in `from_dict()`.
