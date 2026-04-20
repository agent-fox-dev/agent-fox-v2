# Tasks: fix-issue-324 — None indexing guard in lifecycle.py

## Task Group 1: Fix and test None-guard for fetchone() in cleanup_facts

- [x] Add None-guard before `fetchone()[0]` at line 396 (active_count query)
- [x] Add None-guard before `fetchone()[0]` at line 409 (active_remaining recount query)
- [x] Add unit tests: fetchone() returns None → active_count defaults to 0 (AC-1)
- [x] Add unit tests: fetchone() returns None → active_remaining defaults to 0 (AC-2)
- [x] Verify normal cleanup_facts behavior preserved (AC-3)
- [x] Verify guard pattern consistent with lines 90-92 and 178-180 (AC-4)
