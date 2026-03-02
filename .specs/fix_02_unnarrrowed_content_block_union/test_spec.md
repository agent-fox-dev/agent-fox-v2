# Test Specification: Fix Unnarrowed Content Block Union

**Spec:** fix_02_unnarrowed_content_block_union

## TS-FIX-02-1: mypy Type Check Passes

**Requirement:** FIX-02-REQ-2.1, FIX-02-REQ-2.2

**Test Contract:** Run `uv run mypy agent_fox/spec/ai_validator.py` and verify
zero `[union-attr]` errors and zero new errors.

**Verification:**
```bash
uv run mypy agent_fox/spec/ai_validator.py
```
- Expected: exit code 0, or output contains "Success" with no `[union-attr]`
  lines.

## TS-FIX-02-2: Existing Tests Pass

**Requirement:** FIX-02-REQ-3.2

**Test Contract:** All tests in `tests/unit/spec/test_ai_validator.py` pass
without modification.

**Verification:**
```bash
uv run pytest tests/unit/spec/test_ai_validator.py -v
```
- Expected: all tests pass (exit code 0).

## TS-FIX-02-3: Non-TextBlock Graceful Handling

**Requirement:** FIX-02-REQ-1.2, FIX-02-REQ-1.3

**Test Contract:** When the API response's first content block lacks a `.text`
attribute (e.g. a `ToolUseBlock`), `analyze_acceptance_criteria` returns an
empty list and logs a warning.

**Precondition:** Mock `response.content[0]` with an object that has no `.text`
attribute (e.g. `MagicMock(spec=[])` — a MagicMock with an empty spec so
attribute access raises `AttributeError`; alternatively, an object where
`getattr(obj, "text", None)` returns `None`).

**Verification:**
- `findings` is `[]`
- A warning log containing `"has no text content"` is emitted.

## TS-FIX-02-4: TextBlock Happy Path

**Requirement:** FIX-02-REQ-1.1, FIX-02-REQ-3.1

**Test Contract:** When the API response's first content block is a real
`TextBlock` instance, the function correctly extracts and parses the text.

**Note:** Existing tests already cover this indirectly via `MagicMock(text=...)`,
but this test would use an actual `TextBlock` instance if desired. The existing
tests in `TestAIFindingsSeverityAndRule` and `TestAIResponseParsing` serve as
sufficient coverage for this contract.
