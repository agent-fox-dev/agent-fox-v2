# Test Specification: Platform Issue Abstraction

## Overview

Tests verify: (1) the Platform protocol is structurally satisfied by both
GitHubPlatform and GitLabPlatform, (2) GitLabPlatform correctly calls the
GitLab REST API, (3) the factory creates the right platform for each config
type, (4) `file_or_update_issue()` preserves search-before-create behavior
using the abstract protocol, and (5) `handle_auditor_issue()` works with the
abstract protocol.

All external API calls are mocked. No real HTTP requests are made.

## Test Cases

### TS-48-1: Platform Protocol Exports

**Requirement:** 48-REQ-1.1
**Type:** unit
**Description:** Verify the `Platform` protocol is importable and defines
all five methods plus the `name` property.

**Preconditions:**
- None.

**Input:**
- Import `Platform` from `agent_fox.platform`.

**Expected:**
- `Platform` is a class.
- It has attributes: `search_issues`, `create_issue`, `update_issue`,
  `add_issue_comment`, `close_issue`, `name`.

**Assertion pseudocode:**
```
from agent_fox.platform import Platform
ASSERT hasattr(Platform, "search_issues")
ASSERT hasattr(Platform, "create_issue")
ASSERT hasattr(Platform, "update_issue")
ASSERT hasattr(Platform, "add_issue_comment")
ASSERT hasattr(Platform, "close_issue")
ASSERT hasattr(Platform, "name")
```

### TS-48-2: GitHubPlatform Satisfies Protocol

**Requirement:** 48-REQ-2.1, 48-REQ-2.2
**Type:** unit
**Description:** Verify GitHubPlatform is a structural subtype of Platform.

**Preconditions:**
- None.

**Input:**
- Instantiate `GitHubPlatform` with dummy args.

**Expected:**
- `isinstance(gh, Platform)` is True.
- `gh.name == "github"`.

**Assertion pseudocode:**
```
gh = GitHubPlatform(owner="o", repo="r", token="t")
ASSERT isinstance(gh, Platform)
ASSERT gh.name == "github"
```

### TS-48-3: GitLabPlatform Satisfies Protocol

**Requirement:** 48-REQ-3.1, 48-REQ-3.5
**Type:** unit
**Description:** Verify GitLabPlatform satisfies the Platform protocol.

**Preconditions:**
- None.

**Input:**
- Instantiate `GitLabPlatform` with dummy args.

**Expected:**
- `isinstance(gl, Platform)` is True.
- `gl.name == "gitlab"`.

**Assertion pseudocode:**
```
gl = GitLabPlatform(project_id="123", token="t")
ASSERT isinstance(gl, Platform)
ASSERT gl.name == "gitlab"
```

### TS-48-4: GitLabPlatform Create Issue

**Requirement:** 48-REQ-3.3
**Type:** unit
**Description:** Verify GitLabPlatform.create_issue returns an IssueResult.

**Preconditions:**
- Mock httpx response for POST /projects/:id/issues returning 201.

**Input:**
- `title="Test Issue"`, `body="body text"`.

**Expected:**
- Returns `IssueResult` with `number` = GitLab `iid`, `title`, and
  `html_url` = GitLab `web_url`.

**Assertion pseudocode:**
```
mock httpx POST to return {"iid": 42, "title": "Test Issue", "web_url": "https://gitlab.com/..."}
gl = GitLabPlatform(project_id="123", token="t")
result = await gl.create_issue("Test Issue", "body text")
ASSERT result.number == 42
ASSERT result.title == "Test Issue"
ASSERT "gitlab.com" in result.html_url
```

### TS-48-5: GitLabPlatform Search Issues

**Requirement:** 48-REQ-3.1, 48-REQ-3.E2
**Type:** unit
**Description:** Verify GitLabPlatform.search_issues returns matching issues.

**Preconditions:**
- Mock httpx response for GET /projects/:id/issues with search param.

**Input:**
- `title_prefix="[Auditor] my_spec"`.

**Expected:**
- Returns list of IssueResult for matching issues.
- Returns empty list when no matches.

**Assertion pseudocode:**
```
# Case 1: issues found
mock httpx GET to return [{"iid": 1, "title": "[Auditor] my_spec", "web_url": "..."}]
result = await gl.search_issues("[Auditor] my_spec")
ASSERT len(result) == 1
ASSERT result[0].number == 1

# Case 2: no issues found
mock httpx GET to return []
result = await gl.search_issues("[Auditor] other")
ASSERT result == []
```

### TS-48-6: GitLabPlatform Update Issue

**Requirement:** 48-REQ-3.1
**Type:** unit
**Description:** Verify GitLabPlatform.update_issue sends PUT request.

**Preconditions:**
- Mock httpx response for PUT /projects/:id/issues/:iid returning 200.

**Input:**
- `issue_number=42`, `body="updated body"`.

**Expected:**
- No exception raised. PUT request sent with correct payload.

**Assertion pseudocode:**
```
mock httpx PUT to return 200
await gl.update_issue(42, "updated body")
ASSERT mock called with body={"description": "updated body"}
```

### TS-48-7: GitLabPlatform Close Issue

**Requirement:** 48-REQ-3.1
**Type:** unit
**Description:** Verify GitLabPlatform.close_issue sends PUT with
state_event=close.

**Preconditions:**
- Mock httpx response for PUT /projects/:id/issues/:iid returning 200.

**Input:**
- `issue_number=42`, `comment="Closing"`.

**Expected:**
- Comment added via notes endpoint.
- PUT request sent with `state_event=close`.

**Assertion pseudocode:**
```
mock httpx POST (notes) to return 201
mock httpx PUT to return 200
await gl.close_issue(42, comment="Closing")
ASSERT notes POST called with body="Closing"
ASSERT PUT called with {"state_event": "close"}
```

### TS-48-8: GitLabPlatform Add Comment

**Requirement:** 48-REQ-3.1
**Type:** unit
**Description:** Verify GitLabPlatform.add_issue_comment posts a note.

**Preconditions:**
- Mock httpx response for POST /projects/:id/issues/:iid/notes.

**Input:**
- `issue_number=42`, `comment="test comment"`.

**Expected:**
- POST request sent with `body="test comment"`.

**Assertion pseudocode:**
```
mock httpx POST to return 201
await gl.add_issue_comment(42, "test comment")
ASSERT mock called with {"body": "test comment"}
```

### TS-48-9: GitLabPlatform Auth Header

**Requirement:** 48-REQ-3.2
**Type:** unit
**Description:** Verify GitLabPlatform uses PRIVATE-TOKEN header.

**Preconditions:**
- Mock httpx.

**Input:**
- Any API call.

**Expected:**
- Request includes `PRIVATE-TOKEN: <token>` header.

**Assertion pseudocode:**
```
gl = GitLabPlatform(project_id="123", token="my-token")
# trigger any API call (e.g. search_issues)
ASSERT request headers contain {"PRIVATE-TOKEN": "my-token"}
```

### TS-48-10: Factory Returns GitHub

**Requirement:** 48-REQ-4.1
**Type:** unit
**Description:** Verify factory returns GitHubPlatform for type="github".

**Preconditions:**
- `GITHUB_PAT` env var set.
- Git remote is a GitHub URL.

**Input:**
- `PlatformConfig(type="github")`, repo root with GitHub remote.

**Expected:**
- Returns `GitHubPlatform` instance.

**Assertion pseudocode:**
```
with patch.dict(os.environ, {"GITHUB_PAT": "token"}):
    with patch("...get_remote_url", return_value="https://github.com/o/r.git"):
        result = await create_platform(PlatformConfig(type="github"), Path("/repo"))
ASSERT isinstance(result, GitHubPlatform)
```

### TS-48-11: Factory Returns GitLab

**Requirement:** 48-REQ-4.2
**Type:** unit
**Description:** Verify factory returns GitLabPlatform for type="gitlab".

**Preconditions:**
- `GITLAB_PAT` env var set.
- Git remote is a GitLab URL.

**Input:**
- `PlatformConfig(type="gitlab")`, repo root with GitLab remote.

**Expected:**
- Returns `GitLabPlatform` instance.

**Assertion pseudocode:**
```
with patch.dict(os.environ, {"GITLAB_PAT": "token"}):
    with patch("...get_remote_url", return_value="https://gitlab.com/ns/proj.git"):
        result = await create_platform(PlatformConfig(type="gitlab"), Path("/repo"))
ASSERT isinstance(result, GitLabPlatform)
```

### TS-48-12: Factory Returns None for "none"

**Requirement:** 48-REQ-4.3
**Type:** unit
**Description:** Verify factory returns None for type="none".

**Preconditions:**
- None.

**Input:**
- `PlatformConfig(type="none")`.

**Expected:**
- Returns `None`.

**Assertion pseudocode:**
```
result = await create_platform(PlatformConfig(type="none"), Path("/repo"))
ASSERT result is None
```

### TS-48-13: file_or_update_issue Moved Import

**Requirement:** 48-REQ-5.1, 48-REQ-8.1
**Type:** unit
**Description:** Verify file_or_update_issue is importable from the new path.

**Preconditions:**
- None.

**Input:**
- Import from `agent_fox.platform.issues`.

**Expected:**
- Import succeeds. Function is callable.

**Assertion pseudocode:**
```
from agent_fox.platform.issues import file_or_update_issue
ASSERT callable(file_or_update_issue)
```

### TS-48-14: file_or_update_issue Uses Protocol

**Requirement:** 48-REQ-5.2
**Type:** unit
**Description:** Verify file_or_update_issue works with any Platform
implementation.

**Preconditions:**
- Create a mock class satisfying Platform protocol.

**Input:**
- Mock platform with empty search_issues, successful create_issue.

**Expected:**
- Creates issue via mock platform.

**Assertion pseudocode:**
```
mock = MockPlatform()
mock.search_issues.return_value = []
mock.create_issue.return_value = IssueResult(1, "title", "url")
result = await file_or_update_issue("[Test] spec", "body", platform=mock)
ASSERT result == "url"
mock.create_issue.assert_called_once()
```

### TS-48-15: file_or_update_issue Search-Before-Create

**Requirement:** 48-REQ-5.3
**Type:** unit
**Description:** Verify file_or_update_issue updates existing issues.

**Preconditions:**
- Mock platform with existing issue in search results.

**Input:**
- `title_prefix="[Test] spec"`, `body="updated"`.

**Expected:**
- Updates existing issue instead of creating new one.

**Assertion pseudocode:**
```
mock.search_issues.return_value = [IssueResult(1, "[Test] spec", "url")]
result = await file_or_update_issue("[Test] spec", "updated", platform=mock)
mock.update_issue.assert_called_once_with(1, "updated")
mock.create_issue.assert_not_called()
```

### TS-48-16: handle_auditor_issue Renamed

**Requirement:** 48-REQ-6.1, 48-REQ-8.2
**Type:** unit
**Description:** Verify the function is importable by its new name.

**Preconditions:**
- None.

**Input:**
- Import `handle_auditor_issue` from `agent_fox.session.auditor_output`.

**Expected:**
- Import succeeds. Function is callable.

**Assertion pseudocode:**
```
from agent_fox.session.auditor_output import handle_auditor_issue
ASSERT callable(handle_auditor_issue)
```

### TS-48-17: handle_auditor_issue Uses Protocol

**Requirement:** 48-REQ-6.2, 48-REQ-6.3
**Type:** unit
**Description:** Verify handle_auditor_issue works with any Platform.

**Preconditions:**
- Mock Platform. Mock AuditResult with FAIL verdict.

**Input:**
- `spec_name="my_spec"`, FAIL result, mock platform.

**Expected:**
- Calls platform.search_issues and platform.create_issue.

**Assertion pseudocode:**
```
mock_platform.search_issues.return_value = []
await handle_auditor_issue("my_spec", fail_result, platform=mock_platform)
mock_platform.create_issue.assert_called_once()
```

### TS-48-18: PlatformConfig Accepts gitlab

**Requirement:** 48-REQ-7.1
**Type:** unit
**Description:** Verify PlatformConfig accepts "gitlab" as a type value.

**Preconditions:**
- None.

**Input:**
- `PlatformConfig(type="gitlab")`.

**Expected:**
- No validation error. `config.type == "gitlab"`.

**Assertion pseudocode:**
```
config = PlatformConfig(type="gitlab")
ASSERT config.type == "gitlab"
```

### TS-48-19: Old github_issues.py Deleted

**Requirement:** 48-REQ-5.4
**Type:** unit
**Description:** Verify the old session/github_issues.py file no longer
exists.

**Preconditions:**
- Implementation complete.

**Input:**
- Check filesystem path.

**Expected:**
- `agent_fox/session/github_issues.py` does not exist.

**Assertion pseudocode:**
```
path = Path("agent_fox/session/github_issues.py")
ASSERT NOT path.exists()
```

## Property Test Cases

### TS-48-P1: Protocol Structural Conformance

**Property:** Property 1 from design.md
**Validates:** 48-REQ-1.1, 48-REQ-1.2, 48-REQ-2.1, 48-REQ-3.1
**Type:** property
**Description:** Any class implementing all five methods and name property
satisfies the protocol.

**For any:** Dynamically generated class with all required method stubs.
**Invariant:** `isinstance(instance, Platform)` is True.

**Assertion pseudocode:**
```
FOR ANY complete mock class implementing all methods:
    instance = MockClass()
    ASSERT isinstance(instance, Platform) is True
```

### TS-48-P2: Factory Determinism

**Property:** Property 2 from design.md
**Validates:** 48-REQ-4.1, 48-REQ-4.2, 48-REQ-4.3
**Type:** property
**Description:** Factory returns deterministic results for same inputs.

**For any:** platform_type in {"github", "gitlab", "none"}
**Invariant:** Two calls with same config and environment return same type.

**Assertion pseudocode:**
```
FOR ANY platform_type in {"github", "gitlab", "none"}:
    config = PlatformConfig(type=platform_type)
    result1 = await create_platform(config, repo_root)
    result2 = await create_platform(config, repo_root)
    ASSERT type(result1) == type(result2)
```

### TS-48-P3: Factory Graceful Degradation

**Property:** Property 3 from design.md
**Validates:** 48-REQ-4.E1, 48-REQ-4.E2, 48-REQ-4.E3
**Type:** property
**Description:** Factory never raises, returns None on bad input.

**For any:** Random string as platform type, missing env vars.
**Invariant:** `create_platform()` returns None without raising.

**Assertion pseudocode:**
```
FOR ANY type_str in random strings:
    config = PlatformConfig(type=type_str)
    result = await create_platform(config, repo_root)
    ASSERT result is None  # (unless type_str happens to be "github"/"gitlab" with valid env)
```

### TS-48-P4: file_or_update_issue Idempotency

**Property:** Property 4 from design.md
**Validates:** 48-REQ-5.3
**Type:** property
**Description:** N calls with same prefix create at most one issue.

**For any:** N in [1..10], varying body strings.
**Invariant:** `create_issue` called at most once; `update_issue` called
for subsequent calls.

**Assertion pseudocode:**
```
FOR ANY N in 1..10:
    mock = MockPlatform()
    mock.search_issues side_effect: [] first call, then [existing] for subsequent
    FOR i in 1..N:
        await file_or_update_issue("prefix", f"body {i}", platform=mock)
    ASSERT mock.create_issue.call_count <= 1
```

### TS-48-P5: file_or_update_issue Never Raises

**Property:** Property 5 from design.md
**Validates:** 48-REQ-5.E1, 48-REQ-5.E2
**Type:** property
**Description:** file_or_update_issue never raises for any platform state.

**For any:** Platform in {None, raising mock, working mock}.
**Invariant:** Returns str | None, never raises.

**Assertion pseudocode:**
```
FOR ANY platform_state in {None, raising, working}:
    result = await file_or_update_issue("prefix", "body", platform=platform_state)
    ASSERT result is None OR isinstance(result, str)
```

### TS-48-P6: GitLabPlatform Error Handling

**Property:** Property 6 from design.md
**Validates:** 48-REQ-3.E1
**Type:** property
**Description:** GitLabPlatform raises IntegrationError on non-success.

**For any:** HTTP status code in {400, 401, 403, 404, 500, 502, 503}.
**Invariant:** IntegrationError is raised containing the status code.

**Assertion pseudocode:**
```
FOR ANY status_code in non_success_codes:
    mock httpx to return status_code
    ASSERT_RAISES IntegrationError from gl.create_issue(...)
    ASSERT str(status_code) in str(error)
```

### TS-48-P7: Auditor Issue Handling Never Raises

**Property:** Property 7 from design.md
**Validates:** 48-REQ-6.E1
**Type:** property
**Description:** handle_auditor_issue never raises.

**For any:** Platform in {None, raising}, verdict in {"PASS", "FAIL"}.
**Invariant:** Function returns without raising.

**Assertion pseudocode:**
```
FOR ANY (platform, verdict) in combinations:
    # should not raise
    await handle_auditor_issue("spec", make_result(verdict), platform=platform)
```

## Edge Case Tests

### TS-48-E1: Incomplete Protocol Implementation

**Requirement:** 48-REQ-1.E1
**Type:** unit
**Description:** A class missing one method does not satisfy the protocol.

**Preconditions:**
- Define a class with only 4 of 5 required methods.

**Input:**
- `isinstance(instance, Platform)`.

**Expected:**
- Returns False.

**Assertion pseudocode:**
```
class Incomplete:
    name = "test"
    async def search_issues(...): ...
    async def create_issue(...): ...
    async def update_issue(...): ...
    async def add_issue_comment(...): ...
    # missing close_issue

ASSERT isinstance(Incomplete(), Platform) is False
```

### TS-48-E2: GitLab API Error

**Requirement:** 48-REQ-3.E1
**Type:** unit
**Description:** GitLabPlatform raises IntegrationError on API failure.

**Preconditions:**
- Mock httpx to return 403.

**Input:**
- `gl.create_issue("title", "body")`.

**Expected:**
- Raises `IntegrationError` with status code in message.

**Assertion pseudocode:**
```
mock httpx POST to return 403
ASSERT_RAISES IntegrationError:
    await gl.create_issue("title", "body")
```

### TS-48-E3: Factory Missing Token

**Requirement:** 48-REQ-4.E1
**Type:** unit
**Description:** Factory returns None when token env var is missing.

**Preconditions:**
- `GITHUB_PAT` not in environment.

**Input:**
- `PlatformConfig(type="github")`.

**Expected:**
- Returns None. Warning logged.

**Assertion pseudocode:**
```
with patch.dict(os.environ, {}, clear=True):
    result = await create_platform(PlatformConfig(type="github"), Path("/repo"))
ASSERT result is None
```

### TS-48-E4: Factory Unparseable Remote

**Requirement:** 48-REQ-4.E2
**Type:** unit
**Description:** Factory returns None when remote URL is not parseable.

**Preconditions:**
- Token is set but remote URL is not a recognized format.

**Input:**
- `PlatformConfig(type="github")`, remote="https://bitbucket.org/x/y.git".

**Expected:**
- Returns None.

**Assertion pseudocode:**
```
with patch.dict(os.environ, {"GITHUB_PAT": "t"}):
    with patch("...get_remote_url", return_value="https://bitbucket.org/x/y.git"):
        result = await create_platform(PlatformConfig(type="github"), Path("/repo"))
ASSERT result is None
```

### TS-48-E5: Factory Unknown Type

**Requirement:** 48-REQ-4.E3
**Type:** unit
**Description:** Factory returns None for unrecognized platform type.

**Preconditions:**
- None.

**Input:**
- `PlatformConfig(type="bitbucket")`.

**Expected:**
- Returns None.

**Assertion pseudocode:**
```
result = await create_platform(PlatformConfig(type="bitbucket"), Path("/repo"))
ASSERT result is None
```

### TS-48-E6: file_or_update_issue Platform None

**Requirement:** 48-REQ-5.E1
**Type:** unit
**Description:** file_or_update_issue returns None when platform is None.

**Preconditions:**
- None.

**Input:**
- `platform=None`.

**Expected:**
- Returns None. Warning logged.

**Assertion pseudocode:**
```
result = await file_or_update_issue("[Test] spec", "body", platform=None)
ASSERT result is None
```

### TS-48-E7: file_or_update_issue API Error Swallowed

**Requirement:** 48-REQ-5.E2
**Type:** unit
**Description:** file_or_update_issue catches platform exceptions.

**Preconditions:**
- Mock platform whose search_issues raises IntegrationError.

**Input:**
- Mock raising platform.

**Expected:**
- Returns None without raising.

**Assertion pseudocode:**
```
mock.search_issues.side_effect = IntegrationError("fail")
result = await file_or_update_issue("[Test] spec", "body", platform=mock)
ASSERT result is None
```

### TS-48-E8: handle_auditor_issue Platform None

**Requirement:** 48-REQ-6.E1
**Type:** unit
**Description:** handle_auditor_issue returns when platform is None.

**Preconditions:**
- None.

**Input:**
- `platform=None`, FAIL verdict.

**Expected:**
- Returns without raising. Warning logged.

**Assertion pseudocode:**
```
await handle_auditor_issue("spec", fail_result, platform=None)
# no exception
```

### TS-48-E9: GitLab Search No Results

**Requirement:** 48-REQ-3.E2
**Type:** unit
**Description:** GitLabPlatform.search_issues returns empty list.

**Preconditions:**
- Mock httpx GET to return empty array.

**Input:**
- `title_prefix="nonexistent"`.

**Expected:**
- Returns `[]`.

**Assertion pseudocode:**
```
mock httpx GET to return []
result = await gl.search_issues("nonexistent")
ASSERT result == []
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 48-REQ-1.1 | TS-48-1 | unit |
| 48-REQ-1.2 | TS-48-2, TS-48-3, TS-48-P1 | unit, property |
| 48-REQ-1.E1 | TS-48-E1 | unit |
| 48-REQ-2.1 | TS-48-2, TS-48-P1 | unit, property |
| 48-REQ-2.2 | TS-48-2 | unit |
| 48-REQ-3.1 | TS-48-3, TS-48-4, TS-48-5, TS-48-6, TS-48-7, TS-48-8 | unit |
| 48-REQ-3.2 | TS-48-9 | unit |
| 48-REQ-3.3 | TS-48-4 | unit |
| 48-REQ-3.4 | TS-48-3, TS-48-4 | unit |
| 48-REQ-3.5 | TS-48-3 | unit |
| 48-REQ-3.E1 | TS-48-E2, TS-48-P6 | unit, property |
| 48-REQ-3.E2 | TS-48-5, TS-48-E9 | unit |
| 48-REQ-4.1 | TS-48-10, TS-48-P2 | unit, property |
| 48-REQ-4.2 | TS-48-11, TS-48-P2 | unit, property |
| 48-REQ-4.3 | TS-48-12, TS-48-P2 | unit, property |
| 48-REQ-4.4 | TS-48-10, TS-48-11 | unit |
| 48-REQ-4.E1 | TS-48-E3, TS-48-P3 | unit, property |
| 48-REQ-4.E2 | TS-48-E4, TS-48-P3 | unit, property |
| 48-REQ-4.E3 | TS-48-E5, TS-48-P3 | unit, property |
| 48-REQ-5.1 | TS-48-13 | unit |
| 48-REQ-5.2 | TS-48-14 | unit |
| 48-REQ-5.3 | TS-48-15, TS-48-P4 | unit, property |
| 48-REQ-5.4 | TS-48-19 | unit |
| 48-REQ-5.E1 | TS-48-E6, TS-48-P5 | unit, property |
| 48-REQ-5.E2 | TS-48-E7, TS-48-P5 | unit, property |
| 48-REQ-6.1 | TS-48-16 | unit |
| 48-REQ-6.2 | TS-48-17 | unit |
| 48-REQ-6.3 | TS-48-17 | unit |
| 48-REQ-6.E1 | TS-48-E8, TS-48-P7 | unit, property |
| 48-REQ-7.1 | TS-48-18 | unit |
| 48-REQ-7.2 | TS-48-18 | unit |
| 48-REQ-8.1 | TS-48-13 | unit |
| 48-REQ-8.2 | TS-48-16 | unit |
| Property 1 | TS-48-P1 | property |
| Property 2 | TS-48-P2 | property |
| Property 3 | TS-48-P3 | property |
| Property 4 | TS-48-P4 | property |
| Property 5 | TS-48-P5 | property |
| Property 6 | TS-48-P6 | property |
| Property 7 | TS-48-P7 | property |
