# Test Specification: Spec Generator

## Overview

Tests are organized into four categories: acceptance criterion tests
(TS-86-N), edge case tests (TS-86-EN), property tests (TS-86-PN), and
integration smoke tests (TS-86-SMOKE-N). Platform extension tests go in
`tests/unit/platform/`, config tests in `tests/unit/nightshift/`, and
spec generator tests in `tests/unit/nightshift/` and
`tests/integration/`.

## Test Cases

### TS-86-1: remove_label sends DELETE request

**Requirement:** 86-REQ-1.1
**Type:** unit
**Description:** Verify `remove_label` sends a DELETE to the correct
GitHub API endpoint.

**Preconditions:**
- GitHubPlatform instance with mock httpx client.

**Input:**
- `issue_number = 42`, `label = "af:spec"`

**Expected:**
- DELETE request sent to `/repos/{owner}/{repo}/issues/42/labels/af:spec`
- Method returns without error.

**Assertion pseudocode:**
```
platform = GitHubPlatform(owner, repo, token)
mock DELETE /repos/owner/repo/issues/42/labels/af%3Aspec -> 204
await platform.remove_label(42, "af:spec")
ASSERT mock.called_once
ASSERT mock.request.method == "DELETE"
```

---

### TS-86-2: remove_label is idempotent on missing label

**Requirement:** 86-REQ-1.2
**Type:** unit
**Description:** Verify `remove_label` succeeds when the label is not
present (404 response).

**Preconditions:**
- GitHubPlatform with mock returning 404.

**Input:**
- `issue_number = 42`, `label = "nonexistent"`

**Expected:**
- No exception raised.

**Assertion pseudocode:**
```
mock DELETE -> 404
await platform.remove_label(42, "nonexistent")
# No exception = pass
```

---

### TS-86-3: list_issue_comments returns ordered comments

**Requirement:** 86-REQ-1.3
**Type:** unit
**Description:** Verify `list_issue_comments` returns `IssueComment`
objects in chronological order.

**Preconditions:**
- GitHubPlatform with mock returning two comments.

**Input:**
- `issue_number = 10`

**Expected:**
- List of two `IssueComment` objects with correct fields.
- First comment has earlier `created_at` than second.

**Assertion pseudocode:**
```
mock GET /repos/owner/repo/issues/10/comments -> [
  {id: 1, body: "first", user: {login: "alice"}, created_at: "2026-01-01T00:00:00Z"},
  {id: 2, body: "second", user: {login: "bob"}, created_at: "2026-01-02T00:00:00Z"},
]
result = await platform.list_issue_comments(10)
ASSERT len(result) == 2
ASSERT result[0].id == 1
ASSERT result[0].body == "first"
ASSERT result[0].user == "alice"
ASSERT result[1].id == 2
```

---

### TS-86-4: get_issue returns IssueResult

**Requirement:** 86-REQ-1.4
**Type:** unit
**Description:** Verify `get_issue` returns a complete `IssueResult`.

**Preconditions:**
- GitHubPlatform with mock returning issue JSON.

**Input:**
- `issue_number = 5`

**Expected:**
- `IssueResult` with number=5, title, html_url, body.

**Assertion pseudocode:**
```
mock GET /repos/owner/repo/issues/5 -> {number: 5, title: "Test", html_url: "...", body: "desc"}
result = await platform.get_issue(5)
ASSERT result.number == 5
ASSERT result.title == "Test"
ASSERT result.body == "desc"
```

---

### TS-86-5: platform protocol includes new methods

**Requirement:** 86-REQ-1.5
**Type:** unit
**Description:** Verify `PlatformProtocol` includes the three new method
signatures and `GitHubPlatform` satisfies the protocol.

**Preconditions:**
- None.

**Input:**
- `GitHubPlatform` instance.

**Expected:**
- `isinstance(platform, PlatformProtocol)` is True.
- `remove_label`, `list_issue_comments`, `get_issue` are callable.

**Assertion pseudocode:**
```
platform = GitHubPlatform(owner, repo, token)
ASSERT isinstance(platform, PlatformProtocol)
ASSERT hasattr(platform, "remove_label")
ASSERT hasattr(platform, "list_issue_comments")
ASSERT hasattr(platform, "get_issue")
```

---

### TS-86-6: discover af:spec issues

**Requirement:** 86-REQ-2.1
**Type:** unit
**Description:** Verify `run_once` polls for both `af:spec` and
`af:spec-pending` issues.

**Preconditions:**
- Mock platform with issues for both labels.

**Input:**
- Platform returns 1 `af:spec` issue and 1 `af:spec-pending` issue.

**Expected:**
- Both lists are retrieved.
- The `af:spec` issue is passed to `process_issue`.

**Assertion pseudocode:**
```
mock list_issues_by_label("af:spec") -> [issue_a]
mock list_issues_by_label("af:spec-pending") -> [issue_b]
await stream.run_once()
ASSERT generator.process_issue.called_with(issue_a)
```

---

### TS-86-7: sequential processing of oldest issue

**Requirement:** 86-REQ-2.2
**Type:** unit
**Description:** Verify only the oldest `af:spec` issue is processed
when multiple exist.

**Preconditions:**
- Mock platform returns two `af:spec` issues.

**Input:**
- Issue #1 (created first) and Issue #5 (created later).

**Expected:**
- Only Issue #1 is passed to `process_issue`.

**Assertion pseudocode:**
```
mock list_issues_by_label("af:spec") -> [issue_1, issue_5]  # sorted by created asc
await stream.run_once()
ASSERT generator.process_issue.called_once_with(issue_1)
```

---

### TS-86-8: pending issue with new human comment triggers re-analysis

**Requirement:** 86-REQ-2.3
**Type:** unit
**Description:** Verify a pending issue with a new human comment after
the last fox comment is transitioned to analyzing.

**Preconditions:**
- Issue labeled `af:spec-pending`.
- Comments: [fox_comment, human_comment] (human after fox).

**Input:**
- Pending issue with new human comment.

**Expected:**
- Label transitions: assign `af:spec-analyzing`, remove `af:spec-pending`.

**Assertion pseudocode:**
```
comments = [fox_comment(t=1), human_comment(t=2)]
mock list_issue_comments -> comments
await stream.run_once()
ASSERT platform.assign_label.called_with(N, "af:spec-analyzing")
ASSERT platform.remove_label.called_with(N, "af:spec-pending")
```

---

### TS-86-9: pending issue without new comment is skipped

**Requirement:** 86-REQ-2.4
**Type:** unit
**Description:** Verify a pending issue with no new human comment after
the last fox comment is skipped.

**Preconditions:**
- Issue labeled `af:spec-pending`.
- Comments: [fox_comment] (no human reply).

**Input:**
- Pending issue without new human comment.

**Expected:**
- `process_issue` is not called. No label changes.

**Assertion pseudocode:**
```
comments = [fox_comment(t=1)]
mock list_issue_comments -> comments
await stream.run_once()
ASSERT generator.process_issue.not_called
```

---

### TS-86-10: label transition assigns new before removing old

**Requirement:** 86-REQ-3.1
**Type:** unit
**Description:** Verify `_transition_label` calls assign_label before
remove_label.

**Preconditions:**
- Mock platform tracking call order.

**Input:**
- `from_label = "af:spec"`, `to_label = "af:spec-analyzing"`

**Expected:**
- `assign_label` called before `remove_label`.

**Assertion pseudocode:**
```
call_order = []
platform.assign_label = Mock(side_effect=lambda *a: call_order.append("assign"))
platform.remove_label = Mock(side_effect=lambda *a: call_order.append("remove"))
await generator._transition_label(42, "af:spec", "af:spec-analyzing")
ASSERT call_order == ["assign", "remove"]
```

---

### TS-86-11: initial label transition to analyzing

**Requirement:** 86-REQ-3.2
**Type:** unit
**Description:** Verify picking up an `af:spec` issue transitions it to
`af:spec-analyzing`.

**Preconditions:**
- Issue labeled `af:spec`.

**Input:**
- An `af:spec` issue passed to `process_issue`.

**Expected:**
- Label transitions to `af:spec-analyzing`.

**Assertion pseudocode:**
```
result = await generator.process_issue(issue)
ASSERT platform.assign_label.called_with(N, "af:spec-analyzing")
ASSERT platform.remove_label.called_with(N, "af:spec")
```

---

### TS-86-12: transition to generating when clear

**Requirement:** 86-REQ-3.3
**Type:** unit
**Description:** Verify a clear analysis transitions to
`af:spec-generating`.

**Preconditions:**
- Mock AI returns `AnalysisResult(clear=True)`.

**Input:**
- Clear issue.

**Expected:**
- Label transitions from `af:spec-analyzing` to `af:spec-generating`.

**Assertion pseudocode:**
```
mock _analyze_issue -> AnalysisResult(clear=True, questions=[], summary="ok")
result = await generator.process_issue(issue)
ASSERT platform.assign_label.called_with(N, "af:spec-generating")
```

---

### TS-86-13: transition to done and close on completion

**Requirement:** 86-REQ-3.4
**Type:** unit
**Description:** Verify successful generation transitions to
`af:spec-done` and closes the issue.

**Preconditions:**
- Mock AI generates spec package. Mock git landing succeeds.

**Input:**
- Clear issue, successful generation and landing.

**Expected:**
- Label `af:spec-done` assigned. Issue closed.

**Assertion pseudocode:**
```
result = await generator.process_issue(issue)
ASSERT result.outcome == SpecGenOutcome.GENERATED
ASSERT platform.assign_label.called_with(N, "af:spec-done")
ASSERT platform.close_issue.called_with(N)
```

---

### TS-86-14: analysis sends full context to AI

**Requirement:** 86-REQ-4.1
**Type:** unit
**Description:** Verify `_analyze_issue` sends issue body, comments,
referenced issues, existing specs, and steering to the AI model.

**Preconditions:**
- Mock AI client. Context with existing specs and steering.

**Input:**
- Issue with body, 2 comments, 1 referenced issue, 3 existing specs.

**Expected:**
- AI call includes all context in the prompt.
- Returns `AnalysisResult`.

**Assertion pseudocode:**
```
result = await generator._analyze_issue(issue, comments, context)
ASSERT ai_client.called_once
prompt = ai_client.call_args.messages[0]["content"]
ASSERT issue.body in prompt
ASSERT "steering" in prompt
ASSERT isinstance(result, AnalysisResult)
```

---

### TS-86-15: ambiguous analysis posts clarification

**Requirement:** 86-REQ-4.2
**Type:** unit
**Description:** Verify an ambiguous analysis posts a clarification
comment and transitions to pending.

**Preconditions:**
- Mock AI returns ambiguous result with questions.

**Input:**
- Issue that AI considers ambiguous.

**Expected:**
- Clarification comment posted. Label transitions to `af:spec-pending`.

**Assertion pseudocode:**
```
mock _analyze_issue -> AnalysisResult(clear=False, questions=["Q1", "Q2"], summary="...")
result = await generator.process_issue(issue)
ASSERT result.outcome == SpecGenOutcome.PENDING
ASSERT platform.add_issue_comment.called
comment = platform.add_issue_comment.call_args[1]
ASSERT "## Agent Fox" in comment
ASSERT "Q1" in comment
```

---

### TS-86-16: reference harvesting parses and fetches

**Requirement:** 86-REQ-4.3
**Type:** unit
**Description:** Verify `_harvest_references` parses `#N` mentions and
fetches referenced issues.

**Preconditions:**
- Mock platform with `get_issue` and `list_issue_comments`.

**Input:**
- Body containing "see #10 and #20".

**Expected:**
- Two `ReferencedIssue` objects returned with bodies and comments.

**Assertion pseudocode:**
```
mock get_issue(10) -> IssueResult(10, ...)
mock get_issue(20) -> IssueResult(20, ...)
mock list_issue_comments(10) -> [comment_a]
mock list_issue_comments(20) -> [comment_b]
refs = await generator._harvest_references("see #10 and #20", [])
ASSERT len(refs) == 2
ASSERT refs[0].number == 10
ASSERT refs[1].number == 20
```

---

### TS-86-17: count clarification rounds

**Requirement:** 86-REQ-5.1
**Type:** unit
**Description:** Verify `_count_clarification_rounds` counts fox
clarification comments.

**Preconditions:**
- None.

**Input:**
- Comments: [fox_clarification, human_reply, fox_clarification, human_reply].

**Expected:**
- Returns 2.

**Assertion pseudocode:**
```
comments = [
    IssueComment(1, "## Agent Fox -- Clarification Needed\n...", "bot", "t1"),
    IssueComment(2, "Here are my answers", "alice", "t2"),
    IssueComment(3, "## Agent Fox -- Clarification Needed\n...", "bot", "t3"),
    IssueComment(4, "More answers", "alice", "t4"),
]
ASSERT generator._count_clarification_rounds(comments) == 2
```

---

### TS-86-18: escalation after max rounds

**Requirement:** 86-REQ-5.2
**Type:** unit
**Description:** Verify escalation when max rounds is reached.

**Preconditions:**
- `max_clarification_rounds = 2`. Two prior clarification rounds.

**Input:**
- Issue with 2 existing clarification rounds. AI still finds gaps.

**Expected:**
- Escalation comment posted. Label transitions to `af:spec-blocked`.

**Assertion pseudocode:**
```
config.max_clarification_rounds = 2
# comments with 2 fox clarification comments
result = await generator.process_issue(issue)
ASSERT result.outcome == SpecGenOutcome.BLOCKED
comment = platform.add_issue_comment.call_args[1]
ASSERT "Specification Blocked" in comment
ASSERT platform.assign_label.called_with(N, "af:spec-blocked")
```

---

### TS-86-19: fox comment detection

**Requirement:** 86-REQ-5.3
**Type:** unit
**Description:** Verify `_is_fox_comment` correctly identifies fox vs
human comments.

**Preconditions:**
- None.

**Input:**
- Comment with body starting with `## Agent Fox`.
- Comment with body starting with "Thanks for the info".

**Expected:**
- First returns True, second returns False.

**Assertion pseudocode:**
```
fox = IssueComment(1, "## Agent Fox -- Clarification\n...", "bot", "t1")
human = IssueComment(2, "Thanks for the info", "alice", "t2")
ASSERT generator._is_fox_comment(fox) == True
ASSERT generator._is_fox_comment(human) == False
```

---

### TS-86-20: generate 5-file spec package

**Requirement:** 86-REQ-6.1
**Type:** integration
**Description:** Verify `_generate_spec_package` produces all 5 files.

**Preconditions:**
- Mock AI client returning valid document content for each call.

**Input:**
- Clear issue with sufficient context.

**Expected:**
- `SpecPackage` with 5 files: `prd.md`, `requirements.md`, `design.md`,
  `test_spec.md`, `tasks.md`.

**Assertion pseudocode:**
```
package = await generator._generate_spec_package(issue, comments, context)
ASSERT set(package.files.keys()) == {"prd.md", "requirements.md", "design.md", "test_spec.md", "tasks.md"}
ASSERT all(len(content) > 0 for content in package.files.values())
```

---

### TS-86-21: prd.md includes source section

**Requirement:** 86-REQ-6.2
**Type:** unit
**Description:** Verify the generated `prd.md` contains a `## Source`
section linking to the issue.

**Preconditions:**
- Issue with `html_url`.

**Input:**
- Issue #42 with URL `https://github.com/owner/repo/issues/42`.

**Expected:**
- `prd.md` content contains `## Source` and the issue URL.

**Assertion pseudocode:**
```
package = await generator._generate_spec_package(issue, comments, context)
prd = package.files["prd.md"]
ASSERT "## Source" in prd
ASSERT "https://github.com/owner/repo/issues/42" in prd
```

---

### TS-86-22: spec numbering increments from existing

**Requirement:** 86-REQ-6.3
**Type:** unit
**Description:** Verify `_find_next_spec_number` returns the next
sequential number.

**Preconditions:**
- `.specs/` contains folders `84_foo/`, `85_bar/`, `86_baz/`.

**Input:**
- Spec directory with max prefix 86.

**Expected:**
- Returns 87.

**Assertion pseudocode:**
```
# Create mock .specs/ with 84_, 85_, 86_ folders
result = generator._find_next_spec_number()
ASSERT result == 87
```

---

### TS-86-23: spec generation uses configured model tier

**Requirement:** 86-REQ-6.4
**Type:** unit
**Description:** Verify AI calls use the model resolved from
`spec_gen_model_tier`.

**Preconditions:**
- Config with `spec_gen_model_tier = "STANDARD"`.

**Input:**
- Issue triggering generation.

**Expected:**
- AI calls use `claude-sonnet-4-6` (STANDARD tier).

**Assertion pseudocode:**
```
config.spec_gen_model_tier = "STANDARD"
await generator._generate_spec_package(issue, comments, context)
ASSERT ai_client.call_args.model == "claude-sonnet-4-6"
```

---

### TS-86-24: duplicate detection with AI

**Requirement:** 86-REQ-7.1
**Type:** unit
**Description:** Verify `_check_duplicates` calls AI with issue and
existing spec info.

**Preconditions:**
- Mock AI client. Existing specs in `.specs/`.

**Input:**
- Issue titled "Add webhook support".
- Existing spec `42_webhook_support`.

**Expected:**
- AI call receives issue info and spec summaries.
- Returns `DuplicateCheckResult(is_duplicate=True, overlapping_spec="42_webhook_support")`.

**Assertion pseudocode:**
```
mock AI -> {"is_duplicate": true, "overlapping_spec": "42_webhook_support", "explanation": "..."}
result = await generator._check_duplicates(issue, existing_specs)
ASSERT result.is_duplicate == True
ASSERT result.overlapping_spec == "42_webhook_support"
```

---

### TS-86-25: duplicate found posts comment and waits

**Requirement:** 86-REQ-7.2
**Type:** unit
**Description:** Verify a duplicate detection posts a comment and
transitions to pending.

**Preconditions:**
- `_check_duplicates` returns `is_duplicate=True`.

**Input:**
- Issue with detected duplicate.

**Expected:**
- Comment posted asking about supersession. Label `af:spec-pending`.

**Assertion pseudocode:**
```
mock _check_duplicates -> DuplicateCheckResult(is_duplicate=True, ...)
result = await generator.process_issue(issue)
ASSERT result.outcome == SpecGenOutcome.PENDING
ASSERT "supersede" in platform.add_issue_comment.call_args[1].lower()
```

---

### TS-86-26: supersede generates with supersedes section

**Requirement:** 86-REQ-7.3
**Type:** unit
**Description:** Verify supersession generates a spec with
`## Supersedes` section.

**Preconditions:**
- Human replied "supersede" to duplicate check comment.

**Input:**
- Issue with duplicate previously detected, human says supersede.

**Expected:**
- Generated `prd.md` contains `## Supersedes` referencing old spec.

**Assertion pseudocode:**
```
# Setup: prior duplicate check, human replied "supersede"
package = await generator._generate_spec_package(issue, comments, context)
ASSERT "## Supersedes" in package.files["prd.md"]
ASSERT "42_webhook_support" in package.files["prd.md"]
```

---

### TS-86-27: landing creates feature branch and commits

**Requirement:** 86-REQ-8.1
**Type:** integration
**Description:** Verify `_land_spec` creates a branch, writes files,
and commits.

**Preconditions:**
- Git repo at repo_root. On `develop` branch.

**Input:**
- `SpecPackage` with spec_name `87_test_spec` and 5 files.

**Expected:**
- Branch `spec/87_test_spec` created.
- Files written to `.specs/87_test_spec/`.
- Commit message matches pattern.

**Assertion pseudocode:**
```
hash = await generator._land_spec(package, issue_number=42)
ASSERT len(hash) > 0
# Verify files exist
ASSERT Path(".specs/87_test_spec/prd.md").exists()
# Verify commit message
log = subprocess.run(["git", "log", "--oneline", "-1"], capture_output=True)
ASSERT "feat(spec): generate 87_test_spec from #42" in log.stdout
```

---

### TS-86-28: direct merge strategy

**Requirement:** 86-REQ-8.2
**Type:** integration
**Description:** Verify direct merge strategy merges and deletes branch.

**Preconditions:**
- Config with `merge_strategy = "direct"`.

**Input:**
- Spec package ready to land.

**Expected:**
- Branch merged into develop. Feature branch deleted.

**Assertion pseudocode:**
```
config.merge_strategy = "direct"
await generator._land_spec(package, 42)
branches = subprocess.run(["git", "branch"], capture_output=True)
ASSERT "spec/87_test_spec" not in branches.stdout
current = subprocess.run(["git", "branch", "--show-current"], capture_output=True)
ASSERT "develop" in current.stdout
```

---

### TS-86-29: PR merge strategy

**Requirement:** 86-REQ-8.3
**Type:** unit
**Description:** Verify PR merge strategy creates a draft PR.

**Preconditions:**
- Config with `merge_strategy = "pr"`. Mock platform.

**Input:**
- Spec package ready to land.

**Expected:**
- `create_pull_request` called with correct args.

**Assertion pseudocode:**
```
config.merge_strategy = "pr"
await generator._land_spec(package, 42)
ASSERT platform.create_pull_request.called_with(
    title="feat(spec): generate 87_test_spec from #42",
    head="spec/87_test_spec",
    base="develop",
    draft=True,
)
```

---

### TS-86-30: completion comment and issue close

**Requirement:** 86-REQ-8.4
**Type:** unit
**Description:** Verify completion comment is posted with correct
content and issue is closed.

**Preconditions:**
- Successful generation and landing.

**Input:**
- Spec `87_test_spec`, commit hash `abc1234`.

**Expected:**
- Comment contains spec folder, file list, commit hash.
- Issue closed.

**Assertion pseudocode:**
```
result = await generator.process_issue(issue)
comment = platform.add_issue_comment.call_args[1]
ASSERT "87_test_spec" in comment
ASSERT "abc1234" in comment
ASSERT "Specification Created" in comment
ASSERT platform.close_issue.called
```

---

### TS-86-31: config default values

**Requirement:** 86-REQ-9.1, 86-REQ-9.2, 86-REQ-9.3
**Type:** unit
**Description:** Verify new config fields have correct defaults.

**Preconditions:**
- Default `NightShiftConfig`.

**Input:**
- No overrides.

**Expected:**
- `max_clarification_rounds = 3`
- `max_budget_usd = 2.0`
- `spec_gen_model_tier = "ADVANCED"`

**Assertion pseudocode:**
```
config = NightShiftConfig()
ASSERT config.max_clarification_rounds == 3
ASSERT config.max_budget_usd == 2.0
ASSERT config.spec_gen_model_tier == "ADVANCED"
```

---

### TS-86-32: cost tracking during generation

**Requirement:** 86-REQ-10.1
**Type:** unit
**Description:** Verify cumulative cost is tracked across AI calls.

**Preconditions:**
- Mock AI client returning usage with cost info.

**Input:**
- Three API calls costing $0.50, $0.30, $0.40.

**Expected:**
- Cumulative cost after calls: $0.50, $0.80, $1.20.

**Assertion pseudocode:**
```
# Mock AI responses with usage data
package = await generator._generate_spec_package(issue, comments, context)
# Internal cost tracker should show $1.20
```

---

### TS-86-33: cost cap aborts generation

**Requirement:** 86-REQ-10.2
**Type:** unit
**Description:** Verify generation aborts when cost exceeds
`max_budget_usd`.

**Preconditions:**
- `max_budget_usd = 1.0`. AI calls cost $0.60 each.

**Input:**
- Generation that would exceed budget on second call.

**Expected:**
- Generation aborts. Budget-exceeded comment posted. Issue blocked.

**Assertion pseudocode:**
```
config.max_budget_usd = 1.0
# Mock AI: first call costs $0.60, second costs $0.60 -> total $1.20 > $1.0
result = await generator.process_issue(issue)
ASSERT result.outcome == SpecGenOutcome.BLOCKED
ASSERT "budget" in platform.add_issue_comment.call_args[1].lower()
```

---

### TS-86-34: cost reported to SharedBudget

**Requirement:** 86-REQ-10.3
**Type:** unit
**Description:** Verify `run_once` reports cost to `SharedBudget`.

**Preconditions:**
- Mock generator returning `SpecGenResult(cost=1.50)`.

**Input:**
- One cycle with cost $1.50.

**Expected:**
- `SharedBudget.add_cost(1.50)` called.

**Assertion pseudocode:**
```
mock process_issue -> SpecGenResult(outcome=GENERATED, cost=1.50, ...)
await stream.run_once()
ASSERT budget.add_cost.called_with(1.50)
```

---

## Edge Case Tests

### TS-86-E1: remove_label API error raises IntegrationError

**Requirement:** 86-REQ-1.E1
**Type:** unit
**Description:** Verify non-404 errors raise IntegrationError.

**Preconditions:**
- Mock returning 500.

**Input:**
- `remove_label(42, "af:spec")`

**Expected:**
- `IntegrationError` raised.

**Assertion pseudocode:**
```
mock DELETE -> 500
ASSERT_RAISES IntegrationError: await platform.remove_label(42, "af:spec")
```

---

### TS-86-E2: list_issue_comments on issue with no comments

**Requirement:** 86-REQ-1.E2
**Type:** unit
**Description:** Verify empty list returned for commentless issue.

**Preconditions:**
- Mock returning empty array.

**Input:**
- `list_issue_comments(42)`

**Expected:**
- Empty list.

**Assertion pseudocode:**
```
mock GET -> []
result = await platform.list_issue_comments(42)
ASSERT result == []
```

---

### TS-86-E3: get_issue with nonexistent issue

**Requirement:** 86-REQ-1.E3
**Type:** unit
**Description:** Verify IntegrationError on 404.

**Preconditions:**
- Mock returning 404.

**Input:**
- `get_issue(99999)`

**Expected:**
- `IntegrationError` raised.

**Assertion pseudocode:**
```
mock GET -> 404
ASSERT_RAISES IntegrationError: await platform.get_issue(99999)
```

---

### TS-86-E4: no af:spec issues is a no-op

**Requirement:** 86-REQ-2.E1
**Type:** unit
**Description:** Verify `run_once` does nothing when no issues found.

**Preconditions:**
- Mock platform returns empty lists for both labels.

**Input:**
- No eligible issues.

**Expected:**
- No calls to `process_issue`. No label changes.

**Assertion pseudocode:**
```
mock list_issues_by_label -> []
await stream.run_once()
ASSERT generator.process_issue.not_called
```

---

### TS-86-E5: stale issue is skipped

**Requirement:** 86-REQ-2.E2
**Type:** unit
**Description:** Verify issues with no activity for 30+ days are skipped.

**Preconditions:**
- Issue with last comment 31 days ago. No recent label changes.

**Input:**
- Stale `af:spec` issue.

**Expected:**
- Issue skipped. Warning logged.

**Assertion pseudocode:**
```
# Issue with last activity > 30 days ago
await stream.run_once()
ASSERT generator.process_issue.not_called
ASSERT "stale" in captured_logs
```

---

### TS-86-E6: crash recovery resets stale analyzing label

**Requirement:** 86-REQ-3.E1
**Type:** unit
**Description:** Verify stale `af:spec-analyzing` is reset to `af:spec`.

**Preconditions:**
- Issue labeled `af:spec-analyzing` from a previous crashed cycle.

**Input:**
- `af:spec-analyzing` issue found during discovery.

**Expected:**
- Label reset to `af:spec`.

**Assertion pseudocode:**
```
mock list_issues_by_label("af:spec-analyzing") -> [issue]
await stream.run_once()
ASSERT platform.assign_label.called_with(N, "af:spec")
ASSERT platform.remove_label.called_with(N, "af:spec-analyzing")
```

---

### TS-86-E7: crash recovery resets stale generating label

**Requirement:** 86-REQ-3.E2
**Type:** unit
**Description:** Verify stale `af:spec-generating` is reset to `af:spec`.

**Preconditions:**
- Issue labeled `af:spec-generating` from a previous crashed cycle.

**Input:**
- `af:spec-generating` issue found during discovery.

**Expected:**
- Label reset to `af:spec`.

**Assertion pseudocode:**
```
mock list_issues_by_label("af:spec-generating") -> [issue]
await stream.run_once()
ASSERT platform.assign_label.called_with(N, "af:spec")
ASSERT platform.remove_label.called_with(N, "af:spec-generating")
```

---

### TS-86-E8: inaccessible referenced issue is skipped

**Requirement:** 86-REQ-4.E1
**Type:** unit
**Description:** Verify inaccessible `#N` reference is skipped with
warning.

**Preconditions:**
- Mock `get_issue(99)` raises IntegrationError.

**Input:**
- Body containing "see #99".

**Expected:**
- Warning logged. Reference skipped. Analysis continues.

**Assertion pseudocode:**
```
mock get_issue(99) -> raises IntegrationError
refs = await generator._harvest_references("see #99", [])
ASSERT len(refs) == 0
ASSERT "warning" in captured_logs or "inaccessible" in captured_logs
```

---

### TS-86-E9: empty issue body treated as ambiguous

**Requirement:** 86-REQ-4.E2
**Type:** unit
**Description:** Verify empty body triggers clarification.

**Preconditions:**
- Issue with empty body.

**Input:**
- `IssueResult(number=1, title="Feature", html_url="...", body="")`

**Expected:**
- Issue treated as ambiguous. Clarification posted.

**Assertion pseudocode:**
```
issue = IssueResult(1, "Feature", "...", body="")
result = await generator.process_issue(issue)
ASSERT result.outcome == SpecGenOutcome.PENDING
```

---

### TS-86-E10: max rounds reached on first analysis

**Requirement:** 86-REQ-5.E1
**Type:** unit
**Description:** Verify escalation works even with
`max_clarification_rounds = 0` edge case (clamped to 1, but if somehow
0 rounds done and analysis says ambiguous, with max=1 and this being
the first round, a clarification is still posted, not an escalation).

**Preconditions:**
- `max_clarification_rounds = 1`. Issue with 1 prior clarification
  round still ambiguous.

**Input:**
- Issue with 1 existing round, still ambiguous.

**Expected:**
- Escalation posted (1 >= max of 1).

**Assertion pseudocode:**
```
config.max_clarification_rounds = 1
# Comments contain 1 fox clarification already
result = await generator.process_issue(issue)
ASSERT result.outcome == SpecGenOutcome.BLOCKED
```

---

### TS-86-E11: API failure during generation aborts

**Requirement:** 86-REQ-6.E1
**Type:** unit
**Description:** Verify API failure aborts generation and blocks issue.

**Preconditions:**
- Mock AI raises exception on second document generation call.

**Input:**
- Issue that passes analysis but AI fails during generation.

**Expected:**
- Generation aborted. Comment posted. Issue blocked.

**Assertion pseudocode:**
```
mock AI -> first call OK, second call raises Exception
result = await generator.process_issue(issue)
ASSERT result.outcome == SpecGenOutcome.BLOCKED
ASSERT platform.assign_label.called_with(N, "af:spec-blocked")
```

---

### TS-86-E12: no existing specs uses prefix 01

**Requirement:** 86-REQ-6.E2
**Type:** unit
**Description:** Verify first spec uses prefix 01.

**Preconditions:**
- Empty `.specs/` directory (no numbered folders).

**Input:**
- Call `_find_next_spec_number()`.

**Expected:**
- Returns 1.

**Assertion pseudocode:**
```
# .specs/ exists but has no NN_ folders
ASSERT generator._find_next_spec_number() == 1
```

---

### TS-86-E13: no specs skips duplicate detection

**Requirement:** 86-REQ-7.E1
**Type:** unit
**Description:** Verify duplicate detection is skipped when no specs
exist.

**Preconditions:**
- Empty existing_specs list.

**Input:**
- `_check_duplicates(issue, existing_specs=[])`

**Expected:**
- Returns `DuplicateCheckResult(is_duplicate=False)` without AI call.

**Assertion pseudocode:**
```
result = await generator._check_duplicates(issue, [])
ASSERT result.is_duplicate == False
ASSERT ai_client.not_called
```

---

### TS-86-E14: branch name collision appends suffix

**Requirement:** 86-REQ-8.E1
**Type:** unit
**Description:** Verify branch name gets suffix on collision.

**Preconditions:**
- Branch `spec/87_test_spec` already exists.

**Input:**
- Landing spec `87_test_spec`.

**Expected:**
- Branch `spec/87_test_spec-2` used instead.

**Assertion pseudocode:**
```
# Create branch spec/87_test_spec first
hash = await generator._land_spec(package, 42)
# Verify the branch used was spec/87_test_spec-2
```

---

### TS-86-E15: merge failure blocks issue

**Requirement:** 86-REQ-8.E2
**Type:** integration
**Description:** Verify merge failure posts branch name and blocks.

**Preconditions:**
- Mock git merge to fail.

**Input:**
- Spec package with merge conflict.

**Expected:**
- Comment with branch name posted. Issue blocked.

**Assertion pseudocode:**
```
mock git merge -> failure
result = await generator.process_issue(issue)
ASSERT result.outcome == SpecGenOutcome.BLOCKED
comment = platform.add_issue_comment.call_args[1]
ASSERT "spec/87_test_spec" in comment
```

---

### TS-86-E16: config clamps max_clarification_rounds

**Requirement:** 86-REQ-9.E1
**Type:** unit
**Description:** Verify values below 1 are clamped to 1.

**Preconditions:**
- None.

**Input:**
- `max_clarification_rounds = 0`

**Expected:**
- Clamped to 1.

**Assertion pseudocode:**
```
config = NightShiftConfig(max_clarification_rounds=0)
ASSERT config.max_clarification_rounds == 1
```

---

### TS-86-E17: invalid model tier falls back to ADVANCED

**Requirement:** 86-REQ-9.E2
**Type:** unit
**Description:** Verify invalid tier defaults to ADVANCED with warning.

**Preconditions:**
- None.

**Input:**
- `spec_gen_model_tier = "NONEXISTENT"`

**Expected:**
- Model resolves to `claude-opus-4-6`. Warning logged.

**Assertion pseudocode:**
```
config = NightShiftConfig(spec_gen_model_tier="NONEXISTENT")
generator = SpecGenerator(platform, config, repo_root)
# When resolving model, should fall back to ADVANCED
ASSERT resolved_model == "claude-opus-4-6"
ASSERT "warning" in captured_logs
```

---

### TS-86-E18: unlimited budget when max_budget_usd is 0

**Requirement:** 86-REQ-10.E1
**Type:** unit
**Description:** Verify no budget enforcement when cap is 0.

**Preconditions:**
- `max_budget_usd = 0`.

**Input:**
- Generation costing $5.00.

**Expected:**
- Generation completes. No budget abort.

**Assertion pseudocode:**
```
config.max_budget_usd = 0
# Mock AI calls with high cost
result = await generator.process_issue(issue)
ASSERT result.outcome == SpecGenOutcome.GENERATED
```

---

## Property Test Cases

### TS-86-P1: Label transition always assigns before removing

**Property:** Property 1 from design.md
**Validates:** 86-REQ-3.1, 86-REQ-3.2
**Type:** property
**Description:** For any label transition, assign_label is called before
remove_label.

**For any:** pair of (from_label, to_label) drawn from the set of
`af:spec-*` labels
**Invariant:** In the call sequence, the index of the assign_label call
is strictly less than the index of the remove_label call.

**Assertion pseudocode:**
```
FOR ANY (from_label, to_label) IN label_pairs:
    call_order = []
    await generator._transition_label(42, from_label, to_label)
    ASSERT call_order.index("assign") < call_order.index("remove")
```

---

### TS-86-P2: Clarification round count is bounded

**Property:** Property 2 from design.md
**Validates:** 86-REQ-5.1, 86-REQ-5.2
**Type:** property
**Description:** Round count is always between 0 and the number of fox
clarification comments.

**For any:** list of IssueComment objects (generated via Hypothesis)
**Invariant:** `0 <= _count_clarification_rounds(comments) <= count_of_fox_clarification_comments`

**Assertion pseudocode:**
```
FOR ANY comments IN lists(issue_comments):
    rounds = generator._count_clarification_rounds(comments)
    fox_count = sum(1 for c in comments if is_fox_clarification(c))
    ASSERT 0 <= rounds <= fox_count
```

---

### TS-86-P3: Fox comment detection is consistent with prefix

**Property:** Property 3 from design.md
**Validates:** 86-REQ-5.3, 86-REQ-2.3
**Type:** property
**Description:** `_is_fox_comment` returns True iff body starts with
`## Agent Fox`.

**For any:** string body (generated via Hypothesis text strategy)
**Invariant:** `_is_fox_comment(comment) == body.strip().startswith("## Agent Fox")`

**Assertion pseudocode:**
```
FOR ANY body IN text():
    comment = IssueComment(1, body, "bot", "t1")
    ASSERT generator._is_fox_comment(comment) == body.strip().startswith("## Agent Fox")
```

---

### TS-86-P4: Spec number exceeds all existing prefixes

**Property:** Property 4 from design.md
**Validates:** 86-REQ-6.3, 86-REQ-6.E2
**Type:** property
**Description:** Next spec number is always greater than all existing.

**For any:** set of existing spec prefix integers (generated via
Hypothesis sets of integers 1-99)
**Invariant:** `_find_next_spec_number() > max(existing_prefixes)`
(or returns 1 if empty)

**Assertion pseudocode:**
```
FOR ANY prefixes IN sets(integers(1, 99)):
    # Create .specs/ folders with these prefixes
    result = generator._find_next_spec_number()
    IF prefixes is empty:
        ASSERT result == 1
    ELSE:
        ASSERT result > max(prefixes)
```

---

### TS-86-P5: Remove label idempotency

**Property:** Property 5 from design.md
**Validates:** 86-REQ-1.1, 86-REQ-1.2
**Type:** property
**Description:** `remove_label` succeeds regardless of whether the label
is present.

**For any:** (issue_number, label) pair where label may or may not exist
**Invariant:** No exception is raised (404 is handled silently).

**Assertion pseudocode:**
```
FOR ANY label IN label_strings:
    # Mock: 50% chance 204 (present), 50% chance 404 (absent)
    await platform.remove_label(42, label)
    # No exception = property holds
```

---

### TS-86-P6: Cost is monotonically non-decreasing

**Property:** Property 6 from design.md
**Validates:** 86-REQ-10.1, 86-REQ-10.2
**Type:** property
**Description:** Cumulative cost never decreases across API calls.

**For any:** sequence of non-negative cost values
**Invariant:** Each intermediate cumulative total >= previous total, AND
if max_budget_usd > 0, generation stops once total > limit.

**Assertion pseudocode:**
```
FOR ANY costs IN lists(floats(0, 10)):
    tracker = CostTracker(max_budget=2.0)
    prev = 0.0
    for cost in costs:
        tracker.add(cost)
        ASSERT tracker.total >= prev
        prev = tracker.total
        IF tracker.exceeded:
            ASSERT tracker.total >= 2.0
            break
```

---

### TS-86-P7: Spec name derivation produces valid folder names

**Property:** Property 7 from design.md
**Validates:** 86-REQ-6.3
**Type:** property
**Description:** Output always matches `\d{2}_[a-z0-9_]+` pattern.

**For any:** (title: text, prefix: integer 1-99)
**Invariant:** Result matches the spec folder pattern.

**Assertion pseudocode:**
```
FOR ANY title IN text(), prefix IN integers(1, 99):
    name = generator._spec_name_from_title(title, prefix)
    ASSERT re.match(r"^\d{2}_[a-z0-9_]+$", name)
```

---

## Integration Smoke Tests

### TS-86-SMOKE-1: Happy path — clear issue generates and lands spec

**Execution Path:** Path 1 from design.md
**Description:** End-to-end test: clear issue produces spec files
committed to develop.

**Setup:** Mock platform (all issue/label/comment operations). Mock AI
client (returns clear analysis + document contents). Real git repo in
temp directory.

**Trigger:** `await stream.run_once()`

**Expected side effects:**
- 5 spec files exist in `.specs/NN_<name>/`
- Git log shows commit `feat(spec): generate ...`
- Platform `close_issue` called
- Platform `assign_label("af:spec-done")` called
- `SharedBudget.add_cost` called with positive value

**Must NOT satisfy with:** Mocking `SpecGenerator.process_issue` (the
full pipeline must run). Mocking `_land_spec` (git operations must
execute).

**Assertion pseudocode:**
```
platform = MockPlatform()
platform.list_issues_by_label.return_value = [issue]
ai_client = MockAIClient(clear=True, documents={...})
stream = SpecGeneratorStream(config, platform, repo_root)
await stream.run_once()
ASSERT Path(repo_root / ".specs" / spec_name / "prd.md").exists()
ASSERT platform.close_issue.called
ASSERT budget.add_cost.called
```

---

### TS-86-SMOKE-2: Ambiguous issue posts clarification

**Execution Path:** Path 2 from design.md
**Description:** End-to-end: ambiguous issue gets clarification comment,
label transitions to pending.

**Setup:** Mock platform. Mock AI client (returns ambiguous analysis
with questions). No git operations expected.

**Trigger:** `await stream.run_once()`

**Expected side effects:**
- Clarification comment posted with `## Agent Fox` prefix
- Label `af:spec-pending` assigned
- Label `af:spec-analyzing` removed
- No spec files created
- No git commits

**Must NOT satisfy with:** Mocking `_analyze_issue` to skip AI call.

**Assertion pseudocode:**
```
platform = MockPlatform()
ai_client = MockAIClient(clear=False, questions=["Q1"])
await stream.run_once()
ASSERT platform.add_issue_comment.called
ASSERT "## Agent Fox" in platform.add_issue_comment.call_args[1]
ASSERT platform.assign_label.called_with(N, "af:spec-pending")
ASSERT NOT Path(repo_root / ".specs").glob("*/prd.md")  # no new specs
```

---

### TS-86-SMOKE-3: Pending issue with response triggers re-analysis

**Execution Path:** Path 3 from design.md
**Description:** End-to-end: pending issue with new human comment gets
re-analyzed and (in this test) generates spec.

**Setup:** Mock platform with pending issue. Comments show fox question
then human reply. Mock AI returns clear on re-analysis.

**Trigger:** `await stream.run_once()`

**Expected side effects:**
- Label transitions: pending → analyzing → generating → done
- Spec files created
- Issue closed

**Must NOT satisfy with:** Mocking `_has_new_human_comment` — must
parse real comment list.

**Assertion pseudocode:**
```
platform = MockPlatform()
platform.list_issues_by_label("af:spec-pending") -> [issue]
platform.list_issue_comments -> [fox_comment, human_reply]
ai_client = MockAIClient(clear=True, ...)
await stream.run_once()
ASSERT platform.close_issue.called
```

---

### TS-86-SMOKE-4: Max rounds triggers escalation

**Execution Path:** Path 4 from design.md
**Description:** End-to-end: issue hits max rounds and gets escalated.

**Setup:** Mock platform. Comments contain `max_clarification_rounds`
fox clarification comments + human replies. AI still returns ambiguous.

**Trigger:** `await stream.run_once()` (processing the re-analyzed
issue)

**Expected side effects:**
- Escalation comment posted with `## Agent Fox -- Specification Blocked`
- Label `af:spec-blocked` assigned
- Issue NOT closed

**Must NOT satisfy with:** Mocking `_count_clarification_rounds`.

**Assertion pseudocode:**
```
config.max_clarification_rounds = 2
# Comments: [fox_q1, human_a1, fox_q2, human_a2]
ai_client = MockAIClient(clear=False, questions=["still unclear"])
await stream.run_once()
ASSERT "Specification Blocked" in platform.add_issue_comment.call_args[1]
ASSERT platform.assign_label.called_with(N, "af:spec-blocked")
ASSERT NOT platform.close_issue.called
```

---

### TS-86-SMOKE-5: Cost cap exceeded aborts generation

**Execution Path:** Path 5 from design.md
**Description:** End-to-end: generation aborted when per-spec cost
exceeds budget.

**Setup:** Mock platform. Mock AI client that returns expensive
responses (cost > max_budget_usd). `max_budget_usd = 0.50`.

**Trigger:** `await stream.run_once()`

**Expected side effects:**
- Budget-exceeded comment posted
- Label `af:spec-blocked` assigned
- No spec files committed
- Cost still reported to SharedBudget

**Must NOT satisfy with:** Mocking cost tracking internals.

**Assertion pseudocode:**
```
config.max_budget_usd = 0.50
ai_client = MockAIClient(cost_per_call=0.30)  # exceeds after 2 calls
await stream.run_once()
ASSERT "budget" in platform.add_issue_comment.call_args[1].lower()
ASSERT platform.assign_label.called_with(N, "af:spec-blocked")
ASSERT budget.add_cost.called  # cost still reported
```

---

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 86-REQ-1.1 | TS-86-1 | unit |
| 86-REQ-1.2 | TS-86-2 | unit |
| 86-REQ-1.3 | TS-86-3 | unit |
| 86-REQ-1.4 | TS-86-4 | unit |
| 86-REQ-1.5 | TS-86-5 | unit |
| 86-REQ-1.E1 | TS-86-E1 | unit |
| 86-REQ-1.E2 | TS-86-E2 | unit |
| 86-REQ-1.E3 | TS-86-E3 | unit |
| 86-REQ-2.1 | TS-86-6 | unit |
| 86-REQ-2.2 | TS-86-7 | unit |
| 86-REQ-2.3 | TS-86-8 | unit |
| 86-REQ-2.4 | TS-86-9 | unit |
| 86-REQ-2.E1 | TS-86-E4 | unit |
| 86-REQ-2.E2 | TS-86-E5 | unit |
| 86-REQ-3.1 | TS-86-10 | unit |
| 86-REQ-3.2 | TS-86-11 | unit |
| 86-REQ-3.3 | TS-86-12 | unit |
| 86-REQ-3.4 | TS-86-13 | unit |
| 86-REQ-3.E1 | TS-86-E6 | unit |
| 86-REQ-3.E2 | TS-86-E7 | unit |
| 86-REQ-4.1 | TS-86-14 | unit |
| 86-REQ-4.2 | TS-86-15 | unit |
| 86-REQ-4.3 | TS-86-16 | unit |
| 86-REQ-4.E1 | TS-86-E8 | unit |
| 86-REQ-4.E2 | TS-86-E9 | unit |
| 86-REQ-5.1 | TS-86-17 | unit |
| 86-REQ-5.2 | TS-86-18 | unit |
| 86-REQ-5.3 | TS-86-19 | unit |
| 86-REQ-5.E1 | TS-86-E10 | unit |
| 86-REQ-6.1 | TS-86-20 | integration |
| 86-REQ-6.2 | TS-86-21 | unit |
| 86-REQ-6.3 | TS-86-22 | unit |
| 86-REQ-6.4 | TS-86-23 | unit |
| 86-REQ-6.E1 | TS-86-E11 | unit |
| 86-REQ-6.E2 | TS-86-E12 | unit |
| 86-REQ-7.1 | TS-86-24 | unit |
| 86-REQ-7.2 | TS-86-25 | unit |
| 86-REQ-7.3 | TS-86-26 | unit |
| 86-REQ-7.E1 | TS-86-E13 | unit |
| 86-REQ-8.1 | TS-86-27 | integration |
| 86-REQ-8.2 | TS-86-28 | integration |
| 86-REQ-8.3 | TS-86-29 | unit |
| 86-REQ-8.4 | TS-86-30 | unit |
| 86-REQ-8.E1 | TS-86-E14 | unit |
| 86-REQ-8.E2 | TS-86-E15 | integration |
| 86-REQ-9.1 | TS-86-31 | unit |
| 86-REQ-9.2 | TS-86-31 | unit |
| 86-REQ-9.3 | TS-86-31 | unit |
| 86-REQ-9.E1 | TS-86-E16 | unit |
| 86-REQ-9.E2 | TS-86-E17 | unit |
| 86-REQ-10.1 | TS-86-32 | unit |
| 86-REQ-10.2 | TS-86-33 | unit |
| 86-REQ-10.3 | TS-86-34 | unit |
| 86-REQ-10.E1 | TS-86-E18 | unit |
| Property 1 | TS-86-P1 | property |
| Property 2 | TS-86-P2 | property |
| Property 3 | TS-86-P3 | property |
| Property 4 | TS-86-P4 | property |
| Property 5 | TS-86-P5 | property |
| Property 6 | TS-86-P6 | property |
| Property 7 | TS-86-P7 | property |
