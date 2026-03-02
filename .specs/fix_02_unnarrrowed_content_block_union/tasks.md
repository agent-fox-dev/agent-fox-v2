# Tasks: Fix Unnarrowed Content Block Union

**Spec:** fix_02_unnarrowed_content_block_union

- [x] 1. Add isinstance guard to narrow content block union type
  - [x] 1.1 Add `from anthropic.types import TextBlock` import to `agent_fox/spec/ai_validator.py`
  - [x] 1.2 Replace `response_text = response.content[0].text` (line 97) with isinstance-guarded block following the pattern from `agent_fox/memory/extraction.py`: extract first block, check `isinstance(first_block, TextBlock)`, use `getattr` fallback, and return `[]` with warning if no text
  - [x] 1.V Verify: run `uv run mypy agent_fox/spec/ai_validator.py` — expect zero `[union-attr]` errors
- [ ] 2. Validate existing tests still pass
  - [ ] 2.1 Run `uv run pytest tests/unit/spec/test_ai_validator.py -v` — all existing tests must pass without modification
  - [ ] 2.V Verify: confirm zero test failures
