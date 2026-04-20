# Test Specification: GitHub Issue REST API Migration

## Overview

Tests validate that `GitHubPlatform` issue methods correctly call the GitHub
REST API and that `file_or_update_issue()` preserves search-before-create
idempotency using the platform instead of the `gh` CLI. All tests mock
`httpx.AsyncClient` — no real GitHub API calls.

## Test Cases

### TS-28-1: search_issues Returns Matching Issues

**Requirement:** 28-REQ-1.1, 28-REQ-1.2
**Type:** unit
**Description:** Verify `search_issues()` calls the correct API endpoint and
returns parsed results.

**Preconditions:**
- `GitHubPlatform` initialized with owner="org", repo="repo", token="tok".

**Input:**
- `title_prefix="[Skeptic Review] my_spec"`, `state="open"`

**Expected:**
- HTTP GET to `/search/issues` with query containing
  `repo:org/repo in:title [Skeptic Review] my_spec state:open type:issue`
- Returns list of `IssueResult` with number, title, html_url from response.

**Assertion pseudocode:**
```
mock_response = {status: 200, json: {items: [{number: 42, title: "...", html_url: "..."}]}}
platform = GitHubPlatform("org", "repo", "tok")
results = await platform.search_issues("[Skeptic Review] my_spec")
ASSERT len(results) == 1
ASSERT results[0].number == 42
ASSERT request.url contains "/search/issues"
ASSERT request.params.q contains "repo:org/repo"
```

---

### TS-28-2: search_issues Empty Results

**Requirement:** 28-REQ-1.E2
**Type:** unit
**Description:** Verify `search_issues()` returns empty list when no matches.

**Preconditions:**
- API returns `{items: []}`.

**Input:**
- `title_prefix="nonexistent"`

**Expected:**
- Returns empty list.

**Assertion pseudocode:**
```
mock_response = {status: 200, json: {items: []}}
results = await platform.search_issues("nonexistent")
ASSERT results == []
```

---

### TS-28-3: create_issue Success

**Requirement:** 28-REQ-2.1, 28-REQ-2.2
**Type:** unit
**Description:** Verify `create_issue()` POSTs to the correct endpoint and
returns the created issue data.

**Preconditions:**
- API returns status 201 with issue data.

**Input:**
- `title="[Skeptic Review] spec"`, `body="findings..."`

**Expected:**
- HTTP POST to `/repos/org/repo/issues` with `{title, body}` payload.
- Returns `IssueResult(number=1, title="...", html_url="...")`.

**Assertion pseudocode:**
```
mock_response = {status: 201, json: {number: 1, title: "...", html_url: "..."}}
result = await platform.create_issue("[Skeptic Review] spec", "findings...")
ASSERT result.number == 1
ASSERT request.method == "POST"
ASSERT request.url ends with "/repos/org/repo/issues"
```

---

### TS-28-4: update_issue Success

**Requirement:** 28-REQ-3.1
**Type:** unit
**Description:** Verify `update_issue()` PATCHes the correct endpoint.

**Preconditions:**
- API returns status 200.

**Input:**
- `issue_number=42`, `body="updated findings"`

**Expected:**
- HTTP PATCH to `/repos/org/repo/issues/42` with `{body}` payload.

**Assertion pseudocode:**
```
mock_response = {status: 200}
await platform.update_issue(42, "updated findings")
ASSERT request.method == "PATCH"
ASSERT request.url ends with "/repos/org/repo/issues/42"
ASSERT request.json.body == "updated findings"
```

---

### TS-28-5: add_issue_comment Success

**Requirement:** 28-REQ-3.2
**Type:** unit
**Description:** Verify `add_issue_comment()` POSTs to the comments endpoint.

**Preconditions:**
- API returns status 201.

**Input:**
- `issue_number=42`, `comment="Updated on re-run."`

**Expected:**
- HTTP POST to `/repos/org/repo/issues/42/comments` with `{body}` payload.

**Assertion pseudocode:**
```
mock_response = {status: 201}
await platform.add_issue_comment(42, "Updated on re-run.")
ASSERT request.method == "POST"
ASSERT request.url ends with "/repos/org/repo/issues/42/comments"
```

---

### TS-28-6: close_issue Success

**Requirement:** 28-REQ-4.1
**Type:** unit
**Description:** Verify `close_issue()` PATCHes the issue state to closed
and optionally adds a comment.

**Preconditions:**
- API returns status 200 for PATCH, 201 for comment.

**Input:**
- `issue_number=42`, `comment="Closing: no findings on re-run."`

**Expected:**
- HTTP POST to comments endpoint (if comment provided).
- HTTP PATCH to `/repos/org/repo/issues/42` with `{state: "closed"}`.

**Assertion pseudocode:**
```
mock_responses = [{status: 201}, {status: 200}]  # comment, then close
await platform.close_issue(42, comment="Closing: no findings on re-run.")
ASSERT patch_request.json.state == "closed"
```

---

### TS-28-7: file_or_update_issue Creates New Issue

**Requirement:** 28-REQ-5.2, 28-REQ-5.3
**Type:** unit
**Description:** Verify `file_or_update_issue()` creates a new issue when
search returns no matches.

**Preconditions:**
- Platform mock: `search_issues` returns `[]`, `create_issue` returns
  `IssueResult(1, "title", "url")`.

**Input:**
- `title_prefix="[Skeptic] spec"`, `body="findings"`, `platform=mock`

**Expected:**
- `search_issues` called once.
- `create_issue` called once.
- Returns issue URL.

**Assertion pseudocode:**
```
mock_platform.search_issues.return_value = []
mock_platform.create_issue.return_value = IssueResult(1, "t", "http://url")
result = await file_or_update_issue("[Skeptic] spec", "findings", platform=mock_platform)
ASSERT result == "http://url"
ASSERT mock_platform.create_issue.call_count == 1
```

---

### TS-28-8: file_or_update_issue Updates Existing Issue

**Requirement:** 28-REQ-5.2, 28-REQ-5.3
**Type:** unit
**Description:** Verify `file_or_update_issue()` updates an existing issue
when search finds a match.

**Preconditions:**
- Platform mock: `search_issues` returns `[IssueResult(42, "title", "url")]`.

**Input:**
- `title_prefix="[Skeptic] spec"`, `body="updated"`, `platform=mock`

**Expected:**
- `update_issue(42, "updated")` called.
- `add_issue_comment(42, ...)` called.
- `create_issue` NOT called.
- Returns issue URL.

**Assertion pseudocode:**
```
mock_platform.search_issues.return_value = [IssueResult(42, "t", "http://url")]
result = await file_or_update_issue("[Skeptic] spec", "updated", platform=mock_platform)
ASSERT mock_platform.update_issue.call_count == 1
ASSERT mock_platform.add_issue_comment.call_count == 1
ASSERT mock_platform.create_issue.call_count == 0
```

---

### TS-28-9: file_or_update_issue Closes When Empty

**Requirement:** 28-REQ-5.3
**Type:** unit
**Description:** Verify close-if-empty behavior.

**Preconditions:**
- Platform mock: `search_issues` returns a match.

**Input:**
- `title_prefix="[Skeptic] spec"`, `body=""`, `close_if_empty=True`,
  `platform=mock`

**Expected:**
- `close_issue(42, comment=...)` called.
- Returns None.

**Assertion pseudocode:**
```
mock_platform.search_issues.return_value = [IssueResult(42, "t", "http://url")]
result = await file_or_update_issue("[Skeptic] spec", "", platform=mock, close_if_empty=True)
ASSERT mock_platform.close_issue.call_count == 1
ASSERT result is None
```

---

### TS-28-10: No gh CLI References in Module

**Requirement:** 28-REQ-5.4
**Type:** unit
**Description:** Verify `github_issues.py` contains no `gh` CLI references.

**Preconditions:**
- File exists at `agent_fox/session/github_issues.py`.

**Input:**
- Source code of the module.

**Expected:**
- No `create_subprocess_exec`, no `"gh"` string literal, no `_run_gh_command`.

**Assertion pseudocode:**
```
content = read_file("agent_fox/session/github_issues.py")
ASSERT "create_subprocess_exec" not in content
ASSERT "_run_gh_command" not in content
```

---

### TS-28-11: Auth Headers Match create_pr

**Requirement:** 28-REQ-1.1 (via Property 4)
**Type:** unit
**Description:** Verify issue methods use the same auth headers as `create_pr`.

**Preconditions:**
- Platform initialized with token="test-token".

**Input:**
- Any issue method call.

**Expected:**
- Request headers include `Authorization: Bearer test-token`,
  `Accept: application/vnd.github+json`,
  `X-GitHub-Api-Version: 2022-11-28`.

**Assertion pseudocode:**
```
await platform.search_issues("prefix")
ASSERT request.headers["Authorization"] == "Bearer test-token"
ASSERT request.headers["Accept"] == "application/vnd.github+json"
ASSERT request.headers["X-GitHub-Api-Version"] == "2022-11-28"
```

---

### TS-28-12: Errata Document Exists

**Requirement:** 28-REQ-6.1
**Type:** unit
**Description:** Verify errata document is created.

**Preconditions:**
- Implementation complete.

**Input:**
- File path `docs/errata/28_github_issue_rest_api.md`.

**Expected:**
- File exists and references 26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3,
  26-REQ-10.E1.

**Assertion pseudocode:**
```
content = read_file("docs/errata/28_github_issue_rest_api.md")
ASSERT "26-REQ-10.1" in content
ASSERT "REST API" in content
```

## Edge Case Tests

### TS-28-E1: search_issues API Error

**Requirement:** 28-REQ-1.E1
**Type:** unit
**Description:** Verify `search_issues()` raises `IntegrationError` on API error.

**Preconditions:**
- API returns status 403.

**Input:**
- `title_prefix="prefix"`

**Expected:**
- `IntegrationError` raised with status code.

**Assertion pseudocode:**
```
mock_response = {status: 403, text: "forbidden"}
ASSERT_RAISES IntegrationError: await platform.search_issues("prefix")
```

---

### TS-28-E2: create_issue API Error

**Requirement:** 28-REQ-2.E1
**Type:** unit
**Description:** Verify `create_issue()` raises `IntegrationError` on API error.

**Preconditions:**
- API returns status 422.

**Input:**
- `title="title"`, `body="body"`

**Expected:**
- `IntegrationError` raised.

**Assertion pseudocode:**
```
mock_response = {status: 422, text: "validation failed"}
ASSERT_RAISES IntegrationError: await platform.create_issue("title", "body")
```

---

### TS-28-E3: update_issue API Error

**Requirement:** 28-REQ-3.E1
**Type:** unit
**Description:** Verify `update_issue()` raises `IntegrationError` on API error.

**Preconditions:**
- API returns status 404.

**Input:**
- `issue_number=999`, `body="body"`

**Expected:**
- `IntegrationError` raised.

**Assertion pseudocode:**
```
mock_response = {status: 404, text: "not found"}
ASSERT_RAISES IntegrationError: await platform.update_issue(999, "body")
```

---

### TS-28-E4: file_or_update_issue Platform None

**Requirement:** 28-REQ-5.E1
**Type:** unit
**Description:** Verify `file_or_update_issue()` returns None when platform
is None.

**Preconditions:**
- None.

**Input:**
- `platform=None`

**Expected:**
- Returns None.
- Warning logged.

**Assertion pseudocode:**
```
result = await file_or_update_issue("[Skeptic] spec", "body", platform=None)
ASSERT result is None
ASSERT "warning" in captured_logs
```

---

### TS-28-E5: file_or_update_issue API Error Swallowed

**Requirement:** 28-REQ-5.E2
**Type:** unit
**Description:** Verify `file_or_update_issue()` catches `IntegrationError`
and returns None.

**Preconditions:**
- Platform mock: `search_issues` raises `IntegrationError`.

**Input:**
- `platform=mock` (search raises)

**Expected:**
- Returns None.
- Warning logged.
- No exception propagated.

**Assertion pseudocode:**
```
mock_platform.search_issues.side_effect = IntegrationError("fail")
result = await file_or_update_issue("[Skeptic] spec", "body", platform=mock_platform)
ASSERT result is None
```

## Property Test Cases

### TS-28-P1: Search-Before-Create Idempotency

**Property:** Property 2 from design.md
**Validates:** 28-REQ-5.3
**Type:** property
**Description:** Repeated calls produce at most one create and N-1 updates.

**For any:** N in [1..10] calls to `file_or_update_issue()` with the same
title prefix and a stateful mock platform.

**Invariant:** `create_issue` is called at most once. For N > 1, subsequent
calls use `update_issue`.

**Assertion pseudocode:**
```
FOR ANY n IN integers(1, 10):
    create_count = 0
    update_count = 0
    mock_platform = StatefulMockPlatform()
    FOR i IN range(n):
        await file_or_update_issue("prefix", f"body {i}", platform=mock_platform)
    ASSERT create_count <= 1
    ASSERT update_count == max(0, n - 1)
```

---

### TS-28-P2: Graceful Degradation

**Property:** Property 3 from design.md
**Validates:** 28-REQ-5.E1, 28-REQ-5.E2
**Type:** property
**Description:** Function never raises regardless of platform state.

**For any:** platform in [None, mock-that-raises-on-search,
mock-that-raises-on-create, mock-that-raises-on-update].

**Invariant:** `file_or_update_issue()` returns None without raising.

**Assertion pseudocode:**
```
FOR ANY error_point IN [None, "search", "create", "update"]:
    mock = build_failing_mock(error_point)
    result = await file_or_update_issue("prefix", "body", platform=mock)
    ASSERT result is None OR isinstance(result, str)
    # No exception raised
```

### TS-28-P3: No gh CLI References

**Property:** Property 1 from design.md
**Validates:** 28-REQ-5.4
**Type:** property
**Description:** The module contains no subprocess or gh CLI references.

**For any:** source code of `agent_fox/session/github_issues.py`.

**Invariant:** The file SHALL NOT contain `create_subprocess_exec`,
`_run_gh_command`, or the string `"gh"` as a CLI invocation.

**Assertion pseudocode:**
```
content = read_file("agent_fox/session/github_issues.py")
ASSERT "create_subprocess_exec" not in content
ASSERT "_run_gh_command" not in content
```

---

### TS-28-P4: API Authentication Consistency

**Property:** Property 4 from design.md
**Validates:** 28-REQ-1.1, 28-REQ-2.1, 28-REQ-3.1, 28-REQ-4.1
**Type:** property
**Description:** All issue methods use the same auth headers as `create_pr`.

**For any:** method in [search_issues, create_issue, update_issue,
add_issue_comment, close_issue].

**Invariant:** The request includes `Authorization: Bearer {token}`,
`Accept: application/vnd.github+json`, and
`X-GitHub-Api-Version: 2022-11-28`.

**Assertion pseudocode:**
```
FOR ANY method IN [search_issues, create_issue, update_issue, add_issue_comment, close_issue]:
    await method(...)
    ASSERT request.headers["Authorization"] == f"Bearer {token}"
    ASSERT request.headers["Accept"] == "application/vnd.github+json"
    ASSERT request.headers["X-GitHub-Api-Version"] == "2022-11-28"
```

---

### TS-28-P5: Search Query Correctness

**Property:** Property 5 from design.md
**Validates:** 28-REQ-1.2
**Type:** property
**Description:** Search query always contains the required components.

**For any:** title_prefix as a non-empty string, state in ["open", "closed"].

**Invariant:** The query parameter includes `repo:{owner}/{repo}`, `in:title`,
the title prefix, the state, and `type:issue`.

**Assertion pseudocode:**
```
FOR ANY title_prefix IN text(min_size=1, max_size=50):
    FOR ANY state IN ["open", "closed"]:
        await platform.search_issues(title_prefix, state)
        ASSERT f"repo:{owner}/{repo}" in request.params.q
        ASSERT "in:title" in request.params.q
        ASSERT title_prefix in request.params.q
        ASSERT f"state:{state}" in request.params.q
        ASSERT "type:issue" in request.params.q
```

---

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 28-REQ-1.1 | TS-28-1, TS-28-11 | unit |
| 28-REQ-1.2 | TS-28-1 | unit |
| 28-REQ-1.3 | TS-28-1 | unit |
| 28-REQ-1.E1 | TS-28-E1 | unit |
| 28-REQ-1.E2 | TS-28-2 | unit |
| 28-REQ-2.1 | TS-28-3 | unit |
| 28-REQ-2.2 | TS-28-3 | unit |
| 28-REQ-2.E1 | TS-28-E2 | unit |
| 28-REQ-3.1 | TS-28-4 | unit |
| 28-REQ-3.2 | TS-28-5 | unit |
| 28-REQ-3.E1 | TS-28-E3 | unit |
| 28-REQ-4.1 | TS-28-6 | unit |
| 28-REQ-4.E1 | TS-28-E3 | unit |
| 28-REQ-5.1 | TS-28-7, TS-28-E4 | unit |
| 28-REQ-5.2 | TS-28-7, TS-28-8 | unit |
| 28-REQ-5.3 | TS-28-7, TS-28-8, TS-28-9, TS-28-P1 | unit, property |
| 28-REQ-5.4 | TS-28-10 | unit |
| 28-REQ-5.E1 | TS-28-E4 | unit |
| 28-REQ-5.E2 | TS-28-E5, TS-28-P2 | unit, property |
| 28-REQ-6.1 | TS-28-12 | unit |
| Property 1 | TS-28-P3 | property |
| Property 2 | TS-28-P1 | property |
| Property 3 | TS-28-P2 | property |
| Property 4 | TS-28-P4 | property |
| Property 5 | TS-28-P5 | property |
