# Errata

## Unwired CLI Commands (2026-03-06)

The following commands have been removed from the CLI surface:

- `agent-fox ask`
- `agent-fox patterns`
- `agent-fox ingest`
- `agent-fox compact`

The underlying functionality remains intact — the backing modules in
`agent_fox/knowledge/*` and `agent_fox/memory/compaction.py` are preserved and
tested. These commands were deliberately unwired because the knowledge
management approach is being rethought. They will be re-introduced (possibly in
a different form) once the new design is settled.

### Resolution: Knowledge Ingestion Restored (2026-03-10)

`agent_fox/knowledge/ingest.py` (deleted during the codebase simplification)
has been restored and wired into the `agent-fox code` lifecycle as automatic
background ingestion. ADRs and git commits are now ingested into DuckDB at
three points: startup, sync barriers, and shutdown — without any CLI command
required. The `ask`, `patterns`, and `compact` commands remain unwired.
