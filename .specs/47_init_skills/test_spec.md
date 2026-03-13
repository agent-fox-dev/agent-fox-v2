# Test Specification: Install Claude Code Skills via `init --skills`

## Overview

Test cases map to requirements and correctness properties from the design
document. Unit tests validate `_install_skills()` in isolation. Property tests
validate bundled template invariants. Integration tests validate the full CLI
flow.

## Test Cases

### TS-47-1: Skills installed to correct paths

**Requirement:** 47-REQ-2.1
**Type:** integration
**Description:** Verify that `init --skills` creates SKILL.md files in
`.claude/skills/{name}/` for each bundled template.

**Preconditions:**
- Fresh git repository (no `.claude/skills/` directory).

**Input:**
- `agent-fox init --skills`

**Expected:**
- For each bundled template name (e.g., `af-spec`, `af-fix`), the file
  `.claude/skills/{name}/SKILL.md` exists.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["init", "--skills"])
ASSERT result.exit_code == 0
FOR EACH name IN bundled_skill_names:
    ASSERT (project_root / ".claude" / "skills" / name / "SKILL.md").exists()
```

### TS-47-2: No skills without flag

**Requirement:** 47-REQ-2.2
**Type:** integration
**Description:** Verify that `init` without `--skills` does not create any
skill files.

**Preconditions:**
- Fresh git repository.

**Input:**
- `agent-fox init`

**Expected:**
- `.claude/skills/` directory does not exist or is empty.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["init"])
ASSERT result.exit_code == 0
skills_dir = project_root / ".claude" / "skills"
ASSERT NOT skills_dir.exists() OR len(list(skills_dir.iterdir())) == 0
```

### TS-47-3: Skills overwrite on re-run

**Requirement:** 47-REQ-2.4
**Type:** integration
**Description:** Verify that re-running `init --skills` overwrites existing
skill files with latest versions.

**Preconditions:**
- Already-initialized project with skills installed.
- One skill file modified to contain different content.

**Input:**
- `agent-fox init --skills` (second invocation)

**Expected:**
- The modified skill file is overwritten with the bundled version.

**Assertion pseudocode:**
```
cli_runner.invoke(main, ["init", "--skills"])
skill_path = project_root / ".claude" / "skills" / "af-spec" / "SKILL.md"
skill_path.write_text("modified content")
cli_runner.invoke(main, ["init", "--skills"])
ASSERT skill_path.read_text() != "modified content"
ASSERT skill_path.read_text() == bundled_af_spec_content
```

### TS-47-4: Output reports skill count

**Requirement:** 47-REQ-2.5
**Type:** integration
**Description:** Verify that human-readable output mentions the number of
skills installed.

**Preconditions:**
- Fresh git repository.

**Input:**
- `agent-fox init --skills`

**Expected:**
- Output contains the number of skills installed (e.g., "Installed 6 skills").

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["init", "--skills"])
ASSERT "installed" in result.output.lower()
ASSERT str(expected_skill_count) in result.output
```

### TS-47-5: JSON output includes skills_installed

**Requirement:** 47-REQ-3.1
**Type:** integration
**Description:** Verify that JSON output includes `skills_installed` field
when `--skills` is provided.

**Preconditions:**
- Fresh git repository.

**Input:**
- `agent-fox init --skills --json`

**Expected:**
- JSON output contains `"skills_installed"` key with an integer value matching
  the number of bundled skills.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["--json", "init", "--skills"])
data = json.loads(result.output)
ASSERT "skills_installed" in data
ASSERT data["skills_installed"] == expected_skill_count
```

### TS-47-6: JSON output excludes skills_installed without flag

**Requirement:** 47-REQ-3.2
**Type:** integration
**Description:** Verify that JSON output does not include `skills_installed`
when `--skills` is not provided.

**Preconditions:**
- Fresh git repository.

**Input:**
- `agent-fox init --json`

**Expected:**
- JSON output does not contain `"skills_installed"` key.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["--json", "init"])
data = json.loads(result.output)
ASSERT "skills_installed" NOT IN data
```

### TS-47-7: Skills work on re-init

**Requirement:** 47-REQ-4.2
**Type:** integration
**Description:** Verify that `--skills` works when re-initializing an
already-initialized project.

**Preconditions:**
- Already-initialized project (`.agent-fox/config.toml` exists).

**Input:**
- `agent-fox init --skills`

**Expected:**
- Exit code 0, skills installed, normal re-init behavior preserved.

**Assertion pseudocode:**
```
cli_runner.invoke(main, ["init"])  # first init, no skills
result = cli_runner.invoke(main, ["init", "--skills"])  # re-init with skills
ASSERT result.exit_code == 0
ASSERT (project_root / ".claude" / "skills" / "af-spec" / "SKILL.md").exists()
ASSERT "already initialized" in result.output.lower()
```

## Property Test Cases

### TS-47-P1: Bundled templates have valid frontmatter

**Property:** Property 1 from design.md
**Validates:** 47-REQ-1.1, 47-REQ-1.2, 47-REQ-1.3
**Type:** property
**Description:** Every bundled skill template contains YAML frontmatter with
a `name` field matching its filename.

**For any:** bundled skill template file in `_templates/skills/`
**Invariant:** The file starts with `---`, contains a `name:` field matching
the filename, contains a `description:` field, and has a closing `---`.

**Assertion pseudocode:**
```
FOR ANY template_path IN _SKILLS_DIR.iterdir():
    content = template_path.read_text()
    ASSERT content.startswith("---")
    frontmatter = parse_yaml_frontmatter(content)
    ASSERT "name" IN frontmatter
    ASSERT frontmatter["name"] == template_path.name
    ASSERT "description" IN frontmatter
```

### TS-47-P2: Installation bijection

**Property:** Property 2 from design.md
**Validates:** 47-REQ-2.1, 47-REQ-2.3
**Type:** property
**Description:** `_install_skills()` produces exactly one SKILL.md per
template, with identical content.

**For any:** project root directory
**Invariant:** The set of installed skill names equals the set of template
filenames, and each installed file is byte-identical to its source.

**Assertion pseudocode:**
```
count = _install_skills(project_root)
installed = {d.name for d in (project_root / ".claude" / "skills").iterdir()}
templates = {f.name for f in _SKILLS_DIR.iterdir() if not f.name.startswith(".")}
ASSERT installed == templates
ASSERT count == len(templates)
FOR EACH name IN templates:
    ASSERT (project_root / ".claude" / "skills" / name / "SKILL.md").read_bytes() == (_SKILLS_DIR / name).read_bytes()
```

### TS-47-P3: Count accuracy

**Property:** Property 5 from design.md
**Validates:** 47-REQ-2.5, 47-REQ-3.1
**Type:** property
**Description:** The integer returned by `_install_skills()` equals the number
of SKILL.md files written.

**For any:** invocation of `_install_skills()`
**Invariant:** Return value equals the count of SKILL.md files under
`.claude/skills/`.

**Assertion pseudocode:**
```
count = _install_skills(project_root)
skills_dir = project_root / ".claude" / "skills"
written = sum(1 for d in skills_dir.iterdir() if (d / "SKILL.md").exists())
ASSERT count == written
```

## Edge Case Tests

### TS-47-E1: Unreadable template skipped

**Requirement:** 47-REQ-1.E1
**Type:** unit
**Description:** An unreadable template file is skipped with a warning.

**Preconditions:**
- `_SKILLS_DIR` contains a file that raises an exception on read.

**Input:**
- Call `_install_skills(project_root)` with a monkeypatched `_SKILLS_DIR`
  containing an unreadable file alongside valid ones.

**Expected:**
- Valid skills are installed; unreadable one is skipped.
- Return count excludes the skipped skill.

**Assertion pseudocode:**
```
# Monkeypatch _SKILLS_DIR to a tmp dir with one valid and one unreadable file
count = _install_skills(project_root)
ASSERT count == number_of_valid_files
ASSERT unreadable_skill_not_installed
```

### TS-47-E2: Empty templates directory

**Requirement:** 47-REQ-2.E1
**Type:** unit
**Description:** An empty or missing `_templates/skills/` directory results in
zero skills installed.

**Preconditions:**
- `_SKILLS_DIR` points to an empty directory.

**Input:**
- Call `_install_skills(project_root)`.

**Expected:**
- Returns 0, no error raised.

**Assertion pseudocode:**
```
# Monkeypatch _SKILLS_DIR to an empty directory
count = _install_skills(project_root)
ASSERT count == 0
```

### TS-47-E3: Permission error creating skills directory

**Requirement:** 47-REQ-2.E2
**Type:** unit
**Description:** If `.claude/skills/` cannot be created, the error is logged
and init continues.

**Preconditions:**
- `.claude/` directory exists but is not writable.

**Input:**
- Call `_install_skills(project_root)` where directory creation fails.

**Expected:**
- Returns 0 (or raises a handled error), does not crash init.

**Assertion pseudocode:**
```
# Make .claude/ read-only
count = _install_skills(project_root)
ASSERT count == 0
# init continues without error
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 47-REQ-1.1 | TS-47-P1 | property |
| 47-REQ-1.2 | TS-47-P1 | property |
| 47-REQ-1.3 | TS-47-P1 | property |
| 47-REQ-1.E1 | TS-47-E1 | unit |
| 47-REQ-2.1 | TS-47-1, TS-47-P2 | integration, property |
| 47-REQ-2.2 | TS-47-2 | integration |
| 47-REQ-2.3 | TS-47-P2 | property |
| 47-REQ-2.4 | TS-47-3 | integration |
| 47-REQ-2.5 | TS-47-4, TS-47-P3 | integration, property |
| 47-REQ-2.E1 | TS-47-E2 | unit |
| 47-REQ-2.E2 | TS-47-E3 | unit |
| 47-REQ-3.1 | TS-47-5 | integration |
| 47-REQ-3.2 | TS-47-6 | integration |
| 47-REQ-4.1 | TS-47-1 | integration |
| 47-REQ-4.2 | TS-47-7 | integration |
