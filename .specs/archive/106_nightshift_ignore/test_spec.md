# Test Specification: Night-Shift Ignore File

## Overview

Tests verify that the `.night-shift` ignore file is correctly loaded, parsed,
and applied during hunt scans, and that the init command creates it. Tests map
to requirements from `requirements.md` and correctness properties from
`design.md`.

## Test Cases

### TS-106-1: Load ignore spec from valid `.night-shift` file

**Requirement:** 106-REQ-1.1, 106-REQ-1.2
**Type:** unit
**Description:** Verify that `load_ignore_spec` reads and parses a valid
`.night-shift` file from the project root.

**Preconditions:**
- A temporary directory with a `.night-shift` file containing: `vendor/**\n*.log`

**Input:**
- `project_root` pointing to the temporary directory

**Expected:**
- Returns a `NightShiftIgnoreSpec`
- `spec.is_ignored("vendor/lib.py")` returns `True`
- `spec.is_ignored("output.log")` returns `True`
- `spec.is_ignored("src/main.py")` returns `False`

**Assertion pseudocode:**
```
spec = load_ignore_spec(project_root)
ASSERT isinstance(spec, NightShiftIgnoreSpec)
ASSERT spec.is_ignored("vendor/lib.py") == True
ASSERT spec.is_ignored("output.log") == True
ASSERT spec.is_ignored("src/main.py") == False
```

### TS-106-2: Comments and blank lines are ignored

**Requirement:** 106-REQ-1.3
**Type:** unit
**Description:** Verify that comment lines and blank lines in `.night-shift`
do not produce patterns.

**Preconditions:**
- `.night-shift` containing: `# this is a comment\n\n  \n*.tmp`

**Input:**
- `project_root` pointing to the temporary directory

**Expected:**
- `spec.is_ignored("file.tmp")` returns `True`
- `spec.is_ignored("# this is a comment")` returns `False` (literal filename)
- `spec.is_ignored("src/app.py")` returns `False`

**Assertion pseudocode:**
```
spec = load_ignore_spec(project_root)
ASSERT spec.is_ignored("file.tmp") == True
ASSERT spec.is_ignored("src/app.py") == False
```

### TS-106-3: Missing `.night-shift` file returns defaults-only spec

**Requirement:** 106-REQ-1.4
**Type:** unit
**Description:** Verify that a missing `.night-shift` file yields a spec with
only default exclusions.

**Preconditions:**
- A temporary directory with no `.night-shift` file

**Input:**
- `project_root` pointing to the temporary directory

**Expected:**
- Returns a valid `NightShiftIgnoreSpec`
- Default exclusions are applied (`.agent-fox/foo` is ignored)
- Non-default paths are not ignored (`src/main.py` is not ignored)

**Assertion pseudocode:**
```
spec = load_ignore_spec(project_root)
ASSERT spec.is_ignored(".agent-fox/config.toml") == True
ASSERT spec.is_ignored(".git/HEAD") == True
ASSERT spec.is_ignored("src/main.py") == False
```

### TS-106-4: Default exclusions always applied

**Requirement:** 106-REQ-2.1
**Type:** unit
**Description:** Verify that all default exclusion patterns are applied
regardless of `.night-shift` content.

**Preconditions:**
- `.night-shift` file containing only `*.log`

**Input:**
- `project_root` pointing to the temporary directory

**Expected:**
- `.agent-fox/state.jsonl` is ignored
- `.git/HEAD` is ignored
- `node_modules/pkg/index.js` is ignored
- `__pycache__/mod.pyc` is ignored
- `.claude/settings.json` is ignored

**Assertion pseudocode:**
```
spec = load_ignore_spec(project_root)
for path in DEFAULT_PATHS:
    ASSERT spec.is_ignored(path) == True
```

### TS-106-5: Default exclusions cannot be negated

**Requirement:** 106-REQ-2.E1
**Type:** unit
**Description:** Verify that negation patterns in `.night-shift` cannot
un-exclude default exclusion paths.

**Preconditions:**
- `.night-shift` containing: `!.agent-fox/config.toml\n!.git/HEAD`

**Input:**
- `project_root` pointing to the temporary directory

**Expected:**
- `.agent-fox/config.toml` is still ignored
- `.git/HEAD` is still ignored

**Assertion pseudocode:**
```
spec = load_ignore_spec(project_root)
ASSERT spec.is_ignored(".agent-fox/config.toml") == True
ASSERT spec.is_ignored(".git/HEAD") == True
```

### TS-106-6: Filter findings removes ignored affected_files

**Requirement:** 106-REQ-3.2
**Type:** unit
**Description:** Verify that `filter_findings` removes ignored file entries
and drops findings that become empty.

**Preconditions:**
- Ignore spec that excludes `vendor/**`
- Finding A with `affected_files=["vendor/lib.py", "src/main.py"]`
- Finding B with `affected_files=["vendor/util.py"]`
- Finding C with `affected_files=["src/app.py"]`

**Input:**
- `findings = [A, B, C]`, `spec` as above

**Expected:**
- Finding A is preserved with `affected_files=["src/main.py"]`
- Finding B is dropped (all files ignored)
- Finding C is preserved unchanged

**Assertion pseudocode:**
```
result = filter_findings([A, B, C], spec)
ASSERT len(result) == 2
ASSERT result[0].affected_files == ["src/main.py"]
ASSERT result[1].affected_files == ["src/app.py"]
```

### TS-106-7: Findings with empty affected_files are preserved

**Requirement:** 106-REQ-3.2
**Type:** unit
**Description:** Verify that findings with no affected_files are never
dropped by filtering.

**Preconditions:**
- Ignore spec that excludes `vendor/**`
- Finding with `affected_files=[]`

**Input:**
- `findings = [finding_no_files]`, `spec` as above

**Expected:**
- The finding is preserved unchanged

**Assertion pseudocode:**
```
result = filter_findings([finding_no_files], spec)
ASSERT len(result) == 1
ASSERT result[0].affected_files == []
```

### TS-106-8: Additive with .gitignore

**Requirement:** 106-REQ-3.3
**Type:** unit
**Description:** Verify that `.gitignore` patterns are also applied when
both files exist.

**Preconditions:**
- `.gitignore` containing `*.pyc`
- `.night-shift` containing `docs/internal/**`

**Input:**
- `project_root` with both files

**Expected:**
- `spec.is_ignored("mod.pyc")` returns `True` (from .gitignore)
- `spec.is_ignored("docs/internal/notes.md")` returns `True` (from .night-shift)
- `spec.is_ignored("src/main.py")` returns `False`

**Assertion pseudocode:**
```
spec = load_ignore_spec(project_root)
ASSERT spec.is_ignored("mod.pyc") == True
ASSERT spec.is_ignored("docs/internal/notes.md") == True
ASSERT spec.is_ignored("src/main.py") == False
```

### TS-106-9: Init creates `.night-shift` file

**Requirement:** 106-REQ-4.1, 106-REQ-4.2
**Type:** unit
**Description:** Verify that `_ensure_nightshift_ignore` creates a seed file
with the correct content.

**Preconditions:**
- A temporary directory with no `.night-shift` file

**Input:**
- `project_root` pointing to the temporary directory

**Expected:**
- `.night-shift` file is created
- File contains a comment header explaining its purpose
- File contains commented-out default exclusion patterns
- Function returns `"created"`

**Assertion pseudocode:**
```
result = _ensure_nightshift_ignore(project_root)
ASSERT result == "created"
path = project_root / ".night-shift"
ASSERT path.exists()
content = path.read_text()
ASSERT "night-shift" in content
ASSERT ".agent-fox" in content
```

### TS-106-10: Init skips existing `.night-shift` file

**Requirement:** 106-REQ-4.E1
**Type:** unit
**Description:** Verify that init does not overwrite an existing file.

**Preconditions:**
- A temporary directory with a `.night-shift` containing `my-custom-pattern`

**Input:**
- `project_root` pointing to the temporary directory

**Expected:**
- Function returns `"skipped"`
- File content is unchanged

**Assertion pseudocode:**
```
original = (project_root / ".night-shift").read_text()
result = _ensure_nightshift_ignore(project_root)
ASSERT result == "skipped"
ASSERT (project_root / ".night-shift").read_text() == original
```

### TS-106-11: InitResult includes nightshift_ignore status

**Requirement:** 106-REQ-4.4
**Type:** unit
**Description:** Verify that `InitResult` has the `nightshift_ignore` field.

**Preconditions:**
- None

**Input:**
- `InitResult(status="ok", agents_md="created", nightshift_ignore="created")`

**Expected:**
- `result.nightshift_ignore == "created"`

**Assertion pseudocode:**
```
result = InitResult(status="ok", agents_md="created", nightshift_ignore="created")
ASSERT result.nightshift_ignore == "created"
```

### TS-106-12: pathspec is in project dependencies

**Requirement:** 106-REQ-5.1
**Type:** unit
**Description:** Verify that `pathspec` is listed as a project dependency.

**Preconditions:**
- pyproject.toml exists

**Input:**
- Read pyproject.toml

**Expected:**
- `pathspec>=0.12` appears in `[project] dependencies`

**Assertion pseudocode:**
```
content = read_file("pyproject.toml")
ASSERT "pathspec>=0.12" in content
```

### TS-106-13: Gitwildmatch patterns work correctly

**Requirement:** 106-REQ-6.1
**Type:** unit
**Description:** Verify that gitwildmatch patterns (wildcards, double-star,
character classes) are supported.

**Preconditions:**
- `.night-shift` containing:
  ```
  *.log
  build/**/output.bin
  test[0-9].py
  ```

**Input:**
- Various file paths

**Expected:**
- `spec.is_ignored("error.log")` → `True`
- `spec.is_ignored("build/release/output.bin")` → `True`
- `spec.is_ignored("test3.py")` → `True`
- `spec.is_ignored("test.py")` → `False`
- `spec.is_ignored("src/main.py")` → `False`

**Assertion pseudocode:**
```
spec = load_ignore_spec(project_root)
ASSERT spec.is_ignored("error.log") == True
ASSERT spec.is_ignored("build/release/output.bin") == True
ASSERT spec.is_ignored("test3.py") == True
ASSERT spec.is_ignored("test.py") == False
```

### TS-106-14: POSIX relative paths used for matching

**Requirement:** 106-REQ-6.2
**Type:** unit
**Description:** Verify that paths are matched as POSIX-relative from root.

**Preconditions:**
- `.night-shift` containing `src/generated/**`

**Input:**
- Path `"src/generated/model.py"` (POSIX)

**Expected:**
- `spec.is_ignored("src/generated/model.py")` → `True`
- `spec.is_ignored("src/main.py")` → `False`

**Assertion pseudocode:**
```
spec = load_ignore_spec(project_root)
ASSERT spec.is_ignored("src/generated/model.py") == True
ASSERT spec.is_ignored("src/main.py") == False
```

## Edge Case Tests

### TS-106-E1: Unreadable `.night-shift` file

**Requirement:** 106-REQ-1.E1
**Type:** unit
**Description:** Verify graceful handling when `.night-shift` cannot be read.

**Preconditions:**
- `.night-shift` file exists but has no read permission (chmod 000)

**Input:**
- `project_root` pointing to the directory

**Expected:**
- Returns a valid `NightShiftIgnoreSpec` (defaults-only)
- A warning is logged
- Default exclusions still apply

**Assertion pseudocode:**
```
spec = load_ignore_spec(project_root)
ASSERT spec.is_ignored(".agent-fox/state.jsonl") == True
ASSERT spec.is_ignored("src/main.py") == False
# Verify warning was logged
```

### TS-106-E2: Empty `.night-shift` file

**Requirement:** 106-REQ-1.E2
**Type:** unit
**Description:** Verify that an empty file is handled correctly.

**Preconditions:**
- `.night-shift` file exists but is empty (0 bytes)

**Input:**
- `project_root` pointing to the directory

**Expected:**
- Returns a valid `NightShiftIgnoreSpec` (defaults-only)
- Default exclusions still apply

**Assertion pseudocode:**
```
spec = load_ignore_spec(project_root)
ASSERT spec.is_ignored(".agent-fox/foo") == True
ASSERT spec.is_ignored("src/main.py") == False
```

### TS-106-E3: Init handles permission error

**Requirement:** 106-REQ-4.E2
**Type:** unit
**Description:** Verify init does not fail when file cannot be created.

**Preconditions:**
- A read-only directory

**Input:**
- `project_root` pointing to the read-only directory

**Expected:**
- Returns `"skipped"`
- A warning is logged
- No exception raised

**Assertion pseudocode:**
```
result = _ensure_nightshift_ignore(readonly_dir)
ASSERT result == "skipped"
```

### TS-106-E4: HuntScanner.run works when ignore spec loading fails

**Requirement:** 106-REQ-3.E1
**Type:** unit
**Description:** Verify that `HuntScanner.run()` still produces findings when
ignore spec loading encounters an unexpected error.

**Preconditions:**
- `load_ignore_spec` patched to raise RuntimeError

**Input:**
- `HuntScanner.run(project_root)`

**Expected:**
- Findings are returned unfiltered
- A warning is logged

**Assertion pseudocode:**
```
with patch("load_ignore_spec", side_effect=RuntimeError):
    findings = await scanner.run(project_root)
ASSERT len(findings) > 0  # not filtered away
```

## Property Test Cases

### TS-106-P1: Default exclusions always hold

**Property:** Property 1 from design.md
**Validates:** 106-REQ-2.1, 106-REQ-2.E1
**Type:** property
**Description:** For any set of user patterns, default exclusion paths are
always ignored.

**For any:** `patterns: list[str]` generated from `st.lists(st.text(
alphabet=st.characters(whitelist_categories=("L", "N", "P")), min_size=1))`

**Invariant:** For every default exclusion path, `spec.is_ignored(path)` is True.

**Assertion pseudocode:**
```
FOR ANY patterns IN strategy:
    write ".night-shift" with patterns
    spec = load_ignore_spec(project_root)
    for default_path in DEFAULT_TEST_PATHS:
        ASSERT spec.is_ignored(default_path) == True
```

### TS-106-P2: filter_findings never adds findings

**Property:** Property 4 from design.md
**Validates:** 106-REQ-3.2
**Type:** property
**Description:** Filtering can only remove or shrink findings, never add them.

**For any:** `findings: list[Finding]` and `patterns: list[str]`

**Invariant:** `len(filter_findings(findings, spec)) <= len(findings)`

**Assertion pseudocode:**
```
FOR ANY findings, patterns IN strategy:
    spec = build_spec(patterns)
    result = filter_findings(findings, spec)
    ASSERT len(result) <= len(findings)
```

### TS-106-P3: load_ignore_spec never raises

**Property:** Property 3 from design.md
**Validates:** 106-REQ-1.E1, 106-REQ-1.E2, 106-REQ-1.4
**Type:** property
**Description:** `load_ignore_spec` returns a valid spec for any file state.

**For any:** `file_content: str | None` (None = missing file)

**Invariant:** `load_ignore_spec(project_root)` returns a `NightShiftIgnoreSpec`
without raising.

**Assertion pseudocode:**
```
FOR ANY file_content IN st.one_of(st.none(), st.text()):
    if file_content is not None:
        write ".night-shift" with file_content
    spec = load_ignore_spec(project_root)
    ASSERT isinstance(spec, NightShiftIgnoreSpec)
```

### TS-106-P4: Findings with empty affected_files survive filtering

**Property:** Property 4 from design.md
**Validates:** 106-REQ-3.2
**Type:** property
**Description:** Findings with no `affected_files` are never removed by filtering.

**For any:** `patterns: list[str]`, `n_findings: int` (all with empty affected_files)

**Invariant:** All findings are preserved.

**Assertion pseudocode:**
```
FOR ANY patterns, n IN strategy:
    findings = [Finding(affected_files=[]) for _ in range(n)]
    spec = build_spec(patterns)
    result = filter_findings(findings, spec)
    ASSERT len(result) == n
```

### TS-106-P5: Init idempotency

**Property:** Property 6 from design.md
**Validates:** 106-REQ-4.1, 106-REQ-4.E1
**Type:** property
**Description:** Multiple calls to `_ensure_nightshift_ignore` are idempotent.

**For any:** `n_calls: int` (2..5)

**Invariant:** File is created on first call, content unchanged on subsequent calls.

**Assertion pseudocode:**
```
FOR ANY n IN st.integers(min_value=2, max_value=5):
    first_result = _ensure_nightshift_ignore(project_root)
    first_content = read_file(".night-shift")
    for _ in range(n - 1):
        result = _ensure_nightshift_ignore(project_root)
        ASSERT result == "skipped"
        ASSERT read_file(".night-shift") == first_content
```

## Integration Smoke Tests

### TS-106-SMOKE-1: Hunt scan respects `.night-shift` file

**Execution Path:** Path 1 from design.md
**Description:** End-to-end test that a hunt scan filters findings based on
a `.night-shift` file on disk.

**Setup:**
- Create a temporary project directory with a `.night-shift` file containing
  `vendor/**`
- Create a mock hunt category that produces findings with `affected_files`
  pointing to both `vendor/` and `src/` paths
- Real `HuntScanner`, real `load_ignore_spec`, real `filter_findings`
- Mock: only the hunt category's `detect()` (to control findings)

**Trigger:**
- `await scanner.run(project_root)`

**Expected side effects:**
- Returned findings do not contain any `vendor/` paths in `affected_files`
- Findings with only `vendor/` files are dropped entirely
- Findings with `src/` files are preserved

**Must NOT satisfy with:**
- Mocked `load_ignore_spec` (must read real file)
- Mocked `filter_findings` (must use real implementation)

**Assertion pseudocode:**
```
scanner = HuntScanner(registry_with_mock_category, config)
findings = await scanner.run(project_root)
for f in findings:
    for path in f.affected_files:
        ASSERT not path.startswith("vendor/")
```

### TS-106-SMOKE-2: Init creates `.night-shift` and it is loadable

**Execution Path:** Path 2 from design.md
**Description:** End-to-end test that `init_project` creates a `.night-shift`
file that can be loaded by `load_ignore_spec`.

**Setup:**
- Create a temporary directory with `git init`
- Create `.agent-fox/config.toml` to simulate fresh init

**Trigger:**
- `init_project(project_root)`
- `load_ignore_spec(project_root)`

**Expected side effects:**
- `.night-shift` file exists
- `load_ignore_spec` returns a valid spec
- Default exclusions are applied

**Must NOT satisfy with:**
- Mocked `_ensure_nightshift_ignore` (must use real implementation)
- Mocked `load_ignore_spec` (must parse real file)

**Assertion pseudocode:**
```
result = init_project(project_root)
ASSERT result.nightshift_ignore == "created"
spec = load_ignore_spec(project_root)
ASSERT spec.is_ignored(".agent-fox/state.jsonl") == True
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 106-REQ-1.1 | TS-106-1 | unit |
| 106-REQ-1.2 | TS-106-1 | unit |
| 106-REQ-1.3 | TS-106-2 | unit |
| 106-REQ-1.4 | TS-106-3 | unit |
| 106-REQ-1.E1 | TS-106-E1 | unit |
| 106-REQ-1.E2 | TS-106-E2 | unit |
| 106-REQ-2.1 | TS-106-4 | unit |
| 106-REQ-2.E1 | TS-106-5 | unit |
| 106-REQ-3.1 | TS-106-SMOKE-1 | integration |
| 106-REQ-3.2 | TS-106-6, TS-106-7 | unit |
| 106-REQ-3.3 | TS-106-8 | unit |
| 106-REQ-3.E1 | TS-106-E4 | unit |
| 106-REQ-4.1 | TS-106-9 | unit |
| 106-REQ-4.2 | TS-106-9 | unit |
| 106-REQ-4.4 | TS-106-11 | unit |
| 106-REQ-4.E1 | TS-106-10 | unit |
| 106-REQ-4.E2 | TS-106-E3 | unit |
| 106-REQ-5.1 | TS-106-12 | unit |
| 106-REQ-6.1 | TS-106-13 | unit |
| 106-REQ-6.2 | TS-106-14 | unit |
| 106-REQ-6.3 | TS-106-1 | unit |
| Property 1 | TS-106-P1 | property |
| Property 2 | TS-106-P2 | property |
| Property 3 | TS-106-P3 | property |
| Property 4 | TS-106-P4 | property |
| Property 5 | TS-106-14 | unit |
| Property 6 | TS-106-P5 | property |
| Path 1 | TS-106-SMOKE-1 | integration |
| Path 2 | TS-106-SMOKE-2 | integration |
