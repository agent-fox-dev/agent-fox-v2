# Test Specification: CLI Banner Enhancement

## Overview

Tests verify that the enhanced banner renders fox ASCII art, version + model,
and working directory correctly. Unit tests capture Rich console output via
`StringIO`. Integration tests use Click's `CliRunner`. Property tests use
Hypothesis to fuzz model config values.

## Test Cases

### TS-14-1: Banner Contains Fox ASCII Art

**Requirement:** 14-REQ-1.1
**Type:** unit
**Description:** Verify that `render_banner` output contains all four lines
of the fox ASCII art.

**Preconditions:**
- Default `ThemeConfig` and `ModelConfig`.

**Input:**
- Call `render_banner(theme, model_config)` with defaults.

**Expected:**
- Output contains each line of:
  ```
     /\_/\  _
    / o.o \/ \
   ( > ^ < )  )
    \_^/\_/--'
  ```

**Assertion pseudocode:**
```
output = capture_banner_output(theme, model_config)
FOR EACH line IN FOX_ART.splitlines():
    ASSERT line IN output
```

---

### TS-14-2: Banner Styles Fox Art with Header Role

**Requirement:** 14-REQ-1.2
**Type:** unit
**Description:** Verify that the fox art is rendered using the `header` style
role markup.

**Preconditions:**
- Default `ThemeConfig`.

**Input:**
- Call `render_banner(theme, model_config)`.

**Expected:**
- The console `print` call for fox art uses the `header` role.

**Assertion pseudocode:**
```
output = capture_banner_output(theme, model_config)
ASSERT "[header]" appears in raw markup OR
    verify theme.print was called with role="header" for art lines
```

---

### TS-14-3: Banner Shows Version and Model Line

**Requirement:** 14-REQ-2.1, 14-REQ-2.2
**Type:** unit
**Description:** Verify the version/model line format with resolved model ID.

**Preconditions:**
- Default `ModelConfig` (coding = "ADVANCED" → resolves to `claude-opus-4-6`).

**Input:**
- Call `render_banner(theme, model_config)`.

**Expected:**
- Output contains `agent-fox v0.1.0  model: claude-opus-4-6`.

**Assertion pseudocode:**
```
output = capture_banner_output(theme, default_model_config)
ASSERT f"agent-fox v{__version__}  model: claude-opus-4-6" IN output
```

---

### TS-14-4: Banner Shows Working Directory

**Requirement:** 14-REQ-3.1
**Type:** unit
**Description:** Verify the working directory appears in banner output.

**Preconditions:**
- Known working directory (use monkeypatch on `Path.cwd`).

**Input:**
- Monkeypatch `Path.cwd()` to return `/tmp/test-project`.
- Call `render_banner(theme, model_config)`.

**Expected:**
- Output contains `/tmp/test-project`.

**Assertion pseudocode:**
```
monkeypatch.setattr(Path, "cwd", lambda: Path("/tmp/test-project"))
output = capture_banner_output(theme, model_config)
ASSERT "/tmp/test-project" IN output
```

---

### TS-14-5: Banner Displays on Subcommand Invocation

**Requirement:** 14-REQ-4.1
**Type:** integration
**Description:** Verify the banner appears when a subcommand is invoked.

**Preconditions:**
- CLI is importable, `CliRunner` available.

**Input:**
- Invoke `agent-fox status` via `CliRunner`.

**Expected:**
- Output contains the fox art and version line.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["status"])
ASSERT "agent-fox v" IN result.output
ASSERT "/\\_/\\" IN result.output
```

---

### TS-14-6: Banner Suppressed by Quiet Flag

**Requirement:** 14-REQ-4.2
**Type:** integration
**Description:** Verify `--quiet` suppresses the banner entirely.

**Preconditions:**
- CLI is importable, `CliRunner` available.

**Input:**
- Invoke `agent-fox --quiet` via `CliRunner`.

**Expected:**
- Output does NOT contain fox art or version line.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["--quiet"])
ASSERT "agent-fox v" NOT IN result.output
ASSERT "/\\_/\\" NOT IN result.output
```

---

### TS-14-7: Version/Model Line Styled with Header Role

**Requirement:** 14-REQ-2.3
**Type:** unit
**Description:** Verify the version/model line uses the `header` style role.

**Preconditions:**
- Default `ThemeConfig`.

**Input:**
- Call `render_banner(theme, model_config)`.

**Expected:**
- The version/model line is printed via `theme.header()` or equivalent.

**Assertion pseudocode:**
```
output = capture_banner_output(theme, model_config)
ASSERT version/model line is rendered with header role markup
```

---

### TS-14-8: Working Directory Styled with Muted Role

**Requirement:** 14-REQ-3.2
**Type:** unit
**Description:** Verify the working directory line uses the `muted` style role.

**Preconditions:**
- Default `ThemeConfig`.

**Input:**
- Call `render_banner(theme, model_config)`.

**Expected:**
- The cwd line is printed via `theme.print(..., role="muted")`.

**Assertion pseudocode:**
```
output = capture_raw_markup(theme, model_config)
ASSERT cwd line is rendered with muted role markup
```

## Property Test Cases

### TS-14-P1: Fox Art Always Present

**Property:** Property 1 from design.md
**Validates:** 14-REQ-1.1
**Type:** property
**Description:** The fox art appears in banner output for any valid config.

**For any:** ThemeConfig with valid style strings, ModelConfig with any
coding value.
**Invariant:** Banner output (when quiet=False) always contains all four
lines of `FOX_ART`.

**Assertion pseudocode:**
```
FOR ANY theme_config IN valid_theme_configs, model_config IN model_configs:
    output = capture_banner_output(create_theme(theme_config), model_config)
    FOR EACH line IN FOX_ART.splitlines():
        ASSERT line IN output
```

---

### TS-14-P2: Version Line Always Present

**Property:** Property 2 from design.md
**Validates:** 14-REQ-2.1, 14-REQ-2.2
**Type:** property
**Description:** The version + model line always appears with correct format.

**For any:** ModelConfig where `coding` is a valid tier name or model ID.
**Invariant:** Banner output contains `agent-fox v{__version__}  model: {resolved_id}`.

**Assertion pseudocode:**
```
FOR ANY model_name IN ["SIMPLE", "STANDARD", "ADVANCED", "claude-opus-4-6"]:
    model_config = ModelConfig(coding=model_name)
    output = capture_banner_output(theme, model_config)
    resolved = resolve_model(model_name).model_id
    ASSERT f"agent-fox v{__version__}  model: {resolved}" IN output
```

---

### TS-14-P3: Model Fallback Never Crashes

**Property:** Property 3 from design.md
**Validates:** 14-REQ-2.E1
**Type:** property
**Description:** Banner never raises an exception, even with invalid model names.

**For any:** ModelConfig where `coding` is an arbitrary string (including
gibberish, empty string, special characters).
**Invariant:** `render_banner` completes without exception and output
contains `model:`.

**Assertion pseudocode:**
```
FOR ANY coding_name IN text(min_size=0, max_size=50):
    model_config = ModelConfig(coding=coding_name)
    output = capture_banner_output(theme, model_config)  # no exception
    ASSERT "model:" IN output
```

---

### TS-14-P4: Quiet Produces No Output

**Property:** Property 4 from design.md
**Validates:** 14-REQ-4.2
**Type:** property
**Description:** Quiet mode always produces empty output.

**For any:** Any ThemeConfig and ModelConfig combination.
**Invariant:** `render_banner(..., quiet=True)` produces no output.

**Assertion pseudocode:**
```
FOR ANY theme_config IN valid_theme_configs, model_config IN model_configs:
    output = capture_banner_output(create_theme(theme_config), model_config, quiet=True)
    ASSERT output == ""
```

---

### TS-14-P5: CWD Always Present

**Property:** Property 5 from design.md
**Validates:** 14-REQ-3.1
**Type:** property
**Description:** Working directory always appears in non-quiet output.

**For any:** Any valid config, any working directory path.
**Invariant:** Banner output contains the cwd string.

**Assertion pseudocode:**
```
FOR ANY cwd_path IN ["/tmp/a", "/home/user/project", "/a/b/c/d"]:
    monkeypatch Path.cwd -> Path(cwd_path)
    output = capture_banner_output(theme, model_config)
    ASSERT cwd_path IN output
```

## Edge Case Tests

### TS-14-E1: Model Resolution Failure Fallback

**Requirement:** 14-REQ-2.E1
**Type:** unit
**Description:** Invalid model name falls back to raw config value.

**Preconditions:**
- `ModelConfig` with `coding = "NONEXISTENT"`.

**Input:**
- Call `render_banner(theme, ModelConfig(coding="NONEXISTENT"))`.

**Expected:**
- Output contains `model: NONEXISTENT`.
- No exception raised.

**Assertion pseudocode:**
```
model_config = ModelConfig(coding="NONEXISTENT")
output = capture_banner_output(theme, model_config)
ASSERT "model: NONEXISTENT" IN output
```

---

### TS-14-E2: CWD OSError Fallback

**Requirement:** 14-REQ-3.E1
**Type:** unit
**Description:** If `Path.cwd()` raises `OSError`, display `(unknown)`.

**Preconditions:**
- Monkeypatch `Path.cwd` to raise `OSError`.

**Input:**
- Call `render_banner(theme, model_config)`.

**Expected:**
- Output contains `(unknown)`.
- No exception raised.

**Assertion pseudocode:**
```
monkeypatch.setattr(Path, "cwd", lambda: raise OSError("deleted"))
output = capture_banner_output(theme, model_config)
ASSERT "(unknown)" IN output
```

---

### TS-14-E3: Version Flag Skips Banner

**Requirement:** 14-REQ-4.E1
**Type:** integration
**Description:** `--version` shows only the version string, no banner.

**Preconditions:**
- CLI is importable, `CliRunner` available.

**Input:**
- Invoke `agent-fox --version` via `CliRunner`.

**Expected:**
- Output contains the version string.
- Output does NOT contain fox ASCII art.

**Assertion pseudocode:**
```
result = cli_runner.invoke(main, ["--version"])
ASSERT __version__ IN result.output
ASSERT "/\\_/\\" NOT IN result.output
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 14-REQ-1.1 | TS-14-1 | unit |
| 14-REQ-1.2 | TS-14-2 | unit |
| 14-REQ-2.1 | TS-14-3 | unit |
| 14-REQ-2.2 | TS-14-3 | unit |
| 14-REQ-2.3 | TS-14-7 | unit |
| 14-REQ-3.1 | TS-14-4 | unit |
| 14-REQ-3.2 | TS-14-8 | unit |
| 14-REQ-4.1 | TS-14-5 | integration |
| 14-REQ-4.2 | TS-14-6 | integration |
| 14-REQ-1.E1 | (covered by 01-REQ-7.E1 tests) | — |
| 14-REQ-2.E1 | TS-14-E1 | unit |
| 14-REQ-3.E1 | TS-14-E2 | unit |
| 14-REQ-4.E1 | TS-14-E3 | integration |
| Property 1 | TS-14-P1 | property |
| Property 2 | TS-14-P2 | property |
| Property 3 | TS-14-P3 | property |
| Property 4 | TS-14-P4 | property |
| Property 5 | TS-14-P5 | property |
