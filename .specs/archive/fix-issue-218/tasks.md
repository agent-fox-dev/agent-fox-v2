# Tasks: Fix Incomplete Prompt Injection Sanitization (Issue #218)

## Task Group 1: Write Failing Tests

- [x] Write failing tests for AC-1 through AC-11 in `tests/unit/session/test_prompt_injection_sanitization.py`

## Task Group 2: Implement Sanitization at All Injection Sites

- [x] `context.py`: import `sanitize_prompt_content` from `agent_fox.core.prompt_safety` (AC-11)
- [x] `context.py` `render_drift_context`: wrap description in `<untrusted-drift-finding-*>` (AC-1)
- [x] `context.py` `render_review_context`: wrap description in `<untrusted-review-finding-*>` (AC-2)
- [x] `context.py` `render_verification_context`: wrap evidence in `<untrusted-verification-evidence-*>` (AC-3)
- [x] `context.py` `assemble_context`: wrap spec file contents in `<untrusted-spec-*>` (AC-4)
- [x] `context.py` `assemble_context`: upgrade memory facts to `sanitize_prompt_content` (AC-5)
- [x] `context.py` `render_prior_group_findings`: wrap description in `<untrusted-prior-finding-*>` (AC-6)
- [x] `session_lifecycle.py` `_build_prompts`: wrap previous_error in `<untrusted-previous-error-*>` (AC-7)
- [x] `nightshift/spec_builder.py` `build_in_memory_spec`: wrap issue title/body in `<untrusted-*>` (AC-8)
- [x] `nightshift/triage.py` `_build_triage_prompt`: wrap issue title/body in `<untrusted-*>` (AC-9)
- [x] `session_lifecycle.py` `build_retry_context`: wrap finding description in `<untrusted-*>` (AC-10)
