# Test Specification: Platform Config Overhaul

## Overview

Tests validate the platform config schema changes, post-harvest
simplification, `create_pr` removal, API URL resolution, platform factory
wiring, and config template generation. Test cases map 1:1 to acceptance
criteria in requirements.md. Property tests cover the six correctness
properties from design.md.

## Test Cases

### TS-65-1: PlatformConfig has no auto_merge field

**Requirement:** 65-REQ-1.1
**Type:** unit
**Description:** Verify `PlatformConfig()` does not expose `auto_merge`.

**Preconditions:**
- None.

**Input:**
- `config = PlatformConfig()`

**Expected:**
- `hasattr(config, "auto_merge")` is `False`.

**Assertion pseudocode:**
```
config = PlatformConfig()
ASSERT NOT hasattr(config, "auto_merge")
```

### TS-65-2: Old auto_merge key silently ignored

**Requirement:** 65-REQ-1.2
**Type:** unit
**Description:** Verify config with `auto_merge` key loads without error.

**Preconditions:**
- None.

**Input:**
- `config = PlatformConfig(type="github", auto_merge=True)`

**Expected:**
- Config loads successfully.
- `config.type == "github"`.
- `hasattr(config, "auto_merge")` is `False`.

**Assertion pseudocode:**
```
config = PlatformConfig(type="github", auto_merge=True)
ASSERT config.type == "github"
ASSERT NOT hasattr(config, "auto_merge")
```

### TS-65-3: PlatformConfig exposes url field

**Requirement:** 65-REQ-2.1
**Type:** unit
**Description:** Verify `PlatformConfig` has a `url` field of type string.

**Preconditions:**
- None.

**Input:**
- `config = PlatformConfig(url="github.example.com")`

**Expected:**
- `config.url == "github.example.com"`.

**Assertion pseudocode:**
```
config = PlatformConfig(url="github.example.com")
ASSERT config.url == "github.example.com"
```

### TS-65-4: Default url for github type

**Requirement:** 65-REQ-2.2, 65-REQ-2.3
**Type:** unit
**Description:** Verify default `url` is empty string, resolved to
`github.com` for GitHub type and unused for `none` type.

**Preconditions:**
- None.

**Input:**
- `github_config = PlatformConfig(type="github")`
- `none_config = PlatformConfig(type="none")`

**Expected:**
- `github_config.url == ""` (consumers resolve to `github.com`).
- `none_config.url == ""`.

**Assertion pseudocode:**
```
github_config = PlatformConfig(type="github")
ASSERT github_config.url == ""

none_config = PlatformConfig(type="none")
ASSERT none_config.url == ""
```

### TS-65-5: API base URL resolves to api.github.com

**Requirement:** 65-REQ-2.4, 65-REQ-5.2
**Type:** unit
**Description:** Verify `github.com` URL resolves to `https://api.github.com`.

**Preconditions:**
- `GitHubPlatform` instantiated with `url="github.com"`.

**Input:**
- Inspect internal API base URL after construction.

**Expected:**
- API base is `https://api.github.com`.

**Assertion pseudocode:**
```
platform = GitHubPlatform(owner="o", repo="r", token="t", url="github.com")
ASSERT platform._api_base == "https://api.github.com"
```

### TS-65-6: API base URL resolves for GitHub Enterprise

**Requirement:** 65-REQ-2.5, 65-REQ-5.3
**Type:** unit
**Description:** Verify non-default URL resolves to `https://{url}/api/v3`.

**Preconditions:**
- `GitHubPlatform` instantiated with `url="github.example.com"`.

**Input:**
- Inspect internal API base URL after construction.

**Expected:**
- API base is `https://github.example.com/api/v3`.

**Assertion pseudocode:**
```
platform = GitHubPlatform(owner="o", repo="r", token="t", url="github.example.com")
ASSERT platform._api_base == "https://github.example.com/api/v3"
```

### TS-65-7: Post-harvest pushes feature branch

**Requirement:** 65-REQ-3.1
**Type:** unit
**Description:** Verify post-harvest pushes the feature branch to origin.

**Preconditions:**
- Mocked git subprocess (push succeeds).
- Feature branch exists locally.

**Input:**
- `post_harvest_integrate(repo_root, workspace)` (no platform_config).

**Expected:**
- `push_to_remote(repo_root, feature_branch)` is called.

**Assertion pseudocode:**
```
mock push_to_remote, local_branch_exists (returns True)
await post_harvest_integrate(repo_root, workspace)
ASSERT push_to_remote called with (repo_root, workspace.branch)
```

### TS-65-8: Post-harvest pushes develop

**Requirement:** 65-REQ-3.2
**Type:** unit
**Description:** Verify post-harvest pushes develop to origin.

**Preconditions:**
- Mocked git subprocess (push succeeds).

**Input:**
- `post_harvest_integrate(repo_root, workspace)`.

**Expected:**
- `_push_develop_if_pushable(repo_root)` is called.

**Assertion pseudocode:**
```
mock _push_develop_if_pushable
await post_harvest_integrate(repo_root, workspace)
ASSERT _push_develop_if_pushable called with (repo_root,)
```

### TS-65-9: Post-harvest has no platform_config parameter

**Requirement:** 65-REQ-3.3
**Type:** unit
**Description:** Verify `post_harvest_integrate` signature has no
`platform_config` parameter.

**Preconditions:**
- None.

**Input:**
- Inspect function signature via `inspect.signature`.

**Expected:**
- Parameter names are `("repo_root", "workspace")` only.

**Assertion pseudocode:**
```
import inspect
sig = inspect.signature(post_harvest_integrate)
ASSERT "platform_config" NOT IN sig.parameters
```

### TS-65-10: Post-harvest does not import GitHubPlatform

**Requirement:** 65-REQ-3.4
**Type:** unit
**Description:** Verify `post_harvest_integrate` function body does not
reference `GitHubPlatform`.

**Preconditions:**
- None.

**Input:**
- Read source code of `post_harvest_integrate`.

**Expected:**
- Source does not contain `GitHubPlatform`.

**Assertion pseudocode:**
```
import inspect
source = inspect.getsource(post_harvest_integrate)
ASSERT "GitHubPlatform" NOT IN source
```

### TS-65-11: Post-harvest push failure is best-effort

**Requirement:** 65-REQ-3.5
**Type:** unit
**Description:** Verify push failure logs warning but does not raise.

**Preconditions:**
- Mocked git subprocess (push fails).

**Input:**
- `post_harvest_integrate(repo_root, workspace)`.

**Expected:**
- No exception raised.
- Warning logged.

**Assertion pseudocode:**
```
mock push_to_remote to return False
await post_harvest_integrate(repo_root, workspace)
# no exception raised
ASSERT warning logged
```

### TS-65-12: PlatformProtocol has no create_pr

**Requirement:** 65-REQ-4.1
**Type:** unit
**Description:** Verify `PlatformProtocol` does not define `create_pr`.

**Preconditions:**
- None.

**Input:**
- Inspect `PlatformProtocol` class.

**Expected:**
- `create_pr` is not in the protocol's methods.

**Assertion pseudocode:**
```
ASSERT NOT hasattr(PlatformProtocol, "create_pr")
```

### TS-65-13: GitHubPlatform has no create_pr

**Requirement:** 65-REQ-4.2
**Type:** unit
**Description:** Verify `GitHubPlatform` does not implement `create_pr`.

**Preconditions:**
- None.

**Input:**
- Inspect `GitHubPlatform` class.

**Expected:**
- `create_pr` is not a method on the class.

**Assertion pseudocode:**
```
ASSERT NOT hasattr(GitHubPlatform, "create_pr")
```

### TS-65-14: GitHubPlatform has no _get_default_branch

**Requirement:** 65-REQ-4.3
**Type:** unit
**Description:** Verify `GitHubPlatform` does not have `_get_default_branch`.

**Preconditions:**
- None.

**Input:**
- Inspect `GitHubPlatform` class.

**Expected:**
- `_get_default_branch` is not a method on the class.

**Assertion pseudocode:**
```
ASSERT NOT hasattr(GitHubPlatform, "_get_default_branch")
```

### TS-65-15: GitHubPlatform accepts url parameter

**Requirement:** 65-REQ-5.1
**Type:** unit
**Description:** Verify `GitHubPlatform.__init__` accepts a `url` parameter.

**Preconditions:**
- None.

**Input:**
- `GitHubPlatform(owner="o", repo="r", token="t", url="github.example.com")`

**Expected:**
- No error; instance created.

**Assertion pseudocode:**
```
platform = GitHubPlatform(owner="o", repo="r", token="t", url="github.example.com")
ASSERT platform is not None
```

### TS-65-16: Platform factory passes url to GitHubPlatform

**Requirement:** 65-REQ-6.1
**Type:** unit
**Description:** Verify `create_platform` wires `url` from config.

**Preconditions:**
- Config with `type="github"`, `url="github.example.com"`.
- `GITHUB_PAT` set in environment.
- Git remote parseable.

**Input:**
- `create_platform(config, project_root)`.

**Expected:**
- Returned `GitHubPlatform` uses `"github.example.com"` as URL.

**Assertion pseudocode:**
```
config.platform.type = "github"
config.platform.url = "github.example.com"
set GITHUB_PAT env
mock git remote to return valid URL
platform = create_platform(config, project_root)
ASSERT platform._url == "github.example.com"
```

### TS-65-17: Config template includes type and url

**Requirement:** 65-REQ-7.1
**Type:** unit
**Description:** Verify generated config template has `type` and `url`
under `[platform]`.

**Preconditions:**
- None.

**Input:**
- `generate_config_template()`.

**Expected:**
- Output contains `type` field line under `[platform]`.
- Output contains `url` field line under `[platform]`.

**Assertion pseudocode:**
```
template = generate_config_template()
platform_section = extract_section(template, "platform")
ASSERT "type" IN platform_section
ASSERT "url" IN platform_section
```

### TS-65-18: Config template excludes auto_merge

**Requirement:** 65-REQ-7.2
**Type:** unit
**Description:** Verify generated config template has no `auto_merge`.

**Preconditions:**
- None.

**Input:**
- `generate_config_template()`.

**Expected:**
- Output does not contain `auto_merge` anywhere.

**Assertion pseudocode:**
```
template = generate_config_template()
ASSERT "auto_merge" NOT IN template
```

## Edge Case Tests

### TS-65-E1: Unknown keys alongside auto_merge ignored

**Requirement:** 65-REQ-1.E1
**Type:** unit
**Description:** Verify multiple unknown keys are all silently ignored.

**Preconditions:**
- None.

**Input:**
- `PlatformConfig(type="github", auto_merge=True, foo="bar", baz=42)`

**Expected:**
- Config loads. `config.type == "github"`.
- No `auto_merge`, `foo`, or `baz` attributes.

**Assertion pseudocode:**
```
config = PlatformConfig(type="github", auto_merge=True, foo="bar", baz=42)
ASSERT config.type == "github"
ASSERT NOT hasattr(config, "auto_merge")
ASSERT NOT hasattr(config, "foo")
ASSERT NOT hasattr(config, "baz")
```

### TS-65-E2: url set with type=none is accepted

**Requirement:** 65-REQ-2.E1
**Type:** unit
**Description:** Verify `url` with `type="none"` loads without error.

**Preconditions:**
- None.

**Input:**
- `PlatformConfig(type="none", url="github.example.com")`

**Expected:**
- Config loads. `config.url == "github.example.com"`.

**Assertion pseudocode:**
```
config = PlatformConfig(type="none", url="github.example.com")
ASSERT config.type == "none"
ASSERT config.url == "github.example.com"
```

### TS-65-E3: Feature branch deleted before post-harvest

**Requirement:** 65-REQ-3.E1
**Type:** unit
**Description:** Verify deleted feature branch is skipped, develop still
pushed.

**Preconditions:**
- Mocked `local_branch_exists` returns `False`.

**Input:**
- `post_harvest_integrate(repo_root, workspace)`.

**Expected:**
- Feature branch push skipped.
- Warning logged.
- Develop push still attempted.

**Assertion pseudocode:**
```
mock local_branch_exists to return False
mock _push_develop_if_pushable
await post_harvest_integrate(repo_root, workspace)
ASSERT push_to_remote NOT called with feature_branch
ASSERT _push_develop_if_pushable called
ASSERT warning logged
```

### TS-65-E4: Empty url defaults to github.com behavior

**Requirement:** 65-REQ-5.E1
**Type:** unit
**Description:** Verify empty `url` resolves to `api.github.com`.

**Preconditions:**
- None.

**Input:**
- `GitHubPlatform(owner="o", repo="r", token="t", url="")`

**Expected:**
- API base is `https://api.github.com`.

**Assertion pseudocode:**
```
platform = GitHubPlatform(owner="o", repo="r", token="t", url="")
ASSERT platform._api_base == "https://api.github.com"
```

### TS-65-E5: Missing GITHUB_PAT exits with code 1

**Requirement:** 65-REQ-6.E1
**Type:** unit
**Description:** Verify platform factory exits if `GITHUB_PAT` is unset.

**Preconditions:**
- `GITHUB_PAT` not in environment.
- Config with `type="github"`.

**Input:**
- `create_platform(config, project_root)`.

**Expected:**
- `sys.exit(1)` called.

**Assertion pseudocode:**
```
unset GITHUB_PAT
config.platform.type = "github"
ASSERT create_platform(config, project_root) calls sys.exit(1)
```

## Property Test Cases

### TS-65-P1: Post-harvest always pushes both branches

**Property:** Property 1 from design.md
**Validates:** 65-REQ-3.1, 65-REQ-3.2
**Type:** property
**Description:** For any workspace, post-harvest attempts to push both
feature branch and develop.

**For any:** workspace with arbitrary branch name (alphanumeric + `/._-`,
1-100 chars)
**Invariant:** `push_to_remote` is called with the feature branch (if it
exists locally) AND `_push_develop_if_pushable` is called.

**Assertion pseudocode:**
```
FOR ANY branch_name IN branch_strategy:
    workspace = make_workspace(branch=branch_name)
    mock local_branch_exists to return True
    mock push_to_remote, _push_develop_if_pushable
    await post_harvest_integrate(repo_root, workspace)
    ASSERT push_to_remote called with (repo_root, branch_name)
    ASSERT _push_develop_if_pushable called with (repo_root,)
```

### TS-65-P2: Post-harvest never calls GitHub API

**Property:** Property 2 from design.md
**Validates:** 65-REQ-3.3, 65-REQ-3.4
**Type:** property
**Description:** The source of `post_harvest_integrate` contains no
references to `GitHubPlatform`, `httpx`, or `parse_github_remote`.

**For any:** N/A (static analysis of source code)
**Invariant:** Source code of `post_harvest_integrate` does not contain
GitHub API references.

**Assertion pseudocode:**
```
source = inspect.getsource(post_harvest_integrate)
ASSERT "GitHubPlatform" NOT IN source
ASSERT "httpx" NOT IN source
ASSERT "parse_github_remote" NOT IN source
ASSERT "GITHUB_PAT" NOT IN source
```

### TS-65-P3: API URL resolution is deterministic

**Property:** Property 3 from design.md
**Validates:** 65-REQ-2.4, 65-REQ-2.5, 65-REQ-5.2, 65-REQ-5.3, 65-REQ-5.E1
**Type:** property
**Description:** URL resolution produces `api.github.com` for
`github.com`/empty, and `{url}/api/v3` otherwise.

**For any:** URL string (hostname-like: alphanumeric + `.-`, 1-253 chars)
**Invariant:** If url is `"github.com"` or `""`, base is
`https://api.github.com`; otherwise `https://{url}/api/v3`.

**Assertion pseudocode:**
```
FOR ANY url IN hostname_strategy:
    platform = GitHubPlatform(owner="o", repo="r", token="t", url=url)
    IF url IN ("github.com", ""):
        ASSERT platform._api_base == "https://api.github.com"
    ELSE:
        ASSERT platform._api_base == f"https://{url}/api/v3"
```

### TS-65-P4: Unknown config keys silently ignored

**Property:** Property 4 from design.md
**Validates:** 65-REQ-1.1, 65-REQ-1.2, 65-REQ-1.E1
**Type:** property
**Description:** Arbitrary extra keys are silently dropped.

**For any:** Dictionary with `type` in `{"none", "github"}` and 0-10
random extra string keys
**Invariant:** `PlatformConfig(**d)` succeeds, and only `type` and `url`
are accessible as attributes.

**Assertion pseudocode:**
```
FOR ANY extra_keys IN dict_strategy:
    d = {"type": "github", **extra_keys}
    config = PlatformConfig(**d)
    ASSERT config.type == "github"
    FOR key IN extra_keys:
        ASSERT NOT hasattr(config, key)
```

### TS-65-P5: Platform factory wires url

**Property:** Property 5 from design.md
**Validates:** 65-REQ-6.1
**Type:** property
**Description:** The URL from config is passed through to GitHubPlatform.

**For any:** URL string (hostname-like, 1-253 chars)
**Invariant:** `create_platform` passes URL to `GitHubPlatform` constructor.

**Assertion pseudocode:**
```
FOR ANY url IN hostname_strategy:
    config.platform.type = "github"
    config.platform.url = url
    set GITHUB_PAT env
    mock subprocess, GitHubPlatform constructor
    create_platform(config, project_root)
    ASSERT GitHubPlatform called with url=(url or "github.com")
```

### TS-65-P6: Config template schema correctness

**Property:** Property 6 from design.md
**Validates:** 65-REQ-7.1, 65-REQ-7.2
**Type:** property
**Description:** Generated template always includes `type` and `url`,
never `auto_merge`.

**For any:** N/A (deterministic output)
**Invariant:** Template contains `type` and `url` under `[platform]` and
does not contain `auto_merge`.

**Assertion pseudocode:**
```
template = generate_config_template()
ASSERT "type" IN template
ASSERT "url" IN template
ASSERT "auto_merge" NOT IN template
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|---|---|---|
| 65-REQ-1.1 | TS-65-1 | unit |
| 65-REQ-1.2 | TS-65-2 | unit |
| 65-REQ-1.E1 | TS-65-E1 | unit |
| 65-REQ-2.1 | TS-65-3 | unit |
| 65-REQ-2.2 | TS-65-4 | unit |
| 65-REQ-2.3 | TS-65-4 | unit |
| 65-REQ-2.4 | TS-65-5 | unit |
| 65-REQ-2.5 | TS-65-6 | unit |
| 65-REQ-2.E1 | TS-65-E2 | unit |
| 65-REQ-3.1 | TS-65-7 | unit |
| 65-REQ-3.2 | TS-65-8 | unit |
| 65-REQ-3.3 | TS-65-9 | unit |
| 65-REQ-3.4 | TS-65-10 | unit |
| 65-REQ-3.5 | TS-65-11 | unit |
| 65-REQ-3.E1 | TS-65-E3 | unit |
| 65-REQ-3.E2 | — | (existing behavior, covered by spec 36 tests) |
| 65-REQ-4.1 | TS-65-12 | unit |
| 65-REQ-4.2 | TS-65-13 | unit |
| 65-REQ-4.3 | TS-65-14 | unit |
| 65-REQ-5.1 | TS-65-15 | unit |
| 65-REQ-5.2 | TS-65-5 | unit |
| 65-REQ-5.3 | TS-65-6 | unit |
| 65-REQ-5.E1 | TS-65-E4 | unit |
| 65-REQ-6.1 | TS-65-16 | unit |
| 65-REQ-6.E1 | TS-65-E5 | unit |
| 65-REQ-7.1 | TS-65-17 | unit |
| 65-REQ-7.2 | TS-65-18 | unit |
| 65-REQ-7.3 | TS-65-17 | unit |
| Property 1 | TS-65-P1 | property |
| Property 2 | TS-65-P2 | property |
| Property 3 | TS-65-P3 | property |
| Property 4 | TS-65-P4 | property |
| Property 5 | TS-65-P5 | property |
| Property 6 | TS-65-P6 | property |
