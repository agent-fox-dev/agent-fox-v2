# PRD: Steering Document

## Summary

Introduce a project-level steering document at `.specs/steering.md` that lets
users provide persistent, manually-maintained directives to all agents and
skills operating on the repository. The document is read-only from the agents'
perspective — only the user edits it.

## Motivation

Today there is no single place for a user to write "always prefer X" or "never
do Y" and have every agent and skill respect it. CLAUDE.md and AGENTS.md serve
related purposes but are generated/managed artifacts. A dedicated steering file
gives the user a stable, version-controlled surface to influence agent behavior
without editing generated files.

## Requirements

### R1 — Steering file location and format

The steering document lives at `.specs/steering.md` (project root-relative).
It is plain Markdown, free-form, maintained entirely by the user.

### R2 — Initialization

The `init` command creates `.specs/steering.md` as an empty placeholder if the
file does not already exist. The placeholder contains instructional comments
that explain the file's purpose without confusing agents (i.e., comments are
clearly marked as non-directive). The file is added to git.

### R3 — Runtime prompt inclusion

When the engine assembles a system prompt for any archetype, it reads
`.specs/steering.md` and injects its content into the prompt. Placement is
after spec documents and before memory facts. If the file does not exist or
contains only placeholder text (no real directives), it is skipped entirely.

### R4 — Skill template inclusion

Every bundled skill template includes an instruction directing the agent to
read and follow `.specs/steering.md` if the file exists.

### R5 — AGENTS.md reference

The AGENTS.md template includes a reference instructing agents to read and
follow `.specs/steering.md`. This is a static reference, not dynamic embedding.

## Clarifications

- **Fix/analyzer.py:** Out of scope — the fix feature is being removed.
- **Placement priority:** After spec documents, before memory facts. This gives
  steering directives higher priority than memory but lower than the spec
  being implemented.
- **Empty gating:** If the file is missing or contains only the initial
  placeholder content, skip inclusion entirely — do not inject empty/template
  text into prompts.
- **Placeholder design:** The placeholder uses instructional text clearly marked
  so agents do not treat it as directives (e.g., HTML comments or explicit
  "no directives set" sentinel).
