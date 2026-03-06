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
