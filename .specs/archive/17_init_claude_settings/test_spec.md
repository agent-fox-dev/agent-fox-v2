# Test Specification: Init Claude Settings

## Overview

Test cases verify that `_ensure_claude_settings()` correctly creates, merges,
and preserves `.claude/settings.local.json`. Tests map directly to
requirements (17-REQ-*) and correctness properties from the design document.
All tests use filesystem fixtures (temporary directories); no mocking of JSON
parsing is needed.

## Test Cases

### TS-17-1: Create settings file when absent

**Requirement:** 17-REQ-1.1
**Type:** unit
**Description:** When `.claude/settings.local.json` does not exist, the
function creates it with the canonical permission list.

**Preconditions:**
- Project root directory exists.
- `.claude/` directory may or may not exist.

**Input:**
- `project_root` pointing to a temporary directory with no `.claude/` subdirectory.

**Expected:**
- `.claude/settings.local.json` exists after the call.
- File content is valid JSON.
- `permissions.allow` contains every entry in `CANONICAL_PERMISSIONS`.

**Assertion pseudocode:**
```
_ensure_claude_settings(project_root)
content = json.loads(read(project_root / ".claude/settings.local.json"))
ASSERT set(CANONICAL_PERMISSIONS).issubset(set(content["permissions"]["allow"]))
```

---

### TS-17-2: Create .claude directory when absent

**Requirement:** 17-REQ-1.2
**Type:** unit
**Description:** When the `.claude/` directory does not exist, the function
creates it before writing the settings file.

**Preconditions:**
- Project root exists with no `.claude/` subdirectory.

**Input:**
- `project_root` with no `.claude/` directory.

**Expected:**
- `.claude/` directory exists after the call.
- `.claude/settings.local.json` exists after the call.

**Assertion pseudocode:**
```
ASSERT NOT (project_root / ".claude").exists()
_ensure_claude_settings(project_root)
ASSERT (project_root / ".claude").is_dir()
ASSERT (project_root / ".claude" / "settings.local.json").exists()
```

---

### TS-17-3: Merge missing entries into existing file

**Requirement:** 17-REQ-2.1
**Type:** unit
**Description:** When the file exists with some but not all canonical entries,
missing entries are added.

**Preconditions:**
- `.claude/settings.local.json` exists with a subset of canonical entries.

**Input:**
- File containing `{"permissions": {"allow": ["Read", "Write"]}}`.

**Expected:**
- After the call, `permissions.allow` contains all canonical entries.
- `"Read"` and `"Write"` are still present.

**Assertion pseudocode:**
```
write(settings_path, '{"permissions": {"allow": ["Read", "Write"]}}')
_ensure_claude_settings(project_root)
content = json.loads(read(settings_path))
allow = content["permissions"]["allow"]
ASSERT set(CANONICAL_PERMISSIONS).issubset(set(allow))
ASSERT "Read" in allow
ASSERT "Write" in allow
```

---

### TS-17-4: Preserve user-added entries

**Requirement:** 17-REQ-2.2
**Type:** unit
**Description:** User-added entries not in the canonical list are preserved
during merge.

**Preconditions:**
- `.claude/settings.local.json` exists with canonical entries plus a custom entry.

**Input:**
- File containing all canonical entries plus `"Bash(agent-fox:*)"`.

**Expected:**
- After the call, `"Bash(agent-fox:*)"` is still present in `permissions.allow`.

**Assertion pseudocode:**
```
existing = {"permissions": {"allow": CANONICAL_PERMISSIONS + ["Bash(agent-fox:*)"]}}
write(settings_path, json.dumps(existing))
_ensure_claude_settings(project_root)
content = json.loads(read(settings_path))
ASSERT "Bash(agent-fox:*)" in content["permissions"]["allow"]
```

---

### TS-17-5: Preserve ordering of existing entries

**Requirement:** 17-REQ-2.3
**Type:** unit
**Description:** Existing entries maintain their relative order; new entries
are appended after them.

**Preconditions:**
- `.claude/settings.local.json` exists with entries in a specific order.

**Input:**
- File containing `{"permissions": {"allow": ["Write", "Bash(agent-fox:*)", "Read"]}}`.

**Expected:**
- After the call, `"Write"` appears before `"Bash(agent-fox:*)"` which appears
  before `"Read"` in the result. New canonical entries appear after `"Read"`.

**Assertion pseudocode:**
```
write(settings_path, '{"permissions": {"allow": ["Write", "Bash(agent-fox:*)", "Read"]}}')
_ensure_claude_settings(project_root)
content = json.loads(read(settings_path))
allow = content["permissions"]["allow"]
idx_write = allow.index("Write")
idx_custom = allow.index("Bash(agent-fox:*)")
idx_read = allow.index("Read")
ASSERT idx_write < idx_custom < idx_read
# New entries start after existing ones
first_new = next(e for e in allow if e not in ["Write", "Bash(agent-fox:*)", "Read"])
ASSERT allow.index(first_new) > idx_read
```

---

## Edge Case Tests

### TS-17-E1: No-op when all canonical entries present

**Requirement:** 17-REQ-1.E1
**Type:** unit
**Description:** When the file already contains all canonical entries, the
file is unchanged.

**Preconditions:**
- `.claude/settings.local.json` exists with all canonical entries.

**Input:**
- File containing exactly the canonical permission list.

**Expected:**
- File content is identical before and after the call.

**Assertion pseudocode:**
```
original = {"permissions": {"allow": list(CANONICAL_PERMISSIONS)}}
write(settings_path, json.dumps(original, indent=2))
before = read(settings_path)
_ensure_claude_settings(project_root)
after = read(settings_path)
ASSERT before == after
```

---

### TS-17-E2: Invalid JSON logs warning and skips

**Requirement:** 17-REQ-2.E1
**Type:** unit
**Description:** When the file contains invalid JSON, a warning is logged and
the file is left unchanged.

**Preconditions:**
- `.claude/settings.local.json` exists with invalid JSON content.

**Input:**
- File containing `"not valid json {{{}"`.

**Expected:**
- A warning is logged mentioning the file and the parse error.
- The file content is unchanged after the call.
- The init command does not fail (no exception raised).

**Assertion pseudocode:**
```
write(settings_path, "not valid json {{{}")
_ensure_claude_settings(project_root)  # should not raise
after = read(settings_path)
ASSERT after == "not valid json {{{}"
ASSERT warning_logged("settings.local.json")
```

---

### TS-17-E3: Missing permissions structure is created

**Requirement:** 17-REQ-2.E2
**Type:** unit
**Description:** When the file has valid JSON but no `permissions` or
`permissions.allow` key, the missing structure is created.

**Preconditions:**
- `.claude/settings.local.json` exists with valid JSON but no `permissions` key.

**Input:**
- File containing `{"other_key": "value"}`.

**Expected:**
- After the call, `permissions.allow` exists and contains all canonical entries.
- `other_key` is preserved.

**Assertion pseudocode:**
```
write(settings_path, '{"other_key": "value"}')
_ensure_claude_settings(project_root)
content = json.loads(read(settings_path))
ASSERT content["other_key"] == "value"
ASSERT set(CANONICAL_PERMISSIONS).issubset(set(content["permissions"]["allow"]))
```

---

### TS-17-E4: permissions.allow not a list logs warning and skips

**Requirement:** 17-REQ-2.E3
**Type:** unit
**Description:** When `permissions.allow` is not a list, a warning is logged
and the file is left unchanged.

**Preconditions:**
- `.claude/settings.local.json` exists with `permissions.allow` set to a string.

**Input:**
- File containing `{"permissions": {"allow": "not-a-list"}}`.

**Expected:**
- A warning is logged.
- The file content is unchanged.

**Assertion pseudocode:**
```
original = '{"permissions": {"allow": "not-a-list"}}'
write(settings_path, original)
_ensure_claude_settings(project_root)
after = read(settings_path)
ASSERT after == original
ASSERT warning_logged()
```

---

## Property Test Cases

### TS-17-P1: Canonical coverage

**Property:** Property 1 from design.md
**Validates:** 17-REQ-1.1, 17-REQ-1.3, 17-REQ-2.1
**Type:** property
**Description:** After running, all canonical entries are present in the result.

**For any:** List of arbitrary strings as initial `permissions.allow` entries
(0 to 50 entries, including duplicates of canonical entries and random strings).
**Invariant:** After `_ensure_claude_settings()`, the resulting
`permissions.allow` is a superset of `CANONICAL_PERMISSIONS`.

**Assertion pseudocode:**
```
FOR ANY initial_entries IN lists(text(), max_size=50):
    write(settings_path, json.dumps({"permissions": {"allow": initial_entries}}))
    _ensure_claude_settings(project_root)
    result = json.loads(read(settings_path))["permissions"]["allow"]
    ASSERT set(CANONICAL_PERMISSIONS).issubset(set(result))
```

---

### TS-17-P2: User entry preservation

**Property:** Property 2 from design.md
**Validates:** 17-REQ-2.2
**Type:** property
**Description:** All entries present before the call are still present after.

**For any:** List of arbitrary strings as initial `permissions.allow` entries.
**Invariant:** Every entry in the initial list appears in the result.

**Assertion pseudocode:**
```
FOR ANY initial_entries IN lists(text(min_size=1), max_size=50):
    write(settings_path, json.dumps({"permissions": {"allow": initial_entries}}))
    _ensure_claude_settings(project_root)
    result = json.loads(read(settings_path))["permissions"]["allow"]
    ASSERT set(initial_entries).issubset(set(result))
```

---

### TS-17-P3: Idempotency

**Property:** Property 3 from design.md
**Validates:** 17-REQ-1.E1
**Type:** property
**Description:** Running the function twice produces the same result as once.

**For any:** List of arbitrary strings as initial `permissions.allow` entries.
**Invariant:** File content after two calls equals file content after one call.

**Assertion pseudocode:**
```
FOR ANY initial_entries IN lists(text(), max_size=50):
    write(settings_path, json.dumps({"permissions": {"allow": initial_entries}}))
    _ensure_claude_settings(project_root)
    after_first = read(settings_path)
    _ensure_claude_settings(project_root)
    after_second = read(settings_path)
    ASSERT after_first == after_second
```

---

### TS-17-P4: Order preservation

**Property:** Property 4 from design.md
**Validates:** 17-REQ-2.3
**Type:** property
**Description:** Existing entries maintain their relative order in the result.

**For any:** List of unique arbitrary strings as initial `permissions.allow`
entries (to avoid ambiguity in order checking).
**Invariant:** For every pair of entries (a, b) where a appears before b in
the original list, a also appears before b in the result.

**Assertion pseudocode:**
```
FOR ANY initial_entries IN lists(text(min_size=1), unique=True, max_size=30):
    write(settings_path, json.dumps({"permissions": {"allow": initial_entries}}))
    _ensure_claude_settings(project_root)
    result = json.loads(read(settings_path))["permissions"]["allow"]
    FOR i, j WHERE i < j AND initial_entries[i] in result AND initial_entries[j] in result:
        ASSERT result.index(initial_entries[i]) < result.index(initial_entries[j])
```

---

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 17-REQ-1.1 | TS-17-1 | unit |
| 17-REQ-1.2 | TS-17-2 | unit |
| 17-REQ-1.3 | TS-17-1 | unit |
| 17-REQ-2.1 | TS-17-3 | unit |
| 17-REQ-2.2 | TS-17-4 | unit |
| 17-REQ-2.3 | TS-17-5 | unit |
| 17-REQ-1.E1 | TS-17-E1 | unit |
| 17-REQ-2.E1 | TS-17-E2 | unit |
| 17-REQ-2.E2 | TS-17-E3 | unit |
| 17-REQ-2.E3 | TS-17-E4 | unit |
| Property 1 | TS-17-P1 | property |
| Property 2 | TS-17-P2 | property |
| Property 3 | TS-17-P3 | property |
| Property 4 | TS-17-P4 | property |
