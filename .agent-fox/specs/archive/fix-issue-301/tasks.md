# Fix Issue #301 — Wrong Attribution in `standup` Command

## Task Group 1: Fix merge-commit attribution in standup

- [x] Extend `_MERGE_BRANCH_RE` in `agent_fox/reporting/standup.py` to match
      `Merge <type>/<branch> into <target>` patterns (not just `Merge branch '...'`)
- [x] Add regression tests for `Merge fix/...` and `Merge feat/...` commit subjects
      in `tests/unit/reporting/test_standup.py`
