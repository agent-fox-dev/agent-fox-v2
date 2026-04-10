# Test Specification: Fix Branch Push to Upstream

## Overview

Tests validate the config field, branch naming, push gating, ordering, and
error handling. Unit tests mock `push_to_remote` and the platform; property
tests verify branch-name and push-gating invariants; integration smoke tests
exercise the full pipeline path.

## Test Cases

### TS-93-1: Config field defaults to false

**Requirement:** 93-REQ-1.2
**Type:** unit
**Description:** Verify that `NightShiftConfig` defaults `push_fix_branch` to
`False` when the field is absent.

**Preconditions:**
- No `push_fix_branch` key in the config dict.

**Input:**
- `NightShiftConfig()` (empty constructor)

**Expected:**
- `config.push_fix_branch` is `False`

**Assertion pseudocode:**
```
config = NightShiftConfig()
ASSERT config.push_fix_branch == False
```

---

### TS-93-2: Config field reads true from dict

**Requirement:** 93-REQ-1.1
**Type:** unit
**Description:** Verify that `NightShiftConfig` reads `push_fix_branch = true`
correctly.

**Preconditions:**
- Config dict contains `{"push_fix_branch": True}`.

**Input:**
- `NightShiftConfig(push_fix_branch=True)`

**Expected:**
- `config.push_fix_branch` is `True`

**Assertion pseudocode:**
```
config = NightShiftConfig(push_fix_branch=True)
ASSERT config.push_fix_branch == True
```

---

### TS-93-3: Branch name includes issue number

**Requirement:** 93-REQ-2.1, 93-REQ-2.2
**Type:** unit
**Description:** Verify that `sanitise_branch_name` includes the issue number
in the branch name.

**Preconditions:**
- None.

**Input:**
- `title = "Unused imports in utils"`
- `issue_number = 42`

**Expected:**
- Branch name is `"fix/42-unused-imports-in-utils"`

**Assertion pseudocode:**
```
result = sanitise_branch_name("Unused imports in utils", 42)
ASSERT result == "fix/42-unused-imports-in-utils"
ASSERT "42" in result
```

---

### TS-93-4: Push called before harvest when enabled

**Requirement:** 93-REQ-3.1
**Type:** integration
**Description:** Verify that the fix branch is pushed to origin before
`_harvest_and_push` when `push_fix_branch` is `true`.

**Preconditions:**
- `push_fix_branch = True` in config.
- Mock platform with stub methods.
- Mock `push_to_remote` returning `True`.
- Mock `_harvest_and_push` returning `"merged"`.
- Coder-reviewer loop returns `True`.

**Input:**
- An `IssueResult` with `number=1`, `title="test issue"`.
- Non-empty issue body.

**Expected:**
- `push_to_remote` is called with `force=True` before `_harvest_and_push`.
- Both are called exactly once.

**Assertion pseudocode:**
```
call_order = []
mock_push = Mock(side_effect=lambda *a, **k: call_order.append("push"))
mock_harvest = Mock(side_effect=lambda *a, **k: call_order.append("harvest"))
# ... wire mocks ...
await pipeline.process_issue(issue, issue_body="fix this")
ASSERT call_order == ["push", "harvest"]
ASSERT mock_push.called_with(force=True)
```

---

### TS-93-5: Push NOT called when disabled

**Requirement:** 93-REQ-3.3
**Type:** unit
**Description:** Verify that `push_to_remote` is never called for the fix
branch when `push_fix_branch` is `false`.

**Preconditions:**
- `push_fix_branch = False` in config (default).
- Mock platform and push_to_remote.
- Coder-reviewer loop returns `True`.

**Input:**
- An `IssueResult` with `number=1`, `title="test issue"`.
- Non-empty issue body.

**Expected:**
- `push_to_remote` is NOT called for the fix branch.

**Assertion pseudocode:**
```
await pipeline.process_issue(issue, issue_body="fix this")
# push_to_remote may be called for develop (via harvest), but NOT for fix branch
ASSERT mock_push_fix_branch.not_called
```

---

### TS-93-6: Force-push flag is set

**Requirement:** 93-REQ-3.2
**Type:** unit
**Description:** Verify that `push_to_remote` is called with `force=True`
when pushing the fix branch.

**Preconditions:**
- `push_fix_branch = True` in config.
- Mock `push_to_remote`.

**Input:**
- A fix branch push via `_push_fix_branch_upstream`.

**Expected:**
- `push_to_remote` is called with keyword argument `force=True`.

**Assertion pseudocode:**
```
await pipeline._push_fix_branch_upstream(spec, workspace)
ASSERT mock_push_to_remote.call_args.kwargs["force"] == True
```

---

### TS-93-7: Push failure does not block harvest

**Requirement:** 93-REQ-3.E1, 93-REQ-3.E2
**Type:** unit
**Description:** Verify that when the push fails, harvest still runs and
a warning is logged with the failure reason.

**Preconditions:**
- `push_fix_branch = True` in config.
- `push_to_remote` raises `Exception("network error")`.
- Mock `_harvest_and_push` returning `"merged"`.
- Coder-reviewer loop returns `True`.

**Input:**
- An `IssueResult` with valid body.

**Expected:**
- Warning is logged containing the failure reason.
- `_harvest_and_push` is still called after the push failure.
- `process_issue` completes without raising.

**Assertion pseudocode:**
```
mock_push = Mock(side_effect=Exception("network error"))
await pipeline.process_issue(issue, issue_body="fix this")
ASSERT "network error" in caplog.text
ASSERT mock_harvest.called
```

---

### TS-93-8: Independence from merge_strategy

**Requirement:** 93-REQ-4.1
**Type:** unit
**Description:** Verify that the push behavior works identically regardless
of `merge_strategy` setting.

**Preconditions:**
- `push_fix_branch = True`.
- Two configs: one with `merge_strategy = "direct"`, one with
  `merge_strategy = "pr"`.
- Mock platform, push, and harvest.

**Input:**
- Same issue for both configs.

**Expected:**
- `push_to_remote` is called with `force=True` in both cases.

**Assertion pseudocode:**
```
for strategy in ["direct", "pr"]:
    config = make_config(push_fix_branch=True, merge_strategy=strategy)
    pipeline = FixPipeline(config, platform)
    await pipeline.process_issue(issue, issue_body="fix this")
    ASSERT mock_push.called_with(force=True)
```

---

### TS-93-9: Remote branch not deleted after merge

**Requirement:** 93-REQ-3.4
**Type:** unit
**Description:** Verify that no remote branch deletion is performed after the
fix is merged.

**Preconditions:**
- `push_fix_branch = True`.
- Coder-reviewer loop passes, harvest succeeds.

**Input:**
- An `IssueResult` with valid body.

**Expected:**
- No call to `run_git` with `["push", "origin", "--delete", ...]` or
  `["push", "origin", ":{branch}"]`.

**Assertion pseudocode:**
```
await pipeline.process_issue(issue, issue_body="fix this")
for call in mock_run_git.call_args_list:
    ASSERT "--delete" not in call.args[0]
    ASSERT not call.args[0][-1].startswith(":")
```

## Edge Case Tests

### TS-93-E1: Non-boolean push_fix_branch rejected

**Requirement:** 93-REQ-1.E1
**Type:** unit
**Description:** Verify that a non-boolean value for `push_fix_branch` raises
a validation error.

**Preconditions:**
- None.

**Input:**
- `NightShiftConfig(push_fix_branch="yes")`

**Expected:**
- `ValidationError` is raised.

**Assertion pseudocode:**
```
ASSERT_RAISES ValidationError:
    NightShiftConfig(push_fix_branch="yes")
```

---

### TS-93-E2: Empty title produces valid branch name

**Requirement:** 93-REQ-2.E1
**Type:** unit
**Description:** Verify that an empty title produces a branch name with only
the issue number.

**Preconditions:**
- None.

**Input:**
- `title = ""`
- `issue_number = 99`

**Expected:**
- Branch name is `"fix/99"`

**Assertion pseudocode:**
```
result = sanitise_branch_name("", 99)
ASSERT result == "fix/99"
```

---

### TS-93-E3: Special-chars-only title produces valid branch name

**Requirement:** 93-REQ-2.E1
**Type:** unit
**Description:** Verify that a title with only special characters produces a
branch name with only the issue number.

**Preconditions:**
- None.

**Input:**
- `title = "!!@@##$$"`
- `issue_number = 7`

**Expected:**
- Branch name is `"fix/7"`

**Assertion pseudocode:**
```
result = sanitise_branch_name("!!@@##$$", 7)
ASSERT result == "fix/7"
```

---

### TS-93-E4: Push failure logs reason

**Requirement:** 93-REQ-3.E2
**Type:** unit
**Description:** Verify that the failure reason from `push_to_remote` is
included in the warning log.

**Preconditions:**
- `push_fix_branch = True`.
- `push_to_remote` returns `False` (push rejected).

**Input:**
- A call to `_push_fix_branch_upstream`.

**Expected:**
- Warning log message mentions the branch name and failure.

**Assertion pseudocode:**
```
mock_push = Mock(return_value=False)
result = await pipeline._push_fix_branch_upstream(spec, workspace)
ASSERT result == False
ASSERT spec.branch_name in caplog.text
ASSERT "warning" in caplog.records[-1].levelname.lower()
```

## Property Test Cases

### TS-93-P1: Push Gating Invariant

**Property:** Property 1 from design.md
**Validates:** 93-REQ-3.3
**Type:** property
**Description:** When `push_fix_branch` is `False`, `push_to_remote` is never
called for the fix branch regardless of other config values.

**For any:** `NightShiftConfig` with `push_fix_branch=False` and arbitrary
values for other fields (`merge_strategy`, `issue_check_interval`, etc.)
**Invariant:** `_push_fix_branch_upstream` is not invoked during
`process_issue`.

**Assertion pseudocode:**
```
FOR ANY config IN nightshift_configs(push_fix_branch=False):
    pipeline = FixPipeline(config, mock_platform)
    await pipeline.process_issue(issue, issue_body="body")
    ASSERT mock_push_fix.not_called
```

---

### TS-93-P2: Branch Name Always Contains Issue Number

**Property:** Property 2 from design.md
**Validates:** 93-REQ-2.1, 93-REQ-2.2
**Type:** property
**Description:** For any issue number and title, the branch name contains the
issue number as a substring.

**For any:** `issue_number` in positive integers, `title` in arbitrary strings
**Invariant:** `str(issue_number)` is a substring of
`sanitise_branch_name(title, issue_number)`

**Assertion pseudocode:**
```
FOR ANY (issue_number, title) IN (st.integers(min_value=1), st.text()):
    result = sanitise_branch_name(title, issue_number)
    ASSERT str(issue_number) in result
    ASSERT result.startswith("fix/")
```

---

### TS-93-P3: Push Before Harvest Ordering

**Property:** Property 3 from design.md
**Validates:** 93-REQ-3.1
**Type:** property
**Description:** When push is enabled and coder-reviewer passes, push always
precedes harvest in the call sequence.

**For any:** `issue_number` in positive integers, `title` in short strings
**Invariant:** In the call sequence, "push" appears before "harvest".

**Assertion pseudocode:**
```
FOR ANY (issue_number, title) IN (st.integers(min_value=1), st.text(max_size=50)):
    call_order = []
    # wire mocks to record call order
    await pipeline.process_issue(issue, issue_body="body")
    push_idx = call_order.index("push")
    harvest_idx = call_order.index("harvest")
    ASSERT push_idx < harvest_idx
```

---

### TS-93-P4: Push Failure Resilience

**Property:** Property 4 from design.md
**Validates:** 93-REQ-3.E1, 93-REQ-3.E2
**Type:** property
**Description:** When push raises any exception, harvest still executes and
no exception propagates.

**For any:** Exception type in common exception types (RuntimeError, OSError,
TimeoutError, ConnectionError)
**Invariant:** `_harvest_and_push` is called and `process_issue` does not
raise.

**Assertion pseudocode:**
```
FOR ANY exc_type IN st.sampled_from([RuntimeError, OSError, TimeoutError]):
    mock_push.side_effect = exc_type("fail")
    await pipeline.process_issue(issue, issue_body="body")  # no raise
    ASSERT mock_harvest.called
```

---

### TS-93-P5: Force Push Semantics

**Property:** Property 5 from design.md
**Validates:** 93-REQ-3.2
**Type:** property
**Description:** Every call to `push_to_remote` for a fix branch uses
`force=True`.

**For any:** `issue_number` in positive integers
**Invariant:** `push_to_remote` is called with `force=True`.

**Assertion pseudocode:**
```
FOR ANY issue_number IN st.integers(min_value=1, max_value=99999):
    await pipeline._push_fix_branch_upstream(spec, workspace)
    ASSERT mock_push.call_args.kwargs["force"] == True
```

## Integration Smoke Tests

### TS-93-SMOKE-1: Full pipeline with push enabled

**Execution Path:** Path 1 from design.md
**Description:** Verify end-to-end fix pipeline with `push_fix_branch=true`
pushes the branch before harvest.

**Setup:** Mock platform (add_issue_comment, close_issue, remove_label).
Mock `push_to_remote` returning `True`. Mock session runner (triage, coder,
reviewer all succeed). Mock harvest returning `"merged"`. Do NOT mock
`FixPipeline.process_issue`, `_push_fix_branch_upstream`, or
`_coder_review_loop`.

**Trigger:** `await pipeline.process_issue(issue, issue_body="fix bug")`

**Expected side effects:**
- `push_to_remote` called with the fix branch name and `force=True`.
- `_harvest_and_push` called after push.
- Issue closed with completion message.

**Must NOT satisfy with:** Mocking `_push_fix_branch_upstream` (it must
execute the real code path). Mocking `process_issue`.

**Assertion pseudocode:**
```
config = make_config(push_fix_branch=True)
platform = MockPlatform()
pipeline = FixPipeline(config, platform)
pipeline._run_session = AsyncMock(return_value=mock_outcome)
pipeline._harvest_and_push = AsyncMock(return_value="merged")

call_order = []
original_push = pipeline._push_fix_branch_upstream
async def tracking_push(*a, **k):
    call_order.append("push")
    return await original_push(*a, **k)
pipeline._push_fix_branch_upstream = tracking_push

original_harvest = pipeline._harvest_and_push
async def tracking_harvest(*a, **k):
    call_order.append("harvest")
    return await original_harvest(*a, **k)
pipeline._harvest_and_push = tracking_harvest

await pipeline.process_issue(issue, issue_body="fix bug")
ASSERT "push" in call_order
ASSERT "harvest" in call_order
ASSERT call_order.index("push") < call_order.index("harvest")
ASSERT platform.close_issue.called
```

---

### TS-93-SMOKE-2: Full pipeline with push disabled

**Execution Path:** Path 2 from design.md
**Description:** Verify end-to-end fix pipeline with `push_fix_branch=false`
(default) does not push the fix branch.

**Setup:** Same as SMOKE-1 but `push_fix_branch=False`. Mock
`push_to_remote`. Do NOT mock `FixPipeline.process_issue`.

**Trigger:** `await pipeline.process_issue(issue, issue_body="fix bug")`

**Expected side effects:**
- `push_to_remote` is NOT called for the fix branch.
- `_harvest_and_push` is called.
- Issue closed with completion message.

**Must NOT satisfy with:** Mocking `process_issue`.

**Assertion pseudocode:**
```
config = make_config(push_fix_branch=False)
pipeline = FixPipeline(config, platform)
pipeline._run_session = AsyncMock(return_value=mock_outcome)
pipeline._harvest_and_push = AsyncMock(return_value="merged")

await pipeline.process_issue(issue, issue_body="fix bug")
ASSERT mock_push_to_remote.not_called_with_fix_branch
ASSERT pipeline._harvest_and_push.called
ASSERT platform.close_issue.called
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 93-REQ-1.1 | TS-93-2 | unit |
| 93-REQ-1.2 | TS-93-1 | unit |
| 93-REQ-1.E1 | TS-93-E1 | unit |
| 93-REQ-2.1 | TS-93-3 | unit |
| 93-REQ-2.2 | TS-93-3 | unit |
| 93-REQ-2.E1 | TS-93-E2, TS-93-E3 | unit |
| 93-REQ-3.1 | TS-93-4 | integration |
| 93-REQ-3.2 | TS-93-6 | unit |
| 93-REQ-3.3 | TS-93-5 | unit |
| 93-REQ-3.4 | TS-93-9 | unit |
| 93-REQ-3.E1 | TS-93-7 | unit |
| 93-REQ-3.E2 | TS-93-E4 | unit |
| 93-REQ-4.1 | TS-93-8 | unit |
| Property 1 | TS-93-P1 | property |
| Property 2 | TS-93-P2 | property |
| Property 3 | TS-93-P3 | property |
| Property 4 | TS-93-P4 | property |
| Property 5 | TS-93-P5 | property |
| Path 1 | TS-93-SMOKE-1 | integration |
| Path 2 | TS-93-SMOKE-2 | integration |
