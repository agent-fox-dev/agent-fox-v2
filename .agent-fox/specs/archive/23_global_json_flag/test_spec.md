# Test Specification: Global --json Flag

## Overview

Tests verify that the `--json` flag produces valid structured JSON from every
command, suppresses the banner, handles errors as JSON envelopes, reads stdin
JSON, and that removing `--format` does not break existing behavior. All tests
use Click's test runner with mocked dependencies.

## Test Cases

### TS-23-1: Global flag accessible to subcommands

**Requirement:** 23-REQ-1.1, 23-REQ-1.2
**Type:** integration
**Description:** Verify `--json` is accepted by the main group and visible in ctx.obj.

**Preconditions:**
- Click test runner with `main` group.

**Input:**
- `agent-fox --json status`

**Expected:**
- Command executes without Click usage error.
- `ctx.obj["json"]` is `True` inside the subcommand.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "status"])
ASSERT result.exit_code != 2  # not a usage error
```

---

### TS-23-2: Default mode unchanged

**Requirement:** 23-REQ-1.3
**Type:** integration
**Description:** Verify that without `--json`, output is human-readable (not JSON).

**Preconditions:**
- Click test runner.

**Input:**
- `agent-fox status` (no `--json`)

**Expected:**
- Output is not valid JSON (contains banner/text formatting).

**Assertion pseudocode:**
```
result = runner.invoke(main, ["status"])
ASSERT json.loads(result.output) RAISES JSONDecodeError
```

---

### TS-23-3: Banner suppressed in JSON mode

**Requirement:** 23-REQ-2.1
**Type:** integration
**Description:** Verify the fox banner does not appear in JSON mode output.

**Preconditions:**
- Click test runner.

**Input:**
- `agent-fox --json status`

**Expected:**
- stdout does not contain banner markers (e.g., `/\\_/\\` or `agent-fox v`).

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "status"])
ASSERT "/\\_/\\" NOT IN result.output
ASSERT "agent-fox v" NOT IN result.output
```

---

### TS-23-4: No non-JSON text on stdout

**Requirement:** 23-REQ-2.2
**Type:** integration
**Description:** Verify all stdout content is valid JSON in JSON mode.

**Preconditions:**
- Click test runner with mocked dependencies.

**Input:**
- `agent-fox --json status`

**Expected:**
- `json.loads(result.output)` succeeds.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "status"])
data = json.loads(result.output)
ASSERT isinstance(data, dict)
```

---

### TS-23-5: Status command JSON output

**Requirement:** 23-REQ-3.1
**Type:** integration
**Description:** Verify `status --json` emits a JSON object.

**Preconditions:**
- Mocked status report.

**Input:**
- `agent-fox --json status`

**Expected:**
- Valid JSON object on stdout.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "status"])
data = json.loads(result.output)
ASSERT isinstance(data, dict)
```

---

### TS-23-6: Standup command JSON output

**Requirement:** 23-REQ-3.2
**Type:** integration
**Description:** Verify `standup --json` emits a JSON object.

**Preconditions:**
- Mocked standup report.

**Input:**
- `agent-fox --json standup`

**Expected:**
- Valid JSON object on stdout.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "standup"])
data = json.loads(result.output)
ASSERT isinstance(data, dict)
```

---

### TS-23-7: Lint-spec command JSON output

**Requirement:** 23-REQ-3.3
**Type:** integration
**Description:** Verify `lint-spec --json` emits findings as JSON.

**Preconditions:**
- Spec directory with at least one spec.

**Input:**
- `agent-fox --json lint-spec`

**Expected:**
- Valid JSON with `"findings"` and `"summary"` keys.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "lint-spec"])
data = json.loads(result.output)
ASSERT "findings" IN data
ASSERT "summary" IN data
```

---

### TS-23-8: Plan command JSON output

**Requirement:** 23-REQ-3.4
**Type:** integration
**Description:** Verify `plan --json` emits the execution plan as JSON.

**Preconditions:**
- Spec directory with at least one spec and tasks.md.

**Input:**
- `agent-fox --json plan`

**Expected:**
- Valid JSON object on stdout.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "plan"])
data = json.loads(result.output)
ASSERT isinstance(data, dict)
```

---

### TS-23-9: Patterns command JSON output

**Requirement:** 23-REQ-3.5
**Type:** integration
**Description:** Verify `patterns --json` emits results as JSON.

**Preconditions:**
- Mocked pattern detection.

**Input:**
- `agent-fox --json patterns`

**Expected:**
- Valid JSON object on stdout.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "patterns"])
data = json.loads(result.output)
ASSERT isinstance(data, dict)
```

---

### TS-23-10: Compact command JSON output

**Requirement:** 23-REQ-3.6
**Type:** integration
**Description:** Verify `compact --json` emits compaction stats as JSON.

**Preconditions:**
- Mocked knowledge store.

**Input:**
- `agent-fox --json compact`

**Expected:**
- Valid JSON object on stdout.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "compact"])
data = json.loads(result.output)
ASSERT isinstance(data, dict)
```

---

### TS-23-11: Ingest command JSON output

**Requirement:** 23-REQ-3.7
**Type:** integration
**Description:** Verify `ingest --json` emits ingestion stats as JSON.

**Preconditions:**
- Mocked ingestion pipeline.

**Input:**
- `agent-fox --json ingest some_file.md`

**Expected:**
- Valid JSON object on stdout.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "ingest", "some_file.md"])
data = json.loads(result.output)
ASSERT isinstance(data, dict)
```

---

### TS-23-12: Init command JSON output

**Requirement:** 23-REQ-4.1
**Type:** integration
**Description:** Verify `init --json` emits `{"status": "ok"}`.

**Preconditions:**
- Mocked init logic.

**Input:**
- `agent-fox --json init`

**Expected:**
- `{"status": "ok"}` on stdout.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "init"])
data = json.loads(result.output)
ASSERT data["status"] == "ok"
```

---

### TS-23-13: Reset command JSON output

**Requirement:** 23-REQ-4.2
**Type:** integration
**Description:** Verify `reset --json` emits a JSON summary.

**Preconditions:**
- Mocked reset logic.

**Input:**
- `agent-fox --json reset`

**Expected:**
- Valid JSON object on stdout.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "reset"])
data = json.loads(result.output)
ASSERT isinstance(data, dict)
```

---

### TS-23-14: Code command JSONL output

**Requirement:** 23-REQ-5.1
**Type:** integration
**Description:** Verify `code --json` emits JSONL (one JSON object per line).

**Preconditions:**
- Mocked code execution emitting 2+ events.

**Input:**
- `agent-fox --json code "task"`

**Expected:**
- Each line of stdout is a valid JSON object.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "code", "task"])
lines = result.output.strip().splitlines()
FOR line IN lines:
    data = json.loads(line)
    ASSERT isinstance(data, dict)
```

---

### TS-23-15: Ask command JSON output

**Requirement:** 23-REQ-5.2
**Type:** integration
**Description:** Verify `ask --json` emits answer as JSON.

**Preconditions:**
- Mocked oracle.

**Input:**
- `agent-fox --json ask "question"`

**Expected:**
- Valid JSON object on stdout.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "ask", "question"])
data = json.loads(result.output)
ASSERT isinstance(data, dict)
```

---

### TS-23-16: Fix command JSONL output

**Requirement:** 23-REQ-5.3
**Type:** integration
**Description:** Verify `fix --json` emits JSONL events.

**Preconditions:**
- Mocked fix execution.

**Input:**
- `agent-fox --json fix "issue"`

**Expected:**
- Each line is valid JSON.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "fix", "issue"])
lines = result.output.strip().splitlines()
FOR line IN lines:
    ASSERT json.loads(line) is valid
```

---

### TS-23-17: Error envelope on failure

**Requirement:** 23-REQ-6.1, 23-REQ-6.3
**Type:** integration
**Description:** Verify that command failure in JSON mode produces an error envelope.

**Preconditions:**
- Command that raises an exception.

**Input:**
- `agent-fox --json plan` (with invalid specs directory)

**Expected:**
- stdout contains `{"error": "..."}`.
- No unstructured text on stdout.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "plan"])
data = json.loads(result.output)
ASSERT "error" IN data
ASSERT isinstance(data["error"], str)
```

---

### TS-23-18: Exit code preserved in JSON mode

**Requirement:** 23-REQ-6.2
**Type:** integration
**Description:** Verify exit codes are the same with and without `--json`.

**Preconditions:**
- Command that fails with a known exit code.

**Input:**
- Same failing command, once with `--json`, once without.

**Expected:**
- Same non-zero exit code in both cases.

**Assertion pseudocode:**
```
result_text = runner.invoke(main, ["plan"])
result_json = runner.invoke(main, ["--json", "plan"])
ASSERT result_text.exit_code == result_json.exit_code
```

---

### TS-23-19: Stdin JSON read

**Requirement:** 23-REQ-7.1, 23-REQ-7.2
**Type:** unit
**Description:** Verify `read_stdin()` parses JSON from piped input.

**Preconditions:**
- Mocked stdin with JSON content.

**Input:**
- `'{"question": "what is fox?"}'` on stdin.

**Expected:**
- Returns `{"question": "what is fox?"}`.

**Assertion pseudocode:**
```
mock_stdin('{"question": "what is fox?"}')
result = read_stdin()
ASSERT result == {"question": "what is fox?"}
```

---

### TS-23-20: Stdin TTY no blocking

**Requirement:** 23-REQ-7.3
**Type:** unit
**Description:** Verify `read_stdin()` returns empty dict for TTY input.

**Preconditions:**
- stdin.isatty() returns True.

**Input:**
- (none — TTY mode)

**Expected:**
- Returns `{}` immediately.

**Assertion pseudocode:**
```
mock_stdin_tty()
result = read_stdin()
ASSERT result == {}
```

---

### TS-23-21: --format removed from status

**Requirement:** 23-REQ-8.1
**Type:** integration
**Description:** Verify `status --format json` produces a Click usage error.

**Preconditions:**
- Click test runner.

**Input:**
- `agent-fox status --format json`

**Expected:**
- Exit code 2 (Click usage error).

**Assertion pseudocode:**
```
result = runner.invoke(main, ["status", "--format", "json"])
ASSERT result.exit_code == 2
```

---

### TS-23-22: --format removed from standup

**Requirement:** 23-REQ-8.2
**Type:** integration
**Description:** Verify `standup --format json` produces a Click usage error.

**Preconditions:**
- Click test runner.

**Input:**
- `agent-fox standup --format json`

**Expected:**
- Exit code 2.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["standup", "--format", "json"])
ASSERT result.exit_code == 2
```

---

### TS-23-23: --format removed from lint-spec

**Requirement:** 23-REQ-8.3
**Type:** integration
**Description:** Verify `lint-spec --format json` produces a Click usage error.

**Preconditions:**
- Click test runner.

**Input:**
- `agent-fox lint-spec --format json`

**Expected:**
- Exit code 2.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["lint-spec", "--format", "json"])
ASSERT result.exit_code == 2
```

---

### TS-23-24: YAML output format removed

**Requirement:** 23-REQ-8.4, 23-REQ-8.5
**Type:** unit
**Description:** Verify `OutputFormat` enum has no YAML member and YAML formatters are removed.

**Preconditions:**
- Import `OutputFormat` from formatters module.

**Input:**
- Inspect enum members.

**Expected:**
- `"yaml"` is not in `OutputFormat` members.

**Assertion pseudocode:**
```
ASSERT "YAML" NOT IN OutputFormat.__members__
ASSERT NOT hasattr(formatters_module, "YamlFormatter")
```

## Property Test Cases

### TS-23-P1: JSON exclusivity

**Property:** Property 1 from design.md
**Validates:** 23-REQ-2.2, 23-REQ-3.1 through 23-REQ-3.7
**Type:** property
**Description:** For any batch command invoked with --json, stdout is valid JSON.

**For any:** command name drawn from the set of batch commands
**Invariant:** `json.loads(stdout)` succeeds and returns a dict.

**Assertion pseudocode:**
```
FOR ANY cmd IN ["status", "standup", "lint-spec", "plan", "patterns", "compact", "ingest", "init", "reset"]:
    result = runner.invoke(main, ["--json", cmd])
    data = json.loads(result.output)
    ASSERT isinstance(data, dict)
```

---

### TS-23-P2: Error envelope structure

**Property:** Property 2 from design.md
**Validates:** 23-REQ-6.1, 23-REQ-6.3
**Type:** property
**Description:** For any command that fails in JSON mode, stdout contains a valid error envelope.

**For any:** failing command scenario
**Invariant:** Output parses as JSON with an `"error"` key containing a non-empty string.

**Assertion pseudocode:**
```
FOR ANY failing_cmd IN failing_scenarios:
    result = runner.invoke(main, ["--json"] + failing_cmd)
    data = json.loads(result.output)
    ASSERT "error" IN data
    ASSERT len(data["error"]) > 0
```

---

### TS-23-P3: Exit code preservation

**Property:** Property 3 from design.md
**Validates:** 23-REQ-6.2
**Type:** property
**Description:** For any command, JSON mode preserves the exit code.

**For any:** command that produces a known exit code
**Invariant:** Exit code is identical with and without `--json`.

**Assertion pseudocode:**
```
FOR ANY cmd IN all_commands:
    result_text = runner.invoke(main, cmd)
    result_json = runner.invoke(main, ["--json"] + cmd)
    ASSERT result_text.exit_code == result_json.exit_code
```

---

### TS-23-P4: Flag precedence over stdin

**Property:** Property 4 from design.md
**Validates:** 23-REQ-7.2
**Type:** unit
**Description:** CLI flags override stdin JSON fields.

**For any:** parameter name, CLI value, stdin value
**Invariant:** The command uses the CLI flag value, not the stdin value.

**Assertion pseudocode:**
```
FOR ANY param, cli_val, stdin_val WHERE cli_val != stdin_val:
    mock_stdin(json.dumps({param: stdin_val}))
    # invoke with CLI flag set to cli_val
    ASSERT command used cli_val
```

## Edge Case Tests

### TS-23-E1: --json with --verbose

**Requirement:** 23-REQ-1.E1
**Type:** integration
**Description:** Verify `--json --verbose` produces JSON output with debug logs on stderr.

**Preconditions:**
- Click test runner.

**Input:**
- `agent-fox --json --verbose status`

**Expected:**
- stdout is valid JSON.
- stderr contains debug log lines.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "--verbose", "status"])
ASSERT json.loads(result.output) is valid
```

---

### TS-23-E2: Logs go to stderr in JSON mode

**Requirement:** 23-REQ-2.E1
**Type:** integration
**Description:** Verify log messages go to stderr, not stdout, in JSON mode.

**Preconditions:**
- Command that logs at INFO level.

**Input:**
- `agent-fox --json status`

**Expected:**
- stdout contains only JSON.
- Any log output is on stderr only.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "status"])
ASSERT json.loads(result.output) is valid  # no log lines mixed in
```

---

### TS-23-E3: Empty data produces valid JSON

**Requirement:** 23-REQ-3.E1
**Type:** integration
**Description:** Verify a command with no data still emits a valid JSON object.

**Preconditions:**
- Empty specs directory.

**Input:**
- `agent-fox --json plan`

**Expected:**
- stdout is a valid JSON object (may have error key or empty fields).

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "plan"])
data = json.loads(result.output)
ASSERT isinstance(data, dict)
```

---

### TS-23-E4: Streaming interrupted

**Requirement:** 23-REQ-5.E1
**Type:** integration
**Description:** Verify interrupted streaming emits final status object.

**Preconditions:**
- Mocked code command that receives SIGINT mid-stream.

**Input:**
- `agent-fox --json code "task"` (interrupted)

**Expected:**
- Last line of stdout contains `{"status": "interrupted"}`.

**Assertion pseudocode:**
```
# simulate interrupt
last_line = result.output.strip().splitlines()[-1]
data = json.loads(last_line)
ASSERT data["status"] == "interrupted"
```

---

### TS-23-E5: Unhandled exception in JSON mode

**Requirement:** 23-REQ-6.E1
**Type:** integration
**Description:** Verify unhandled exceptions produce error envelope in JSON mode.

**Preconditions:**
- Command that raises unexpected Exception.

**Input:**
- Command triggering unhandled error.

**Expected:**
- stdout is `{"error": "..."}`.
- Exit code is 1.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "failing_cmd"])
data = json.loads(result.output)
ASSERT "error" IN data
ASSERT result.exit_code == 1
```

---

### TS-23-E6: Invalid JSON on stdin

**Requirement:** 23-REQ-7.E1
**Type:** unit
**Description:** Verify invalid stdin JSON produces error envelope.

**Preconditions:**
- stdin contains `"not valid json {"`.

**Input:**
- Invalid JSON string.

**Expected:**
- Error envelope with message about invalid JSON.

**Assertion pseudocode:**
```
mock_stdin("not valid json {")
result = read_stdin()  # should raise
# or at command level:
ASSERT "error" IN json.loads(result.output)
```

---

### TS-23-E7: Unknown stdin fields ignored

**Requirement:** 23-REQ-7.E2
**Type:** unit
**Description:** Verify unknown fields in stdin JSON are silently ignored.

**Preconditions:**
- stdin JSON contains `{"unknown_field": 42, "question": "test"}`.

**Input:**
- JSON with extra fields.

**Expected:**
- Command processes recognized fields, ignores unknown ones.

**Assertion pseudocode:**
```
mock_stdin('{"unknown_field": 42, "question": "test"}')
result = read_stdin()
ASSERT result["question"] == "test"
# no error raised
```

---

### TS-23-E8: --format produces usage error

**Requirement:** 23-REQ-8.E1
**Type:** integration
**Description:** Verify removed `--format` flag produces Click usage error.

**Preconditions:**
- Click test runner.

**Input:**
- `agent-fox status --format yaml`

**Expected:**
- Exit code 2 (usage error).

**Assertion pseudocode:**
```
result = runner.invoke(main, ["status", "--format", "yaml"])
ASSERT result.exit_code == 2
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 23-REQ-1.1 | TS-23-1 | integration |
| 23-REQ-1.2 | TS-23-1 | integration |
| 23-REQ-1.3 | TS-23-2 | integration |
| 23-REQ-1.E1 | TS-23-E1 | integration |
| 23-REQ-2.1 | TS-23-3 | integration |
| 23-REQ-2.2 | TS-23-4 | integration |
| 23-REQ-2.E1 | TS-23-E2 | integration |
| 23-REQ-3.1 | TS-23-5 | integration |
| 23-REQ-3.2 | TS-23-6 | integration |
| 23-REQ-3.3 | TS-23-7 | integration |
| 23-REQ-3.4 | TS-23-8 | integration |
| 23-REQ-3.5 | TS-23-9 | integration |
| 23-REQ-3.6 | TS-23-10 | integration |
| 23-REQ-3.7 | TS-23-11 | integration |
| 23-REQ-3.E1 | TS-23-E3 | integration |
| 23-REQ-4.1 | TS-23-12 | integration |
| 23-REQ-4.2 | TS-23-13 | integration |
| 23-REQ-5.1 | TS-23-14 | integration |
| 23-REQ-5.2 | TS-23-15 | integration |
| 23-REQ-5.3 | TS-23-16 | integration |
| 23-REQ-5.E1 | TS-23-E4 | integration |
| 23-REQ-6.1 | TS-23-17 | integration |
| 23-REQ-6.2 | TS-23-18 | integration |
| 23-REQ-6.3 | TS-23-17 | integration |
| 23-REQ-6.E1 | TS-23-E5 | integration |
| 23-REQ-7.1 | TS-23-19 | unit |
| 23-REQ-7.2 | TS-23-19 | unit |
| 23-REQ-7.3 | TS-23-20 | unit |
| 23-REQ-7.E1 | TS-23-E6 | unit |
| 23-REQ-7.E2 | TS-23-E7 | unit |
| 23-REQ-8.1 | TS-23-21 | integration |
| 23-REQ-8.2 | TS-23-22 | integration |
| 23-REQ-8.3 | TS-23-23 | integration |
| 23-REQ-8.4 | TS-23-24 | unit |
| 23-REQ-8.5 | TS-23-24 | unit |
| 23-REQ-8.E1 | TS-23-E8 | integration |
| Property 1 | TS-23-P1 | property |
| Property 2 | TS-23-P2 | property |
| Property 3 | TS-23-P3 | property |
| Property 4 | TS-23-P4 | unit |
