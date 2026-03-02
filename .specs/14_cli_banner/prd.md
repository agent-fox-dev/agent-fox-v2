# PRD: CLI Output Banner Enhancement

> Source: [GitHub Issue #46](https://github.com/agent-fox-dev/agent-fox-v2/issues/46)

## Problem

The CLI output banner is missing the fox ASCII art and contextual information.
Currently the banner only displays `agent-fox v{version}` and a playful/neutral
message. Users need to see the fox mascot, the active coding model, and the
current working directory at a glance.

## Requirements

Enhance the CLI banner to display:

1. **Fox ASCII art** styled with the theme's header color:
   ```
      /\_/\  _
     / o.o \/ \
    ( > ^ < )  )
     \_^/\_/--'
   ```
2. **Version and model info** on a single line: `agent-fox v{version}  model: {resolved_coding_model}`
3. **Current working directory** on its own line.

### Example Output

```
   /\_/\  _
  / o.o \/ \
 ( > ^ < )  )
  \_^/\_/--'
agent-fox v0.1.0  model: claude-opus-4-6
/Users/candlekeep/devel/workspace/agent-fox-v2
```

## Clarifications

1. **Which model?** Display the resolved `coding` model from config (e.g.,
   if `models.coding = "ADVANCED"`, resolve to `claude-opus-4-6`).
2. **When to display?** The banner SHALL be displayed on every CLI invocation,
   including when running subcommands — not just when invoked without a
   subcommand.
3. **Fox art styling:** The ASCII fox SHALL use the theme's existing `header`
   color role (bold orange by default).
4. **Working directory:** Display `Path.cwd()` — the directory from which the
   CLI was invoked.
5. **Model resolution failure:** If the configured model cannot be resolved,
   display the raw tier name (e.g., `model: ADVANCED`) instead of crashing.
6. **Canonical fox art:** Use the version from this issue (differs slightly
   from README.md).

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 01_core_foundation | 4 | 1 | Imports CLI framework, theme system, config, model registry from group 4 |
