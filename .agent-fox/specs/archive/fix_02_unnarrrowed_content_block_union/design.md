# Design: Fix Unnarrowed Content Block Union

## Architecture

This is a single-file, single-function fix. No architectural changes are needed.

### Change Summary

**File:** `agent_fox/spec/ai_validator.py`

1. **Add import** (line 12 area): `from anthropic.types import TextBlock`
2. **Replace line 97** with a type-narrowing block following the established
   pattern from `agent_fox/memory/extraction.py`.

### Before (line 96-97)

```python
# Parse the response
response_text = response.content[0].text
```

### After (lines 96-106)

```python
# Parse the response — narrow the content block union to TextBlock
first_block = response.content[0]
if isinstance(first_block, TextBlock):
    response_text: str = first_block.text
else:
    # Fallback for types with a .text attribute (e.g. test mocks)
    maybe_text: str | None = getattr(first_block, "text", None)
    if maybe_text is None:
        logger.warning(
            "AI response for spec '%s' has no text content, skipping",
            spec_name,
        )
        return []
    response_text = maybe_text
```

## Correctness Properties

### CP-1: Type Safety
The `isinstance(first_block, TextBlock)` guard narrows the union type so that
`first_block.text` is statically known to be valid. mypy can verify this.

### CP-2: Exhaustive Handling
All branches of the union are handled:
- `TextBlock` → direct `.text` access (happy path)
- Any block with a `.text` attribute → `getattr` fallback
- Any block without `.text` → warning + empty return

### CP-3: Pattern Consistency
The implementation mirrors `agent_fox/memory/extraction.py` lines 76-85
exactly, ensuring codebase consistency.

### CP-4: Backward Compatibility
- The happy path (first block is `TextBlock`) produces identical behavior.
- Test mocks using `MagicMock(text=...)` will hit the `getattr` fallback and
  continue to work because `MagicMock` is not an instance of `TextBlock` but
  does have a `.text` attribute.

## Dependencies

- `anthropic.types.TextBlock` — already available in the project's dependencies
  (used in `agent_fox/memory/extraction.py`).
