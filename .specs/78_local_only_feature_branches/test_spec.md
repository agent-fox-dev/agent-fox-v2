# Test Specification: Local-Only Feature Branches

## Overview

Tests verify that feature branches are no longer pushed to the remote during
post-harvest integration, and that all agent/skill templates reflect the
local-only branch workflow. Test cases map to requirements 78-REQ-1 through
78-REQ-4 and correctness properties 1 through 4.

## Test Cases

### TS-78-1: Post-harvest does not push feature branch

**Requirement:** 78-REQ-1.1
**Type:** unit
**Description:** `post_harvest_integrate` never calls `push_to_remote` with the
feature branch name.

**Preconditions:**
- `push_to_remote` and `_push_develop_if_pushable` are mocked.

**Input:**
- `repo_root`: any Path
- `workspace`: WorkspaceInfo with branch `"feature/test_spec/1"`

**Expected:**
- `push_to_remote` is NOT called at all (it should only be called indirectly
  via `_push_develop_if_pushable`, which is separately mocked).

**Assertion pseudocode:**
```
mock push_to_remote, _push_develop_if_pushable
await post_harvest_integrate(repo_root, workspace)
ASSERT push_to_remote.call_count == 0
```

### TS-78-2: Post-harvest still pushes develop

**Requirement:** 78-REQ-1.2
**Type:** unit
**Description:** `post_harvest_integrate` calls `_push_develop_if_pushable`.

**Preconditions:**
- `_push_develop_if_pushable` is mocked.

**Input:**
- `repo_root`: any Path
- `workspace`: WorkspaceInfo with any branch name

**Expected:**
- `_push_develop_if_pushable(repo_root)` is called exactly once.

**Assertion pseudocode:**
```
mock _push_develop_if_pushable
await post_harvest_integrate(repo_root, workspace)
ASSERT _push_develop_if_pushable.called_once_with(repo_root)
```

### TS-78-3: Post-harvest does not check feature branch existence

**Requirement:** 78-REQ-1.3
**Type:** unit
**Description:** `post_harvest_integrate` does not call `local_branch_exists`.

**Preconditions:**
- `local_branch_exists` and `_push_develop_if_pushable` are mocked.

**Input:**
- `repo_root`: any Path
- `workspace`: WorkspaceInfo with any branch name

**Expected:**
- `local_branch_exists` is NOT called.

**Assertion pseudocode:**
```
mock local_branch_exists, _push_develop_if_pushable
await post_harvest_integrate(repo_root, workspace)
ASSERT local_branch_exists.call_count == 0
```

### TS-78-4: agents_md.md has no "pushed to origin" in session completion

**Requirement:** 78-REQ-2.1
**Type:** unit
**Description:** The agent instructions template does not tell agents to push
feature branches to origin in the session completion section.

**Preconditions:**
- Template file exists at `_templates/agents_md.md`.

**Input:**
- Content of the template file.

**Expected:**
- The string `pushed to \`origin\`` does not appear in the file.

**Assertion pseudocode:**
```
content = read("_templates/agents_md.md")
ASSERT "pushed to `origin`" NOT IN content
```

### TS-78-5: agents_md.md has no "push the feature branch"

**Requirement:** 78-REQ-2.2
**Type:** unit
**Description:** The agent instructions template does not instruct agents to
push feature branches.

**Preconditions:**
- Template file exists at `_templates/agents_md.md`.

**Input:**
- Content of the template file.

**Expected:**
- The string `push the feature branch` does not appear in the file.

**Assertion pseudocode:**
```
content = read("_templates/agents_md.md")
ASSERT "push the feature branch" NOT IN content
```

### TS-78-6: agents_md.md describes local-only feature branches

**Requirement:** 78-REQ-2.3
**Type:** unit
**Description:** The agent instructions template contains guidance that
feature branches are local-only.

**Preconditions:**
- Template file exists at `_templates/agents_md.md`.

**Input:**
- Content of the template file.

**Expected:**
- The content contains a statement about feature branches being local-only
  (the phrase "local-only" or "local only" appears).

**Assertion pseudocode:**
```
content = read("_templates/agents_md.md").lower()
ASSERT "local-only" IN content OR "local only" IN content
```

### TS-78-7: af-spec template has no "pushed to remote" in Definition of Done

**Requirement:** 78-REQ-3.1
**Type:** unit
**Description:** The af-spec skill template does not reference pushing to
remote in the Definition of Done.

**Preconditions:**
- Template file exists at `_templates/skills/af-spec`.

**Input:**
- Content of the template file.

**Expected:**
- The string `pushed to remote` does not appear in the file.

**Assertion pseudocode:**
```
content = read("_templates/skills/af-spec")
ASSERT "pushed to remote" NOT IN content
```

### TS-78-8: af-spec template git-flow has no feature branch push

**Requirement:** 78-REQ-3.2
**Type:** unit
**Description:** The af-spec skill template's git-flow comment does not
instruct pushing feature branches.

**Preconditions:**
- Template file exists at `_templates/skills/af-spec`.

**Input:**
- Content of the template file.

**Expected:**
- The git-flow line does not contain "push" as a separate step after "merge
  to develop".

**Assertion pseudocode:**
```
content = read("_templates/skills/af-spec")
FOR line IN content.lines:
    IF "git-flow" IN line.lower() OR "feature branch from develop" IN line:
        ASSERT "-> push" NOT IN line
```

### TS-78-9: Erratum file exists for spec 65

**Requirement:** 78-REQ-4.1
**Type:** unit
**Description:** An erratum file documents the divergence from spec 65.

**Preconditions:**
- Implementation is complete.

**Input:**
- File system path `docs/errata/65_no_feature_branch_push.md`.

**Expected:**
- The file exists and contains references to 65-REQ-3.1 and 65-REQ-3.E1.

**Assertion pseudocode:**
```
content = read("docs/errata/65_no_feature_branch_push.md")
ASSERT "65-REQ-3.1" IN content
ASSERT "65-REQ-3.E1" IN content
```

## Edge Case Tests

### TS-78-E1: Post-harvest with deleted feature branch still pushes develop

**Requirement:** 78-REQ-1.E1
**Type:** unit
**Description:** Even if the workspace's feature branch no longer exists
locally, `post_harvest_integrate` still pushes develop without error.

**Preconditions:**
- `_push_develop_if_pushable` is mocked.

**Input:**
- `repo_root`: any Path
- `workspace`: WorkspaceInfo with branch `"feature/deleted/1"`

**Expected:**
- No exception is raised.
- `_push_develop_if_pushable(repo_root)` is called.

**Assertion pseudocode:**
```
mock _push_develop_if_pushable
await post_harvest_integrate(repo_root, workspace)  # no exception
ASSERT _push_develop_if_pushable.called_once_with(repo_root)
```

## Property Test Cases

### TS-78-P1: Post-harvest never pushes feature branch

**Property:** Property 1 from design.md
**Validates:** 78-REQ-1.1, 78-REQ-1.3
**Type:** property
**Description:** For any workspace, `post_harvest_integrate` never calls
`push_to_remote` directly.

**For any:** WorkspaceInfo with branch name drawn from
`st.from_regex(r"feature/[a-z_]+/[0-9]+")`.
**Invariant:** `push_to_remote` is never called directly by
`post_harvest_integrate` (only indirectly via `_push_develop_if_pushable`).

**Assertion pseudocode:**
```
FOR ANY branch IN feature_branch_strategy:
    workspace = WorkspaceInfo(branch=branch, ...)
    mock push_to_remote, _push_develop_if_pushable
    await post_harvest_integrate(repo_root, workspace)
    ASSERT push_to_remote.call_count == 0
```

### TS-78-P2: Post-harvest always pushes develop

**Property:** Property 2 from design.md
**Validates:** 78-REQ-1.2, 78-REQ-1.E1
**Type:** property
**Description:** For any workspace, `post_harvest_integrate` always calls
`_push_develop_if_pushable`.

**For any:** WorkspaceInfo with branch name drawn from
`st.from_regex(r"feature/[a-z_]+/[0-9]+")`.
**Invariant:** `_push_develop_if_pushable` is called exactly once with the
repo_root.

**Assertion pseudocode:**
```
FOR ANY branch IN feature_branch_strategy:
    workspace = WorkspaceInfo(branch=branch, ...)
    mock _push_develop_if_pushable
    await post_harvest_integrate(repo_root, workspace)
    ASSERT _push_develop_if_pushable.called_once_with(repo_root)
```

### TS-78-P3: Agent template has no feature branch push instructions

**Property:** Property 3 from design.md
**Validates:** 78-REQ-2.1, 78-REQ-2.2
**Type:** property
**Description:** The agents_md.md template never instructs pushing feature
branches.

**For any:** The current content of `_templates/agents_md.md`.
**Invariant:** Content does not contain "pushed to `origin`" or "push the
feature branch".

**Assertion pseudocode:**
```
content = read("_templates/agents_md.md")
ASSERT "pushed to `origin`" NOT IN content
ASSERT "push the feature branch" NOT IN content
```

### TS-78-P4: Spec template has no feature branch push instructions

**Property:** Property 4 from design.md
**Validates:** 78-REQ-3.1, 78-REQ-3.2
**Type:** property
**Description:** The af-spec skill template does not reference pushing feature
branches.

**For any:** The current content of `_templates/skills/af-spec`.
**Invariant:** Content does not contain "pushed to remote" and the git-flow
line does not include "-> push".

**Assertion pseudocode:**
```
content = read("_templates/skills/af-spec")
ASSERT "pushed to remote" NOT IN content
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 78-REQ-1.1 | TS-78-1 | unit |
| 78-REQ-1.2 | TS-78-2 | unit |
| 78-REQ-1.3 | TS-78-3 | unit |
| 78-REQ-1.E1 | TS-78-E1 | unit |
| 78-REQ-2.1 | TS-78-4 | unit |
| 78-REQ-2.2 | TS-78-5 | unit |
| 78-REQ-2.3 | TS-78-6 | unit |
| 78-REQ-3.1 | TS-78-7 | unit |
| 78-REQ-3.2 | TS-78-8 | unit |
| 78-REQ-4.1 | TS-78-9 | unit |
| Property 1 | TS-78-P1 | property |
| Property 2 | TS-78-P2 | property |
| Property 3 | TS-78-P3 | property |
| Property 4 | TS-78-P4 | property |
