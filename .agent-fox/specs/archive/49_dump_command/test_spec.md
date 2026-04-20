# Test Specification: `dump` CLI Command

## Overview

Test cases map 1:1 to acceptance criteria and correctness properties from the
requirements and design documents. All tests use in-memory DuckDB connections
and Click's `CliRunner` for CLI invocation.

## Test Cases

### TS-49-1: Command is registered

**Requirement:** 49-REQ-1.1
**Type:** unit
**Description:** Verify `dump` appears as a subcommand of the main CLI group.

**Preconditions:**
- Main CLI group is imported.

**Input:**
- Inspect `main.commands`.

**Expected:**
- `"dump"` is a key in `main.commands`.

**Assertion pseudocode:**
```
ASSERT "dump" IN main.commands
```

### TS-49-2: Error when no flags provided

**Requirement:** 49-REQ-1.2
**Type:** unit
**Description:** Bare `dump` without `--memory` or `--db` exits with code 1.

**Preconditions:**
- Knowledge DB exists (mock or in-memory).

**Input:**
- Invoke `dump` with no flags.

**Expected:**
- Exit code 1.
- Output contains error text about missing flag.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["dump"])
ASSERT result.exit_code == 1
ASSERT "must specify" IN result.output.lower() OR result.stderr
```

### TS-49-3: Error when both flags provided

**Requirement:** 49-REQ-1.E1
**Type:** unit
**Description:** `dump --memory --db` exits with code 1.

**Preconditions:**
- Knowledge DB exists.

**Input:**
- Invoke `dump --memory --db`.

**Expected:**
- Exit code 1.
- Output contains error text about mutual exclusivity.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["dump", "--memory", "--db"])
ASSERT result.exit_code == 1
ASSERT "mutually exclusive" IN result.output.lower() OR result.stderr
```

### TS-49-4: Memory export writes Markdown

**Requirement:** 49-REQ-2.1
**Type:** unit
**Description:** `--memory` produces `docs/memory.md` with facts grouped by
category.

**Preconditions:**
- In-memory DuckDB with `memory_facts` table containing at least 2 facts
  in different categories.

**Input:**
- Invoke `dump --memory`.

**Expected:**
- `docs/memory.md` exists and contains category headings and fact bullets.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["dump", "--memory"])
ASSERT result.exit_code == 0
content = Path("docs/memory.md").read_text()
ASSERT "## Gotchas" IN content
ASSERT fact_content IN content
```

### TS-49-5: Memory export writes JSON

**Requirement:** 49-REQ-2.2
**Type:** unit
**Description:** `--json dump --memory` produces `docs/memory.json`.

**Preconditions:**
- In-memory DuckDB with facts.

**Input:**
- Invoke `--json dump --memory`.

**Expected:**
- `docs/memory.json` exists, is valid JSON, has `facts` array and
  `generated` timestamp, each fact has required keys.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "dump", "--memory"])
ASSERT result.exit_code == 0
data = json.loads(Path("docs/memory.json").read_text())
ASSERT "facts" IN data
ASSERT "generated" IN data
ASSERT len(data["facts"]) == expected_count
for fact in data["facts"]:
    ASSERT {"id", "content", "category", "spec_name", "confidence"} <= fact.keys()
```

### TS-49-6: Memory export prints confirmation

**Requirement:** 49-REQ-2.3
**Type:** unit
**Description:** `--memory` prints a confirmation message with file path and
fact count.

**Preconditions:**
- In-memory DuckDB with N facts.

**Input:**
- Invoke `dump --memory`.

**Expected:**
- stderr contains file path and fact count.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["dump", "--memory"])
ASSERT "docs/memory" IN result.output
ASSERT str(N) IN result.output
```

### TS-49-7: DB dump writes Markdown

**Requirement:** 49-REQ-3.1
**Type:** unit
**Description:** `--db` produces `.agent-fox/knowledge_dump.md` with all
tables.

**Preconditions:**
- In-memory DuckDB with at least 2 tables containing rows.

**Input:**
- Invoke `dump --db`.

**Expected:**
- `.agent-fox/knowledge_dump.md` exists, contains `## table_name` headings
  for each table, with column headers and data rows.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["dump", "--db"])
ASSERT result.exit_code == 0
content = Path(".agent-fox/knowledge_dump.md").read_text()
ASSERT "## memory_facts" IN content
ASSERT "## schema_version" IN content
```

### TS-49-8: DB dump writes JSON

**Requirement:** 49-REQ-3.2
**Type:** unit
**Description:** `--json dump --db` produces `.agent-fox/knowledge_dump.json`.

**Preconditions:**
- In-memory DuckDB with tables.

**Input:**
- Invoke `--json dump --db`.

**Expected:**
- `.agent-fox/knowledge_dump.json` exists, is valid JSON with `tables` dict
  and `generated` timestamp.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["--json", "dump", "--db"])
ASSERT result.exit_code == 0
data = json.loads(Path(".agent-fox/knowledge_dump.json").read_text())
ASSERT "tables" IN data
ASSERT "generated" IN data
ASSERT isinstance(data["tables"], dict)
ASSERT len(data["tables"]) == expected_table_count
```

### TS-49-9: DB dump prints confirmation

**Requirement:** 49-REQ-3.3
**Type:** unit
**Description:** `--db` prints confirmation with file path and table count.

**Preconditions:**
- In-memory DuckDB with tables.

**Input:**
- Invoke `dump --db`.

**Expected:**
- Output contains file path and table count.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["dump", "--db"])
ASSERT "knowledge_dump" IN result.output
ASSERT str(table_count) IN result.output
```

### TS-49-10: DB dump truncates long cells

**Requirement:** 49-REQ-3.4
**Type:** unit
**Description:** Cell values longer than 120 chars are truncated with `...`
in Markdown output.

**Preconditions:**
- In-memory DuckDB with a table containing a cell value > 120 chars.

**Input:**
- Call `dump_table_md(conn, table_name)`.

**Expected:**
- The cell is truncated to 117 chars + `...`.

**Assertion pseudocode:**
```
md = dump_table_md(conn, "test_table")
ASSERT "..." IN md
ASSERT long_value NOT IN md
ASSERT long_value[:117] IN md
```

### TS-49-11: Error when DB missing

**Requirement:** 49-REQ-4.1
**Type:** unit
**Description:** Command exits 1 when knowledge DB file does not exist.

**Preconditions:**
- No `.agent-fox/knowledge.duckdb` file.

**Input:**
- Invoke `dump --memory`.

**Expected:**
- Exit code 1, error message about missing database.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["dump", "--memory"])
ASSERT result.exit_code == 1
ASSERT "not found" IN result.output.lower() OR "does not exist" IN result.output.lower()
```

## Edge Case Tests

### TS-49-E1: Memory export with no facts

**Requirement:** 49-REQ-2.E1
**Type:** unit
**Description:** `--memory` with empty DB writes an empty-state file.

**Preconditions:**
- In-memory DuckDB with `memory_facts` table but no rows.

**Input:**
- Invoke `dump --memory`.

**Expected:**
- Output file exists with empty-state content.
- Warning printed to stderr.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["dump", "--memory"])
ASSERT result.exit_code == 0
content = Path("docs/memory.md").read_text()
ASSERT "no facts" IN content.lower()
```

### TS-49-E2: Memory JSON export with no facts

**Requirement:** 49-REQ-2.E1
**Type:** unit
**Description:** `--json --memory` with empty DB writes JSON with empty array.

**Preconditions:**
- In-memory DuckDB with empty `memory_facts` table.

**Input:**
- Invoke `--json dump --memory`.

**Expected:**
- `docs/memory.json` contains `{"facts": [], "generated": "..."}`.

**Assertion pseudocode:**
```
data = json.loads(Path("docs/memory.json").read_text())
ASSERT data["facts"] == []
ASSERT "generated" IN data
```

### TS-49-E3: DB dump with no tables

**Requirement:** 49-REQ-3.E1
**Type:** unit
**Description:** `--db` with a DB containing no tables exits with code 1.

**Preconditions:**
- In-memory DuckDB with no user tables.

**Input:**
- Invoke `dump --db`.

**Expected:**
- Exit code 1, warning about no tables.

**Assertion pseudocode:**
```
result = runner.invoke(main, ["dump", "--db"])
ASSERT result.exit_code == 1
ASSERT "no tables" IN result.output.lower()
```

## Property Test Cases

### TS-49-P1: Memory fact count preservation

**Property:** Property 3 from design.md
**Validates:** 49-REQ-2.1
**Type:** property
**Description:** Markdown output has exactly one bullet per active fact.

**For any:** List of 1-50 facts with random categories and content.
**Invariant:** The number of lines starting with `- ` in the output equals the
number of input facts.

**Assertion pseudocode:**
```
FOR ANY facts IN lists(fact_strategy, min_size=1, max_size=50):
    insert facts into in-memory DuckDB
    render_summary(conn, output_path)
    content = output_path.read_text()
    bullet_count = count lines starting with "- "
    ASSERT bullet_count == len(facts)
```

### TS-49-P2: Memory JSON key completeness

**Property:** Property 4 from design.md
**Validates:** 49-REQ-2.2
**Type:** property
**Description:** Every fact in JSON output has all required keys.

**For any:** List of 1-20 facts.
**Invariant:** Every object in `facts` array has keys `id`, `content`,
`category`, `spec_name`, `confidence`.

**Assertion pseudocode:**
```
FOR ANY facts IN lists(fact_strategy, min_size=1, max_size=20):
    insert facts into in-memory DuckDB
    render_summary_json(conn, output_path)
    data = json.loads(output_path.read_text())
    ASSERT len(data["facts"]) == len(facts)
    FOR each fact_obj IN data["facts"]:
        ASSERT {"id", "content", "category", "spec_name", "confidence"} <= fact_obj.keys()
```

### TS-49-P3: DB dump table coverage

**Property:** Property 5 from design.md
**Validates:** 49-REQ-3.1, 49-REQ-3.2
**Type:** property
**Description:** Output contains exactly as many table sections as the DB has
tables.

**For any:** DuckDB with 1-10 dynamically created tables.
**Invariant:** Markdown output has N `## table_name` headings; JSON output has
N keys in `tables` dict.

**Assertion pseudocode:**
```
FOR ANY table_names IN lists(table_name_strategy, min_size=1, max_size=10):
    create tables in in-memory DuckDB
    tables = discover_tables(conn)
    md = dump_all_tables_md(conn, output_path)
    ASSERT count("## " headings) == len(tables)

    json_data = dump_all_tables_json(conn, json_path)
    ASSERT len(json_data["tables"]) == len(tables)
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 49-REQ-1.1 | TS-49-1 | unit |
| 49-REQ-1.2 | TS-49-2 | unit |
| 49-REQ-1.E1 | TS-49-3 | unit |
| 49-REQ-2.1 | TS-49-4 | unit |
| 49-REQ-2.2 | TS-49-5 | unit |
| 49-REQ-2.3 | TS-49-6 | unit |
| 49-REQ-2.E1 | TS-49-E1, TS-49-E2 | unit |
| 49-REQ-3.1 | TS-49-7 | unit |
| 49-REQ-3.2 | TS-49-8 | unit |
| 49-REQ-3.3 | TS-49-9 | unit |
| 49-REQ-3.4 | TS-49-10 | unit |
| 49-REQ-3.E1 | TS-49-E3 | unit |
| 49-REQ-4.1 | TS-49-11 | unit |
| 49-REQ-5.1 | TS-49-P1 (implicit) | property |
| Property 3 | TS-49-P1 | property |
| Property 4 | TS-49-P2 | property |
| Property 5 | TS-49-P3 | property |
