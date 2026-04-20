# Test Specification: Git and Platform Overhaul

## Overview

Test cases are organized by requirement area: develop branch management, prompt
template changes, post-harvest integration, GitHub REST API platform,
simplified config, and dead code removal. All git operations are mocked via
`run_git` patches. All HTTP calls are mocked via httpx/respx.

## Test Cases

### TS-19-1: ensure_develop Creates From Remote

**Requirement:** 19-REQ-1.2
**Type:** unit
**Description:** When local develop does not exist but origin/develop does,
ensure_develop creates a local tracking branch.

**Preconditions:**
- No local `develop` branch.
- `origin/develop` exists on the remote.

**Input:**
- `repo_root` pointing to a git repository.

**Expected:**
- `git fetch origin` is called.
- `git branch develop origin/develop` (or equivalent) is called.
- No error is raised.

**Assertion pseudocode:**
```
mock run_git to simulate: no local develop, origin/develop exists
await ensure_develop(repo_root)
ASSERT run_git called with ["fetch", "origin"]
ASSERT run_git called with branch creation from origin/develop
```

---

### TS-19-2: ensure_develop Creates From Default Branch

**Requirement:** 19-REQ-1.3, 19-REQ-1.4
**Type:** unit
**Description:** When neither local nor remote develop exists, ensure_develop
creates develop from the default branch.

**Preconditions:**
- No local `develop` branch.
- No `origin/develop` on the remote.
- Local `main` branch exists.

**Input:**
- `repo_root` pointing to a git repository.

**Expected:**
- `git branch develop main` is called.
- No error is raised.

**Assertion pseudocode:**
```
mock run_git to simulate: no local develop, no origin/develop, main exists
await ensure_develop(repo_root)
ASSERT run_git called with ["branch", "develop", "main"]
```

---

### TS-19-3: ensure_develop Fast-Forwards Behind Local

**Requirement:** 19-REQ-1.6
**Type:** unit
**Description:** When local develop exists but is behind origin/develop,
ensure_develop fast-forwards it.

**Preconditions:**
- Local `develop` exists.
- `origin/develop` is ahead of local `develop`.

**Input:**
- `repo_root` pointing to a git repository.

**Expected:**
- `git fetch origin` is called.
- Local develop is fast-forwarded to match origin/develop.

**Assertion pseudocode:**
```
mock run_git to simulate: develop exists, origin/develop is 2 commits ahead
await ensure_develop(repo_root)
ASSERT run_git called with fast-forward merge or branch update
```

---

### TS-19-4: detect_default_branch Via Symbolic Ref

**Requirement:** 19-REQ-1.4
**Type:** unit
**Description:** detect_default_branch reads the default branch from
git symbolic-ref.

**Preconditions:**
- `refs/remotes/origin/HEAD` points to `refs/remotes/origin/main`.

**Input:**
- `repo_root` pointing to a git repository.

**Expected:**
- Returns `"main"`.

**Assertion pseudocode:**
```
mock run_git for symbolic-ref to return "refs/remotes/origin/main"
result = await detect_default_branch(repo_root)
ASSERT result == "main"
```

---

### TS-19-5: detect_default_branch Fallback Chain

**Requirement:** 19-REQ-1.4
**Type:** unit
**Description:** When symbolic-ref fails, falls back to main, then master.

**Preconditions:**
- `git symbolic-ref` fails.
- No local `main` branch.
- Local `master` branch exists.

**Input:**
- `repo_root` pointing to a git repository.

**Expected:**
- Returns `"master"`.

**Assertion pseudocode:**
```
mock run_git: symbolic-ref fails, "main" does not exist, "master" exists
result = await detect_default_branch(repo_root)
ASSERT result == "master"
```

---

### TS-19-6: push_to_remote Success

**Requirement:** 19-REQ-3.1
**Type:** unit
**Description:** push_to_remote calls git push and returns True on success.

**Preconditions:**
- Remote `origin` is configured and reachable.

**Input:**
- `repo_root`, branch `"develop"`.

**Expected:**
- `git push origin develop` is called.
- Returns `True`.

**Assertion pseudocode:**
```
mock run_git to succeed
result = await push_to_remote(repo_root, "develop")
ASSERT result is True
ASSERT run_git called with ["push", "origin", "develop"]
```

---

### TS-19-7: push_to_remote Failure Returns False

**Requirement:** 19-REQ-3.E1
**Type:** unit
**Description:** push_to_remote logs a warning and returns False on failure.

**Preconditions:**
- Remote push fails (e.g., permission denied).

**Input:**
- `repo_root`, branch `"develop"`.

**Expected:**
- Returns `False`.
- Warning is logged.

**Assertion pseudocode:**
```
mock run_git to fail with returncode 1
result = await push_to_remote(repo_root, "develop")
ASSERT result is False
ASSERT warning logged
```

---

### TS-19-8: git-flow.md Has No Push Instructions

**Requirement:** 19-REQ-2.1, 19-REQ-2.2, 19-REQ-2.3
**Type:** unit
**Description:** The git-flow.md template does not contain git push commands.

**Preconditions:**
- Template file exists at `_templates/prompts/git-flow.md`.

**Input:**
- Read the template file content.

**Expected:**
- Content does not contain `git push`.
- Content does not contain "pushed to `origin`" or similar.

**Assertion pseudocode:**
```
content = read_file("agent_fox/_templates/prompts/git-flow.md")
ASSERT "git push" not in content
ASSERT "pushed to" not in content.lower()
```

---

### TS-19-9: coding.md Has No Push Instructions

**Requirement:** 19-REQ-2.4, 19-REQ-2.5
**Type:** unit
**Description:** The coding.md template does not contain git push commands
or push failure policy.

**Preconditions:**
- Template file exists at `_templates/prompts/coding.md`.

**Input:**
- Read the template file content.

**Expected:**
- Content does not contain `git push`.
- Content does not contain "FAILURE POLICY" section about push retries.

**Assertion pseudocode:**
```
content = read_file("agent_fox/_templates/prompts/coding.md")
ASSERT "git push" not in content
ASSERT "If push fails" not in content
```

---

### TS-19-10: Post-Harvest No Platform Pushes Develop

**Requirement:** 19-REQ-3.1
**Type:** unit
**Description:** With no platform (type="none"), post-harvest pushes develop.

**Preconditions:**
- Harvest completed successfully.
- Platform config type is "none".

**Input:**
- `repo_root`, workspace info, platform config.

**Expected:**
- `push_to_remote(repo_root, "develop")` is called.
- No PR is created.

**Assertion pseudocode:**
```
config = PlatformConfig(type="none")
await _post_harvest_integrate(repo_root, workspace, config)
ASSERT push_to_remote called with "develop"
ASSERT create_pr NOT called
```

---

### TS-19-11: Post-Harvest GitHub Auto-Merge Pushes Both

**Requirement:** 19-REQ-3.2
**Type:** unit
**Description:** With github + auto_merge=true, post-harvest pushes feature
branch and develop.

**Preconditions:**
- Harvest completed successfully.
- Platform config: type="github", auto_merge=true.
- GITHUB_PAT is set.

**Input:**
- `repo_root`, workspace info, platform config.

**Expected:**
- Feature branch is pushed to origin.
- Develop is pushed to origin.
- No PR is created.

**Assertion pseudocode:**
```
config = PlatformConfig(type="github", auto_merge=True)
await _post_harvest_integrate(repo_root, workspace, config)
ASSERT push_to_remote called with feature_branch
ASSERT push_to_remote called with "develop"
ASSERT create_pr NOT called
```

---

### TS-19-12: Post-Harvest GitHub No Auto-Merge Creates PR

**Requirement:** 19-REQ-3.3
**Type:** unit
**Description:** With github + auto_merge=false, post-harvest pushes feature
branch and creates a PR against main.

**Preconditions:**
- Harvest completed successfully.
- Platform config: type="github", auto_merge=false.
- GITHUB_PAT is set.

**Input:**
- `repo_root`, workspace info, platform config.

**Expected:**
- Feature branch is pushed to origin.
- PR is created against the default branch.
- Develop is NOT pushed to origin.

**Assertion pseudocode:**
```
config = PlatformConfig(type="github", auto_merge=False)
await _post_harvest_integrate(repo_root, workspace, config)
ASSERT push_to_remote called with feature_branch
ASSERT push_to_remote NOT called with "develop"
ASSERT create_pr called with feature_branch
```

---

### TS-19-13: GitHubPlatform create_pr Via REST API

**Requirement:** 19-REQ-4.1, 19-REQ-4.2, 19-REQ-4.3
**Type:** unit
**Description:** GitHubPlatform.create_pr posts to the GitHub REST API
with correct auth and payload.

**Preconditions:**
- GitHubPlatform initialized with owner, repo, token.
- Mock HTTP responds with 201.

**Input:**
- `branch="feature/test"`, `title="Test PR"`, `body="Description"`.

**Expected:**
- POST to `/repos/{owner}/{repo}/pulls` with Bearer token.
- Returns the PR URL from the response.

**Assertion pseudocode:**
```
mock httpx POST to return 201, {"html_url": "https://github.com/o/r/pull/1"}
platform = GitHubPlatform(owner="o", repo="r", token="tok")
result = await platform.create_pr("feature/test", "Test PR", "Desc")
ASSERT result == "https://github.com/o/r/pull/1"
ASSERT POST was to "https://api.github.com/repos/o/r/pulls"
ASSERT Authorization header == "Bearer tok"
```

---

### TS-19-14: parse_github_remote HTTPS

**Requirement:** 19-REQ-4.4
**Type:** unit
**Description:** Parses owner/repo from HTTPS GitHub URL.

**Preconditions:** None.

**Input:**
- `"https://github.com/owner/repo.git"`

**Expected:**
- Returns `("owner", "repo")`.

**Assertion pseudocode:**
```
result = parse_github_remote("https://github.com/owner/repo.git")
ASSERT result == ("owner", "repo")
```

---

### TS-19-15: parse_github_remote SSH

**Requirement:** 19-REQ-4.4
**Type:** unit
**Description:** Parses owner/repo from SSH GitHub URL.

**Preconditions:** None.

**Input:**
- `"git@github.com:owner/repo.git"`

**Expected:**
- Returns `("owner", "repo")`.

**Assertion pseudocode:**
```
result = parse_github_remote("git@github.com:owner/repo.git")
ASSERT result == ("owner", "repo")
```

---

### TS-19-16: PlatformConfig Only Has Type and AutoMerge

**Requirement:** 19-REQ-5.1
**Type:** unit
**Description:** PlatformConfig accepts only type and auto_merge fields.

**Preconditions:** None.

**Input:**
- `PlatformConfig(type="github", auto_merge=True)`

**Expected:**
- Object created with type="github" and auto_merge=True.
- No other fields exist (wait_for_ci, etc. are gone).

**Assertion pseudocode:**
```
config = PlatformConfig(type="github", auto_merge=True)
ASSERT config.type == "github"
ASSERT config.auto_merge is True
ASSERT not hasattr(config, "wait_for_ci")
```

## Edge Case Tests

### TS-19-E1: ensure_develop Local Already Exists

**Requirement:** 19-REQ-1.E1
**Type:** unit
**Description:** When develop already exists and is up-to-date, no-op.

**Preconditions:**
- Local `develop` exists.
- Local is at or ahead of `origin/develop`.

**Input:**
- `repo_root`.

**Expected:**
- No branch creation calls.
- No error raised.

**Assertion pseudocode:**
```
mock: develop exists, up-to-date with origin/develop
await ensure_develop(repo_root)
ASSERT no branch creation calls made
```

---

### TS-19-E2: ensure_develop No Default Branch

**Requirement:** 19-REQ-1.E2
**Type:** unit
**Description:** Raises WorkspaceError when no suitable base branch exists.

**Preconditions:**
- No local develop.
- No origin/develop.
- No main, no master.

**Input:**
- `repo_root`.

**Expected:**
- `WorkspaceError` is raised.

**Assertion pseudocode:**
```
mock: no develop, no origin/develop, no main, no master
ASSERT ensure_develop(repo_root) raises WorkspaceError
```

---

### TS-19-E3: ensure_develop Fetch Fails

**Requirement:** 19-REQ-1.E3
**Type:** unit
**Description:** When fetch fails, warns and uses local state.

**Preconditions:**
- Fetch fails (no network).
- Local `main` exists.

**Input:**
- `repo_root`.

**Expected:**
- Warning is logged.
- Develop is created from local `main`.

**Assertion pseudocode:**
```
mock: fetch fails, local main exists
await ensure_develop(repo_root)
ASSERT warning logged about fetch failure
ASSERT develop created from main
```

---

### TS-19-E4: ensure_develop Diverged Branches

**Requirement:** 19-REQ-1.E4
**Type:** unit
**Description:** When local and remote develop have diverged, warns and
uses local as-is.

**Preconditions:**
- Local `develop` has commits not on `origin/develop`.
- `origin/develop` has commits not on local `develop`.

**Input:**
- `repo_root`.

**Expected:**
- Warning about divergence is logged.
- Local develop is not modified.

**Assertion pseudocode:**
```
mock: develop exists, diverged from origin/develop
await ensure_develop(repo_root)
ASSERT warning logged about divergence
ASSERT no branch update calls
```

---

### TS-19-E5: Post-Harvest Push Failure Continues

**Requirement:** 19-REQ-3.E1
**Type:** unit
**Description:** When push fails, log warning and continue.

**Preconditions:**
- Harvest succeeded.
- Push to origin fails.

**Input:**
- `repo_root`, workspace, config type="none".

**Expected:**
- Warning logged.
- No exception raised.

**Assertion pseudocode:**
```
mock push_to_remote to return False
await _post_harvest_integrate(repo_root, workspace, config)
ASSERT warning logged
ASSERT no exception raised
```

---

### TS-19-E6: Post-Harvest PR Creation Failure Continues

**Requirement:** 19-REQ-3.E2
**Type:** unit
**Description:** When PR creation fails, log warning and continue.

**Preconditions:**
- Platform type="github", auto_merge=false.
- Feature branch push succeeds.
- PR creation raises IntegrationError.

**Input:**
- `repo_root`, workspace, config.

**Expected:**
- Warning logged.
- No exception raised.

**Assertion pseudocode:**
```
mock create_pr to raise IntegrationError
await _post_harvest_integrate(repo_root, workspace, config)
ASSERT warning logged
ASSERT no exception raised
```

---

### TS-19-E7: GITHUB_PAT Not Set Falls Back

**Requirement:** 19-REQ-4.E1
**Type:** unit
**Description:** Missing GITHUB_PAT causes fallback to no-platform behavior.

**Preconditions:**
- Platform type="github".
- GITHUB_PAT env var is not set.

**Input:**
- Post-harvest integration with github config.

**Expected:**
- Warning logged about missing token.
- Develop is pushed (fallback behavior).
- No PR created.

**Assertion pseudocode:**
```
unset GITHUB_PAT
config = PlatformConfig(type="github", auto_merge=False)
await _post_harvest_integrate(repo_root, workspace, config)
ASSERT warning logged about GITHUB_PAT
ASSERT push_to_remote called with "develop"
ASSERT create_pr NOT called
```

---

### TS-19-E8: GitHub API Auth Error Falls Back

**Requirement:** 19-REQ-4.E2
**Type:** unit
**Description:** GitHub API 401 causes fallback to no-platform behavior.

**Preconditions:**
- GITHUB_PAT is set but invalid.
- GitHub API returns 401.

**Input:**
- `create_pr` call.

**Expected:**
- `IntegrationError` raised.

**Assertion pseudocode:**
```
mock httpx POST to return 401
platform = GitHubPlatform(owner="o", repo="r", token="bad")
ASSERT platform.create_pr(...) raises IntegrationError
```

---

### TS-19-E9: Non-GitHub Remote URL

**Requirement:** 19-REQ-4.E4
**Type:** unit
**Description:** Non-GitHub remote URL returns None from parser.

**Preconditions:** None.

**Input:**
- `"https://gitlab.com/owner/repo.git"`

**Expected:**
- Returns `None`.

**Assertion pseudocode:**
```
result = parse_github_remote("https://gitlab.com/owner/repo.git")
ASSERT result is None
```

---

### TS-19-E10: Config With Old Fields Parses OK

**Requirement:** 19-REQ-5.E1
**Type:** unit
**Description:** Config with removed fields loads without error.

**Preconditions:** None.

**Input:**
- `PlatformConfig(type="github", auto_merge=True, wait_for_ci=True, labels=["bot"])`

**Expected:**
- Object created with type="github", auto_merge=True.
- Extra fields silently ignored.

**Assertion pseudocode:**
```
config = PlatformConfig(**{"type": "github", "auto_merge": True, "wait_for_ci": True, "labels": ["bot"]})
ASSERT config.type == "github"
ASSERT config.auto_merge is True
ASSERT not hasattr(config, "wait_for_ci")
```

---

### TS-19-E11: Feature Branch Deleted Before Push

**Requirement:** 19-REQ-3.E3
**Type:** unit
**Description:** If feature branch no longer exists locally, skip pushing it.

**Preconditions:**
- Platform type="github", auto_merge=true.
- Feature branch has been deleted.

**Input:**
- `repo_root`, workspace, config.

**Expected:**
- Warning logged about missing branch.
- Develop is still pushed.

**Assertion pseudocode:**
```
mock local_branch_exists to return False for feature branch
await _post_harvest_integrate(repo_root, workspace, config)
ASSERT warning logged
ASSERT push_to_remote called with "develop"
ASSERT push_to_remote NOT called with feature_branch
```

## Property Test Cases

### TS-19-P1: No Push Instructions In Any Template

**Property:** Property 3 from design.md
**Validates:** 19-REQ-2.1, 19-REQ-2.4, 19-REQ-2.E1
**Type:** property
**Description:** No template file contains git push instructions.

**For any:** template file in `agent_fox/_templates/prompts/`
**Invariant:** The file content does not contain the string `git push`.

**Assertion pseudocode:**
```
FOR ANY template_file IN glob("agent_fox/_templates/prompts/*.md"):
    content = read(template_file)
    ASSERT "git push" not in content
```

---

### TS-19-P2: Remote URL Parsing Roundtrip

**Property:** Property 6 from design.md
**Validates:** 19-REQ-4.4, 19-REQ-4.E4
**Type:** property
**Description:** GitHub URLs parse correctly, non-GitHub URLs return None.

**For any:** owner (alphanum+hyphens), repo (alphanum+hyphens+underscores)
**Invariant:** Both HTTPS and SSH forms parse to (owner, repo). Non-GitHub
URLs return None.

**Assertion pseudocode:**
```
FOR ANY owner IN text(alphabet+digits+"-", min_size=1, max_size=39):
    FOR ANY repo IN text(alphabet+digits+"-_", min_size=1, max_size=100):
        https_url = f"https://github.com/{owner}/{repo}.git"
        ssh_url = f"git@github.com:{owner}/{repo}.git"
        ASSERT parse_github_remote(https_url) == (owner, repo)
        ASSERT parse_github_remote(ssh_url) == (owner, repo)

FOR ANY host IN text() WHERE host != "github.com":
    url = f"https://{host}/owner/repo.git"
    ASSERT parse_github_remote(url) is None
```

---

### TS-19-P3: Config Backward Compatibility

**Property:** Property 7 from design.md
**Validates:** 19-REQ-5.E1
**Type:** property
**Description:** Old config fields are silently ignored.

**For any:** combination of old field names and values
**Invariant:** PlatformConfig parses without error, only type and auto_merge
are retained.

**Assertion pseudocode:**
```
FOR ANY old_fields IN subsets_of({"wait_for_ci": bool, "wait_for_review": bool,
                                   "ci_timeout": int, "pr_granularity": str,
                                   "labels": list}):
    data = {"type": "none", "auto_merge": False, **old_fields}
    config = PlatformConfig(**data)
    ASSERT config.type == "none"
    ASSERT config.auto_merge is False
```

---

### TS-19-P4: Post-Harvest Strategy Matches Config

**Property:** Property 4 from design.md
**Validates:** 19-REQ-3.1, 19-REQ-3.2, 19-REQ-3.3
**Type:** property
**Description:** The push strategy is determined solely by platform config.

**For any:** platform type in {"none", "github"}, auto_merge in {True, False}
**Invariant:** Develop is pushed iff type="none" or auto_merge=True. PR is
created iff type="github" and auto_merge=False.

**Assertion pseudocode:**
```
FOR ANY (ptype, auto) IN product(["none", "github"], [True, False]):
    config = PlatformConfig(type=ptype, auto_merge=auto)
    actions = simulate_post_harvest(config)
    ASSERT ("push", "develop") in actions == (ptype == "none" or auto is True)
    ASSERT "create_pr" in actions == (ptype == "github" and auto is False)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 19-REQ-1.1 | TS-19-1 | unit |
| 19-REQ-1.2 | TS-19-1 | unit |
| 19-REQ-1.3 | TS-19-2 | unit |
| 19-REQ-1.4 | TS-19-4, TS-19-5 | unit |
| 19-REQ-1.5 | TS-19-2 | unit |
| 19-REQ-1.6 | TS-19-3 | unit |
| 19-REQ-1.E1 | TS-19-E1 | unit |
| 19-REQ-1.E2 | TS-19-E2 | unit |
| 19-REQ-1.E3 | TS-19-E3 | unit |
| 19-REQ-1.E4 | TS-19-E4 | unit |
| 19-REQ-2.1 | TS-19-8, TS-19-P1 | unit, property |
| 19-REQ-2.2 | TS-19-8 | unit |
| 19-REQ-2.3 | TS-19-8 | unit |
| 19-REQ-2.4 | TS-19-9, TS-19-P1 | unit, property |
| 19-REQ-2.5 | TS-19-9 | unit |
| 19-REQ-2.E1 | TS-19-P1 | property |
| 19-REQ-3.1 | TS-19-6, TS-19-10, TS-19-P4 | unit, property |
| 19-REQ-3.2 | TS-19-11, TS-19-P4 | unit, property |
| 19-REQ-3.3 | TS-19-12, TS-19-P4 | unit, property |
| 19-REQ-3.4 | TS-19-10 | unit |
| 19-REQ-3.E1 | TS-19-7, TS-19-E5 | unit |
| 19-REQ-3.E2 | TS-19-E6 | unit |
| 19-REQ-3.E3 | TS-19-E11 | unit |
| 19-REQ-4.1 | TS-19-13 | unit |
| 19-REQ-4.2 | TS-19-13 | unit |
| 19-REQ-4.3 | TS-19-13 | unit |
| 19-REQ-4.4 | TS-19-14, TS-19-15, TS-19-P2 | unit, property |
| 19-REQ-4.E1 | TS-19-E7 | unit |
| 19-REQ-4.E2 | TS-19-E8 | unit |
| 19-REQ-4.E3 | TS-19-E8 | unit |
| 19-REQ-4.E4 | TS-19-E9, TS-19-P2 | unit, property |
| 19-REQ-5.1 | TS-19-16 | unit |
| 19-REQ-5.2 | TS-19-16 | unit |
| 19-REQ-5.3 | TS-19-16 | unit |
| 19-REQ-5.E1 | TS-19-E10, TS-19-P3 | unit, property |
| 19-REQ-6.1 | (verified by removal) | — |
| 19-REQ-6.2 | (verified by removal) | — |
| 19-REQ-6.3 | (verified by removal) | — |
| 19-REQ-6.4 | (verified by test updates) | — |
| Property 1 | TS-19-1, TS-19-2 | unit |
| Property 2 | TS-19-3 | unit |
| Property 3 | TS-19-P1 | property |
| Property 4 | TS-19-P4 | property |
| Property 5 | TS-19-E7 | unit |
| Property 6 | TS-19-P2 | property |
| Property 7 | TS-19-P3 | property |
