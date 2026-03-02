# PRD: Fix Unnarrowed Content Block Union in AI Validator

## Problem

The `agent_fox/spec/ai_validator.py` module accesses `.text` on an Anthropic API
content block union type (`response.content[0].text` at line 97) without first
narrowing the type to `TextBlock`. This produces 11 mypy `[union-attr]` errors
because the other union members (`ThinkingBlock`, `RedactedThinkingBlock`,
`ToolUseBlock`, `ServerToolUseBlock`, `WebSearchToolResultBlock`,
`WebFetchToolResultBlock`, `CodeExecutionToolResultBlock`,
`BashCodeExecutionToolResultBlock`, `TextEditorCodeExecutionToolResultBlock`,
`ToolSearchToolResultBlock`, `ContainerUploadBlock`) do not have a `.text`
attribute.

## Root Cause

Line 97 of `ai_validator.py`:
```python
response_text = response.content[0].text
```

This directly accesses `.text` without an `isinstance` check to narrow the union
to `TextBlock`.

## Existing Pattern

The codebase already solves this in `agent_fox/memory/extraction.py` (lines 76-85):
```python
first_block = response.content[0]
if isinstance(first_block, TextBlock):
    raw_text: str = first_block.text
else:
    maybe_text: str | None = getattr(first_block, "text", None)
    if maybe_text is None:
        logger.warning("Extraction response has no text content, skipping")
        return []
    raw_text = maybe_text
```

## Goal

Add a type-narrowing `isinstance` guard before accessing `.text`, following the
established pattern. This resolves all 11 mypy errors and adds a graceful
fallback when the first content block is not a `TextBlock`.

## Scope

- **Single file change**: `agent_fox/spec/ai_validator.py`
- **Single import addition**: `from anthropic.types import TextBlock`
- **Lines affected**: 96-97 (replace with ~10 lines)
- **No behavioral change** for the happy path (first block is always `TextBlock`
  in normal API usage)
- **Improved robustness**: graceful handling if the first block is unexpectedly
  not a `TextBlock`

## Clarifications

- The fix follows the exact pattern already established in `extraction.py`.
- The `getattr` fallback preserves compatibility with test mocks that use
  `MagicMock(text=...)` without being actual `TextBlock` instances.
- Existing tests use `MagicMock(text=response_text)` for mock content blocks,
  which will continue to work via the `getattr` fallback path.
