# Test Specification: Platform Integration

## Overview

Tests for the platform integration layer: the Platform protocol, NullPlatform
(direct merge), GitHubPlatform (gh CLI), and the create_platform factory.
All `gh` CLI and `git` subprocess calls are mocked -- no real GitHub or git
interaction occurs during testing. Tests map to requirements in
`requirements.md` and correctness properties in `design.md`.

## Test Cases

### TS-10-1: Platform protocol defines required methods

**Requirement:** 10-REQ-1.1
**Type:** unit
**Description:** Verify the Platform protocol declares all four required async
methods with correct signatures.

**Preconditions:** None.

**Input:**
- Inspect `Platform` protocol class attributes.

**Expected:**
- Protocol has methods: `create_pr`, `wait_for_ci`, `wait_for_review`,
  `merge_pr`.
- `create_pr` returns `str`.
- `wait_for_ci` returns `bool`.
- `wait_for_review` returns `bool`.
- `merge_pr` returns `None`.

**Assertion pseudocode:**
```
ASSERT hasattr(Platform, "create_pr")
ASSERT hasattr(Platform, "wait_for_ci")
ASSERT hasattr(Platform, "wait_for_review")
ASSERT hasattr(Platform, "merge_pr")
```

---

### TS-10-2: NullPlatform satisfies Platform protocol

**Requirement:** 10-REQ-2.1
**Type:** unit
**Description:** Verify NullPlatform is a structural subtype of Platform.

**Preconditions:** None.

**Input:**
- `isinstance` check or `runtime_checkable` protocol check.

**Expected:**
- NullPlatform satisfies the Platform protocol.

**Assertion pseudocode:**
```
ASSERT isinstance(NullPlatform(), Platform)
```

---

### TS-10-3: NullPlatform.create_pr merges directly and returns empty string

**Requirement:** 10-REQ-2.2
**Type:** unit
**Description:** Verify NullPlatform merges the branch into develop and returns
an empty string.

**Preconditions:**
- `subprocess.run` is mocked to succeed for both `git checkout` and `git merge`.

**Input:**
- `await NullPlatform().create_pr("feature/test", "Title", "Body", ["label"])`

**Expected:**
- `subprocess.run` called with `["git", "checkout", "develop"]`.
- `subprocess.run` called with `["git", "merge", "--no-ff", "feature/test"]`.
- Return value is `""`.

**Assertion pseudocode:**
```
mock_subprocess(returncode=0)
result = await null_platform.create_pr("feature/test", "Title", "Body", [])
ASSERT result == ""
ASSERT mock called with ["git", "checkout", "develop"]
ASSERT mock called with ["git", "merge", "--no-ff", "feature/test"]
```

---

### TS-10-4: NullPlatform.wait_for_ci returns True immediately

**Requirement:** 10-REQ-2.3
**Type:** unit
**Description:** Verify NullPlatform CI waiting always returns True.

**Preconditions:** None.

**Input:**
- `await NullPlatform().wait_for_ci("", 600)`

**Expected:**
- Returns `True`.
- No subprocess calls made.

**Assertion pseudocode:**
```
result = await null_platform.wait_for_ci("", 600)
ASSERT result is True
```

---

### TS-10-5: NullPlatform.wait_for_review returns True immediately

**Requirement:** 10-REQ-2.4
**Type:** unit
**Description:** Verify NullPlatform review waiting always returns True.

**Preconditions:** None.

**Input:**
- `await NullPlatform().wait_for_review("")`

**Expected:**
- Returns `True`.

**Assertion pseudocode:**
```
result = await null_platform.wait_for_review("")
ASSERT result is True
```

---

### TS-10-6: NullPlatform.merge_pr is a no-op

**Requirement:** 10-REQ-2.5
**Type:** unit
**Description:** Verify NullPlatform merge is a no-op.

**Preconditions:** None.

**Input:**
- `await NullPlatform().merge_pr("")`

**Expected:**
- Returns None.
- No subprocess calls made.

**Assertion pseudocode:**
```
result = await null_platform.merge_pr("")
ASSERT result is None
```

---

### TS-10-7: GitHubPlatform.create_pr calls gh pr create

**Requirement:** 10-REQ-3.2
**Type:** unit
**Description:** Verify GitHubPlatform creates a PR using the gh CLI and returns
the PR URL.

**Preconditions:**
- `gh` CLI is available and authenticated (mocked).
- `subprocess.run` mocked to return successful `gh pr create` output.

**Input:**
- `await github_platform.create_pr("feature/test", "My PR", "Body text", ["bug", "urgent"])`

**Expected:**
- `gh pr create` called with `--head feature/test`, `--title "My PR"`,
  `--body "Body text"`, `--label bug`, `--label urgent`.
- Returns the PR URL from stdout.

**Assertion pseudocode:**
```
mock_subprocess(stdout="https://github.com/owner/repo/pull/42\n", returncode=0)
result = await github_platform.create_pr("feature/test", "My PR", "Body text", ["bug", "urgent"])
ASSERT result == "https://github.com/owner/repo/pull/42"
ASSERT "--head" IN mock_call_args
ASSERT "--label" IN mock_call_args
```

---

### TS-10-8: GitHubPlatform.wait_for_ci returns True when all checks pass

**Requirement:** 10-REQ-3.3
**Type:** unit
**Description:** Verify wait_for_ci returns True when all CI checks report
success.

**Preconditions:**
- `gh pr checks` mocked to return JSON with all checks completed and
  succeeded.

**Input:**
- `await github_platform.wait_for_ci("https://github.com/owner/repo/pull/42", 600)`

**Expected:**
- Returns `True`.

**Assertion pseudocode:**
```
mock_gh_checks([
    {"name": "build", "state": "completed", "conclusion": "success"},
    {"name": "lint", "state": "completed", "conclusion": "success"},
])
result = await github_platform.wait_for_ci(pr_url, 600)
ASSERT result is True
```

---

### TS-10-9: GitHubPlatform.wait_for_review returns True when approved

**Requirement:** 10-REQ-3.4
**Type:** unit
**Description:** Verify wait_for_review returns True when the PR is approved.

**Preconditions:**
- `gh pr view` mocked to return `{"reviewDecision": "APPROVED"}`.

**Input:**
- `await github_platform.wait_for_review("https://github.com/owner/repo/pull/42")`

**Expected:**
- Returns `True`.

**Assertion pseudocode:**
```
mock_gh_view({"reviewDecision": "APPROVED"})
result = await github_platform.wait_for_review(pr_url)
ASSERT result is True
```

---

### TS-10-10: GitHubPlatform.merge_pr calls gh pr merge

**Requirement:** 10-REQ-3.5
**Type:** unit
**Description:** Verify merge_pr executes gh pr merge successfully.

**Preconditions:**
- `gh pr merge` mocked to succeed.

**Input:**
- `await github_platform.merge_pr("https://github.com/owner/repo/pull/42")`

**Expected:**
- `gh pr merge` called with the PR URL and `--merge` flag.
- No exception raised.

**Assertion pseudocode:**
```
mock_subprocess(returncode=0)
await github_platform.merge_pr(pr_url)
ASSERT mock called with ["gh", "pr", "merge", pr_url, "--merge"]
```

---

### TS-10-11: Factory returns NullPlatform for type "none"

**Requirement:** 10-REQ-5.2
**Type:** unit
**Description:** Verify create_platform returns NullPlatform when type is "none".

**Preconditions:** None.

**Input:**
- `create_platform(PlatformConfig(type="none"))`

**Expected:**
- Returns an instance of NullPlatform.

**Assertion pseudocode:**
```
platform = create_platform(PlatformConfig(type="none"))
ASSERT isinstance(platform, NullPlatform)
```

---

### TS-10-12: Factory returns GitHubPlatform for type "github"

**Requirement:** 10-REQ-5.3
**Type:** unit
**Description:** Verify create_platform returns GitHubPlatform when type is
"github".

**Preconditions:**
- `gh` CLI is available and authenticated (mocked).

**Input:**
- `create_platform(PlatformConfig(type="github"))`

**Expected:**
- Returns an instance of GitHubPlatform.

**Assertion pseudocode:**
```
mock_gh_available()
platform = create_platform(PlatformConfig(type="github"))
ASSERT isinstance(platform, GitHubPlatform)
```

## Property Test Cases

### TS-10-P1: NullPlatform gates always pass

**Property:** Property 1 from design.md
**Validates:** 10-REQ-2.3, 10-REQ-2.4
**Type:** property
**Description:** NullPlatform always returns True for CI and review gates.

**For any:** integer timeout >= 0, any PR URL string
**Invariant:** `wait_for_ci` and `wait_for_review` both return True.

**Assertion pseudocode:**
```
FOR ANY timeout IN non_negative_integers(),
        pr_url IN text_strings():
    null = NullPlatform()
    ASSERT await null.wait_for_ci(pr_url, timeout) is True
    ASSERT await null.wait_for_review(pr_url) is True
```

---

### TS-10-P2: NullPlatform create_pr returns empty string

**Property:** Property 2 from design.md
**Validates:** 10-REQ-2.2
**Type:** property
**Description:** NullPlatform always returns empty string from create_pr.

**For any:** branch name, title, body, labels list (with mocked subprocess)
**Invariant:** Return value is `""`.

**Assertion pseudocode:**
```
FOR ANY branch IN text_strings(),
        title IN text_strings(),
        body IN text_strings(),
        labels IN lists(text_strings()):
    mock_subprocess(returncode=0)
    result = await NullPlatform().create_pr(branch, title, body, labels)
    ASSERT result == ""
```

---

### TS-10-P3: Factory rejects unknown platform types

**Property:** Property 3 from design.md
**Validates:** 10-REQ-5.E1
**Type:** property
**Description:** Any platform type not in {"none", "github"} raises ConfigError.

**For any:** string not in {"none", "github"}
**Invariant:** `create_platform` raises `ConfigError`.

**Assertion pseudocode:**
```
FOR ANY type_str IN text_strings().filter(lambda s: s not in ("none", "github")):
    ASSERT_RAISES ConfigError FROM create_platform(PlatformConfig(type=type_str))
```

## Edge Case Tests

### TS-10-E1: GitHubPlatform raises when gh not installed

**Requirement:** 10-REQ-3.E1
**Type:** unit
**Description:** Verify GitHubPlatform raises IntegrationError when gh CLI is
not found.

**Preconditions:**
- `shutil.which("gh")` mocked to return None.

**Input:**
- `GitHubPlatform()`

**Expected:**
- `IntegrationError` raised.
- Message mentions "gh" and "install".

**Assertion pseudocode:**
```
mock_shutil_which(return_value=None)
ASSERT_RAISES IntegrationError FROM GitHubPlatform()
ASSERT "gh" IN str(error)
```

---

### TS-10-E2: GitHubPlatform raises when gh not authenticated

**Requirement:** 10-REQ-3.E1
**Type:** unit
**Description:** Verify GitHubPlatform raises IntegrationError when gh is
installed but not authenticated.

**Preconditions:**
- `shutil.which("gh")` returns a path.
- `gh auth status` mocked to return non-zero exit code.

**Input:**
- `GitHubPlatform()`

**Expected:**
- `IntegrationError` raised.
- Message mentions "authenticated" or "auth login".

**Assertion pseudocode:**
```
mock_shutil_which(return_value="/usr/bin/gh")
mock_subprocess("gh auth status", returncode=1)
ASSERT_RAISES IntegrationError FROM GitHubPlatform()
ASSERT "auth" IN str(error).lower()
```

---

### TS-10-E3: GitHubPlatform.create_pr raises on gh failure

**Requirement:** 10-REQ-3.E2
**Type:** unit
**Description:** Verify create_pr raises IntegrationError when gh pr create
fails.

**Preconditions:**
- `gh` is available and authenticated (mocked).
- `gh pr create` mocked to return non-zero exit code.

**Input:**
- `await github_platform.create_pr("feature/test", "Title", "Body", [])`

**Expected:**
- `IntegrationError` raised.
- Error contains the command stderr.

**Assertion pseudocode:**
```
mock_subprocess("gh pr create", returncode=1, stderr="no permission")
ASSERT_RAISES IntegrationError FROM await github_platform.create_pr(...)
ASSERT "no permission" IN str(error)
```

---

### TS-10-E4: GitHubPlatform.wait_for_ci returns False on check failure

**Requirement:** 10-REQ-3.E3
**Type:** unit
**Description:** Verify wait_for_ci returns False when a CI check fails.

**Preconditions:**
- `gh pr checks` mocked to return JSON with one failed check.

**Input:**
- `await github_platform.wait_for_ci(pr_url, 600)`

**Expected:**
- Returns `False`.

**Assertion pseudocode:**
```
mock_gh_checks([
    {"name": "build", "state": "completed", "conclusion": "failure"},
])
result = await github_platform.wait_for_ci(pr_url, 600)
ASSERT result is False
```

---

### TS-10-E5: GitHubPlatform.wait_for_ci returns False on timeout

**Requirement:** 10-REQ-3.E4
**Type:** unit
**Description:** Verify wait_for_ci returns False when the timeout expires
before checks complete.

**Preconditions:**
- `gh pr checks` mocked to always return in_progress state.
- Timeout set to a small value (e.g., 1 second).
- Poll interval patched to 0 to speed up the test.

**Input:**
- `await github_platform.wait_for_ci(pr_url, 1)`

**Expected:**
- Returns `False` after the timeout.

**Assertion pseudocode:**
```
mock_gh_checks([{"name": "build", "state": "in_progress", "conclusion": ""}])
patch(_CI_POLL_INTERVAL, 0)
result = await github_platform.wait_for_ci(pr_url, 1)
ASSERT result is False
```

---

### TS-10-E6: GitHubPlatform.wait_for_review returns False on changes requested

**Requirement:** 10-REQ-3.E5
**Type:** unit
**Description:** Verify wait_for_review returns False when changes are
requested.

**Preconditions:**
- `gh pr view` mocked to return `{"reviewDecision": "CHANGES_REQUESTED"}`.

**Input:**
- `await github_platform.wait_for_review(pr_url)`

**Expected:**
- Returns `False`.

**Assertion pseudocode:**
```
mock_gh_view({"reviewDecision": "CHANGES_REQUESTED"})
result = await github_platform.wait_for_review(pr_url)
ASSERT result is False
```

---

### TS-10-E7: GitHubPlatform.merge_pr raises on merge failure

**Requirement:** 10-REQ-3.E6
**Type:** unit
**Description:** Verify merge_pr raises IntegrationError when gh pr merge fails.

**Preconditions:**
- `gh pr merge` mocked to return non-zero exit code.

**Input:**
- `await github_platform.merge_pr(pr_url)`

**Expected:**
- `IntegrationError` raised.
- Error contains the merge failure details.

**Assertion pseudocode:**
```
mock_subprocess("gh pr merge", returncode=1, stderr="merge conflict")
ASSERT_RAISES IntegrationError FROM await github_platform.merge_pr(pr_url)
ASSERT "merge conflict" IN str(error)
```

---

### TS-10-E8: Factory raises ConfigError for unknown platform type

**Requirement:** 10-REQ-5.E1
**Type:** unit
**Description:** Verify create_platform raises ConfigError for unrecognized
platform types.

**Preconditions:** None.

**Input:**
- `create_platform(PlatformConfig(type="gitlab"))`

**Expected:**
- `ConfigError` raised.
- Message lists valid platform types.

**Assertion pseudocode:**
```
ASSERT_RAISES ConfigError FROM create_platform(PlatformConfig(type="gitlab"))
ASSERT "none" IN str(error)
ASSERT "github" IN str(error)
```

---

### TS-10-E9: NullPlatform.create_pr raises on merge conflict

**Requirement:** 10-REQ-2.2
**Type:** unit
**Description:** Verify NullPlatform raises IntegrationError when git merge
fails.

**Preconditions:**
- `git checkout` succeeds.
- `git merge` mocked to return non-zero exit code.

**Input:**
- `await NullPlatform().create_pr("feature/conflict", "Title", "Body", [])`

**Expected:**
- `IntegrationError` raised.
- Error mentions the branch name.

**Assertion pseudocode:**
```
mock_subprocess("git checkout", returncode=0)
mock_subprocess("git merge", returncode=1, stderr="CONFLICT")
ASSERT_RAISES IntegrationError FROM await null_platform.create_pr("feature/conflict", ...)
ASSERT "feature/conflict" IN str(error)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 10-REQ-1.1 | TS-10-1 | unit |
| 10-REQ-2.1 | TS-10-2 | unit |
| 10-REQ-2.2 | TS-10-3, TS-10-P2, TS-10-E9 | unit, property |
| 10-REQ-2.3 | TS-10-4, TS-10-P1 | unit, property |
| 10-REQ-2.4 | TS-10-5, TS-10-P1 | unit, property |
| 10-REQ-2.5 | TS-10-6 | unit |
| 10-REQ-3.1 | TS-10-12 | unit |
| 10-REQ-3.2 | TS-10-7 | unit |
| 10-REQ-3.3 | TS-10-8 | unit |
| 10-REQ-3.4 | TS-10-9 | unit |
| 10-REQ-3.5 | TS-10-10 | unit |
| 10-REQ-3.E1 | TS-10-E1, TS-10-E2 | unit |
| 10-REQ-3.E2 | TS-10-E3 | unit |
| 10-REQ-3.E3 | TS-10-E4 | unit |
| 10-REQ-3.E4 | TS-10-E5 | unit |
| 10-REQ-3.E5 | TS-10-E6 | unit |
| 10-REQ-3.E6 | TS-10-E7 | unit |
| 10-REQ-5.2 | TS-10-11 | unit |
| 10-REQ-5.3 | TS-10-12 | unit |
| 10-REQ-5.E1 | TS-10-E8, TS-10-P3 | unit, property |
| Property 1 | TS-10-P1 | property |
| Property 2 | TS-10-P2 | property |
| Property 3 | TS-10-P3 | property |
| Property 4 | TS-10-11, TS-10-12 | unit |
