# PRD: Transient Audit Reports

## Problem

The auditor writes `audit.md` files into `.specs/NN_name/` directories. These
files are implementation artifacts — they are never read back by any code and
exist solely for human inspection during development. Because they live inside
spec directories (which are tracked by git), they show up as untracked files in
`git status` and risk being accidentally committed.

## Goal

Make audit reports truly transient by:

1. Writing them to `.agent-fox/audit/` (already gitignored) instead of into
   spec directories.
2. Automatically deleting them when they are no longer useful.

## Behaviour

- **Output location:** Audit reports are written to
  `.agent-fox/audit/audit_{spec_name}.md` (e.g.,
  `audit_91_nightshift_cost_tracking.md`).
- **Overwrite:** One file per spec. Each new audit run overwrites the previous
  report for that spec.
- **Delete on PASS:** When the auditor verdict is PASS, the audit report file
  for that spec is deleted (not written).
- **Delete on spec completion:** When all task groups for a spec are completed
  at the end of an engine run, the audit report file is deleted.

## Clarifications

- **Q: Where in `.agent-fox/`?**
  A: Reuse the existing `.agent-fox/audit/` directory. Encode the spec name in
  the filename. The existing JSONL audit event files use `.jsonl` extension so
  there is no naming conflict with `.md` report files.

- **Q: When to delete?**
  A: Two triggers: (d) overwrite on each audit run and delete on PASS verdict;
  (b) delete when full spec implementation is done (all task groups complete).

- **Q: Clean up existing audit.md in `.specs/`?**
  A: No migration. Existing files are left in place.

- **Q: Multiple audits per spec?**
  A: One file per spec, overwriting each attempt.

## Out of Scope

- Migration or cleanup of existing `audit.md` files in `.specs/` directories.
- Changes to the JSONL audit event system in `.agent-fox/audit/`.
- Changes to the GitHub issue filing logic in `auditor_output.py`.
