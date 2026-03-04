# Code Audit Report

Generated: 2026-03-04  
Branch: `develop`  
Scope: runtime behavior review of planning, orchestration, session execution, and test validity.

## Executive Summary

The current implementation has critical runtime reliability issues that can make runs appear successful when they are not, and the current test strategy does not reliably detect these failures. The most severe problems are in the coding-session execution path and plan-cache semantics.

## Environment Note

In this environment, the test suite is not fully green:

- `956 passed, 3 failed`
- Failing file: `tests/unit/ui/test_banner.py` (ANSI styling assertions)

## Findings (ordered by severity)

### P0 - Session can be marked completed without a terminal result

`agent_fox/session/runner.py` initializes session status to `"completed"` and only flips to failed if a `result` message has `is_error=True`. If no `result` message is ever emitted, the function still returns completed.

- Evidence:
  - `agent_fox/session/runner.py:129`
  - `agent_fox/session/runner.py:164`
  - `agent_fox/session/runner.py:181`
- Reproduction performed:
  - Patched `query()` to emit only an assistant message.
  - `run_session(...)` returned: `status="completed"`, `input_tokens=0`, `output_tokens=0`, `error_message=None`.

Impact: false positives in task completion and downstream orchestration state.

### P0 - Tool permission callback path is likely broken at runtime

The session runner uses `can_use_tool` with a one-message async prompt stream. In the SDK, streaming input calls `end_input()` after the stream is exhausted, closing stdin. Control-protocol requests used for tool permissions write to that channel, so permission callbacks can fail after stream closure.

- Project evidence:
  - `agent_fox/session/runner.py:147`
  - `agent_fox/session/runner.py:158`
- SDK evidence (installed in `.venv`):
  - `.venv/lib/python3.12/site-packages/claude_code_sdk/_internal/query.py:472`
  - `.venv/lib/python3.12/site-packages/claude_code_sdk/_internal/query.py:480`
  - `.venv/lib/python3.12/site-packages/claude_code_sdk/_internal/transport/subprocess_cli.py:272`

Impact: commands may fail unpredictably during live sessions when tool permission checks are needed.

### P1 - Plan cache ignores `--fast` and `--spec` semantics

`plan` returns cached `plan.json` whenever it exists and `--reanalyze` is not set, regardless of current `--fast` and `--spec` flags.

- Evidence:
  - `agent_fox/cli/plan.py:153`
- Reproductions performed:
  - Run `plan`, then `plan --fast` -> cached plan remained `metadata.fast_mode=false`, optional nodes still included.
  - Run `plan`, then `plan --spec 01_alpha` -> cached plan still contained all prior specs, `filtered_spec` unchanged.

Impact: users can request narrowed/fast planning but receive stale incompatible plans.

### P1 - Sink records success when harvest actually failed

When `harvest()` raises `IntegrationError`, `NodeSessionRunner` correctly sets local record status to failed, but sink recording still writes the original successful `SessionOutcome`.

- Evidence:
  - `agent_fox/engine/session_lifecycle.py:261`
  - `agent_fox/engine/session_lifecycle.py:274`
  - `agent_fox/engine/session_lifecycle.py:304`
- Reproduction performed:
  - Forced `harvest()` to raise `IntegrationError`.
  - Returned `SessionRecord.status == "failed"` while captured sink outcome had `status == "completed"`.

Impact: DuckDB/audit data diverges from actual orchestration result, breaking observability and trust.

### P2 - CLI overrides bypass config validation/clamping

`_apply_overrides()` uses `model_copy(update=...)` directly, which does not enforce field validators by default for updated values.

- Evidence:
  - `agent_fox/cli/code.py:75`
- Reproduction performed:
  - `OrchestratorConfig().model_copy(update={"parallel": 0}).parallel` produced `0`.

Impact: invalid runtime config can be injected via CLI path and behave differently from validated config file values.

### P2 - Timeout path does not preserve partial metrics

Comments and requirements indicate partial metrics should survive timeout, but timeout returns mostly zeroed values because execution state is not persisted across cancellation in `run_session`.

- Evidence:
  - `agent_fox/session/runner.py:66`
  - `agent_fox/session/runner.py:91`

Impact: inaccurate cost and token reporting for timed-out sessions.

## Test Validity Assessment

### 1) Missing integration coverage for critical runtime path

There is no integration test for `agent-fox code` end-to-end behavior. Current integration suite contains only:

- `tests/integration/test_init.py`
- `tests/integration/test_lint_spec.py`
- `tests/integration/test_plan.py`

### 2) `plan --fast` and `plan --spec` tests are non-semantic

Integration tests for these flags assert only command success, not resulting plan correctness.

- Evidence:
  - `tests/integration/test_plan.py:197`
  - `tests/integration/test_plan.py:207`

### 3) `code` command tests are heavily mocked

Most tests patch orchestrator and filesystem interactions, so real control-flow faults are not exercised.

- Evidence:
  - `tests/unit/cli/test_code.py:93`
  - `tests/unit/cli/test_code.py:167`
  - `tests/unit/cli/test_code.py:479`

### 4) Overall test signal is currently unstable

Even before code changes, full suite run in this environment is not fully green (`3` failures in banner style tests).

## Comparison Note vs v1

The legacy repository (`https://github.com/agent-fox-dev/agent-fox`) contained stronger session-path protections (explicit no-result failure handling and stream/timeout control). The current v2 implementation appears to have regressed in these areas.
