---
name: af-release
description: >-
  Create a new versioned release of agent-fox. Bumps version in pyproject.toml
  and __init__.py, regenerates the lockfile, commits to develop, merges into
  main, tags, and creates a GitHub release. Use when the user wants to cut a
  release, bump the version, or publish a new version.
---

# af-release — Cut a New Release

You are an autonomous release agent. The user provides a VERSION string
(e.g. `2.6.3`). You perform every step below **in order, without halting for
confirmation**, unless a step explicitly says to halt.

**Single-pass mandate:** Complete all steps from start to finish. Only stop if
a step fails in a way that cannot be recovered.

---

## Step 0: Validate Input

`$ARGUMENTS` must be a valid semver version: `MAJOR.MINOR.PATCH`
(e.g. `2.6.3`). Pre-release suffixes are not supported.

**Validation regex:** `^\d+\.\d+\.\d+$`

If invalid, halt with:

```
Invalid version: "$ARGUMENTS"

Usage: /af-release 2.6.3
```

Store the validated version as `VERSION` and the tag as `TAG` = `v{VERSION}`.

---

## Step 1: Pre-flight Checks

### 1.1 Clean working tree

```bash
git status --porcelain
```

If the output is non-empty, **halt**:

```
Working tree has uncommitted changes. Commit or stash before releasing.
```

### 1.2 On the correct branch

```bash
git branch --show-current
```

If not on `develop`, check it out:

```bash
git checkout develop
git pull origin develop
```

### 1.3 Tag collision

```bash
git tag --list "v{VERSION}"
```

If the tag already exists, **halt**:

```
Tag v{VERSION} already exists. Choose a different version.
```

### 1.4 Confirm tests pass

```bash
make check
```

If `make check` fails, **halt** and show the output. Do not release broken
code.

---

## Step 2: Bump Version

Update the version string in exactly two files. Use precise string replacement
— do not rewrite entire files.

### 2.1 `pyproject.toml`

Replace the existing `version = "..."` line in the `[project]` section with:

```
version = "{VERSION}"
```

### 2.2 `agent_fox/__init__.py`

Replace the existing `__version__ = "..."` line with:

```python
__version__ = "{VERSION}"
```

### 2.3 Regenerate lockfile

```bash
uv lock
```

This updates `uv.lock` to reflect the new version.

### 2.4 Verify the bump

Read both files back and confirm the version strings match `{VERSION}`.

---

## Step 3: Commit the Version Bump

```bash
git add pyproject.toml agent_fox/__init__.py uv.lock
git commit -m "chore: bump version to {VERSION}"
```

Only stage these three files. Do not use `git add -A`.

---

## Step 4: Push develop

```bash
git push origin develop
```

If the push fails, retry up to 3 times (2 s, 4 s, 8 s backoff). If all
retries fail, halt with the error.

---

## Step 5: Merge into main

```bash
git checkout main
git pull origin main
git merge develop --no-ff -m "Merge develop into main for v{VERSION}"
```

If the merge has conflicts, **halt** and list the conflicting files. Do not
auto-resolve release merges.

---

## Step 6: Tag and Push main

```bash
git tag -a "v{VERSION}" -m "Release v{VERSION}"
git push origin main --follow-tags
```

If the push fails, retry up to 3 times with backoff. If all retries fail, halt.

---

## Step 7: Create GitHub Release

Generate release notes by comparing the previous tag to the new one.

### 7.1 Find the previous tag

```bash
git tag --sort=-v:refname | head -2
```

The second line is the previous tag. Store it as `PREV_TAG`.

### 7.2 Collect changelog

```bash
git log {PREV_TAG}..v{VERSION} --oneline --no-merges
```

Group commits by conventional-commit type and format as markdown bullet
points. Example:

```markdown
## What's Changed

- **feat:** add prompt caching support
- **fix:** correct timeout handling in engine
- **refactor:** simplify platform factory

**Full Changelog**: https://github.com/agent-fox-dev/agent-fox/compare/{PREV_TAG}...v{VERSION}
```

### 7.3 Create the release

```bash
gh release create "v{VERSION}" \
  --repo agent-fox-dev/agent-fox \
  --title "v{VERSION}" \
  --notes "{release_notes}"
```

If `gh` fails, print the release notes so they can be pasted manually.

---

## Step 8: Return to develop

```bash
git checkout develop
```

---

## Step 9: Completion Summary

Print:

```
[af-release] Release v{VERSION} complete.
  Tag:       v{VERSION}
  GitHub:    https://github.com/agent-fox-dev/agent-fox/releases/tag/v{VERSION}
  Commits:   {N} commits since {PREV_TAG}
  Files:     pyproject.toml, agent_fox/__init__.py, uv.lock
```
