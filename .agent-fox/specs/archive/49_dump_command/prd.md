# PRD: `dump` CLI Command

## Summary

Add a new CLI command `agent-fox dump` that exposes two mutually exclusive
export operations:

- **`--memory`** — Re-creates `docs/memory.md` from the DuckDB knowledge
  database, using the existing `render_summary()` pipeline. This gives users
  an on-demand way to regenerate the memory file outside of a full
  orchestrator run.

- **`--db`** — Dumps every table in the DuckDB knowledge store to a
  human-readable Markdown file at `.agent-fox/knowledge_dump.md`, mirroring
  the behavior of the existing `scripts/dump_knowledge.py` helper.

Both flags respect the **global `--json`** flag. When `--json` is active the
output is written as a `.json` file instead of Markdown:

| Flag combination          | Output file                        |
|---------------------------|------------------------------------|
| `--memory`                | `docs/memory.md`                   |
| `--json --memory`         | `docs/memory.json`                 |
| `--db`                    | `.agent-fox/knowledge_dump.md`     |
| `--json --db`             | `.agent-fox/knowledge_dump.json`   |

## Constraints

- `--memory` and `--db` are **mutually exclusive**; specifying both is an
  error.
- At least one of `--memory` or `--db` must be provided; bare `agent-fox dump`
  is an error.
- Output paths are **fixed** (no `--output` override).
- The command opens the knowledge DB in **read-only** mode.
- If the knowledge DB does not exist the command prints an error and exits
  with code 1.

## JSON Format

### `--memory --json`

```json
{
  "facts": [
    {
      "id": "...",
      "content": "...",
      "category": "gotcha",
      "spec_name": "...",
      "confidence": 0.90
    }
  ],
  "generated": "2026-03-19T12:00:00"
}
```

### `--db --json`

```json
{
  "tables": {
    "table_name": [
      {"column1": "value1", "column2": "value2"},
      ...
    ]
  },
  "generated": "2026-03-19T12:00:00"
}
```

## Clarifications

1. **Mutual exclusivity:** `--memory` and `--db` are mutually exclusive.
   Providing both is a user error.
2. **Output paths:** Fixed defaults matching existing conventions — no
   `--output` override.
3. **JSON flag:** Uses the existing global `--json` flag from the CLI group,
   consistent with other commands.
4. **DB JSON shape:** `{"tables": {"table_name": [{row}, ...], ...}}` dict
   keyed by table name.
