# Requirements: Fix Unnarrowed Content Block Union

**Spec:** fix_02_unnarrowed_content_block_union
**Parent Refs:** 09-REQ-8.1, 09-REQ-8.2, 09-REQ-8.3, 09-REQ-8.E1

## FIX-02-REQ-1: Type-Safe Content Block Access

**FIX-02-REQ-1.1** (Type Narrowing)
When the `analyze_acceptance_criteria` function receives an API response, the
system SHALL narrow the first content block to `TextBlock` using an `isinstance`
check before accessing the `.text` attribute.

**FIX-02-REQ-1.2** (Fallback for Non-TextBlock)
Where the first content block is not a `TextBlock` instance, the system SHALL
attempt to read a `.text` attribute via `getattr` as a fallback.

**FIX-02-REQ-1.3** (Graceful Handling of Missing Text)
Where the first content block has no `.text` attribute, the system SHALL log a
warning and return an empty findings list.

**FIX-02-REQ-1.4** (Import)
The system SHALL import `TextBlock` from `anthropic.types` for use in the
`isinstance` guard.

## FIX-02-REQ-2: Static Type Checking

**FIX-02-REQ-2.1** (mypy Clean)
After the fix, `uv run mypy agent_fox/spec/ai_validator.py` SHALL produce zero
`[union-attr]` errors.

**FIX-02-REQ-2.2** (No New Errors)
The fix SHALL NOT introduce any new mypy errors in `agent_fox/spec/ai_validator.py`.

## FIX-02-REQ-3: Behavioral Preservation

**FIX-02-REQ-3.1** (Happy Path Unchanged)
When the first content block is a `TextBlock`, the function SHALL behave
identically to the current implementation (extract `.text` and parse JSON).

**FIX-02-REQ-3.2** (Existing Tests Pass)
All existing tests in `tests/unit/spec/test_ai_validator.py` SHALL continue
to pass without modification.
