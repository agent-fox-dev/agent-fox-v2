# Tasks: Fix Issue #269 — API Connection Drops Cause 0ms Session Failures

## Group 1: Transport-Layer Retry and Error Distinction

- [x] Add `is_transport_error: bool = False` to `ResultMessage` in `protocol.py`
- [x] Add `import asyncio` and retry constants to `claude.py`
- [x] Replace `execute()` single-shot streaming with 3-attempt retry-with-backoff loop
- [x] Add `is_transport_error` to `SessionOutcome` in `sink.py`
- [x] Add `is_transport_error` to `_QueryExecutionState` and propagate in `session.py`
- [x] Add `is_transport_error` to `SessionRecord` in `state.py` and `invoke_runner`
- [x] Propagate `is_transport_error` from `SessionOutcome` in `session_lifecycle.py`
- [x] Skip escalation ladder in `result_handler._handle_failure()` for transport errors
- [x] Add transport retry tests (AC-1 through AC-5) to `test_claude.py`
- [x] Add transport error result handler tests (AC-6, AC-7) in `test_transport_error_handling.py`
- [x] Update `test_sdk_features.py` fake_stream to yield ResultMessage (prevents retry side effects)
- [x] Update existing `TestStreamingErrorYieldsResult` tests to mock sleep and assert `is_transport_error=True`
