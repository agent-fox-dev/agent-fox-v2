# PRD: ADR Ingestion into Knowledge System

## Overview

After each coding session, agent-fox should inspect whether the agent produced
an Architecture Decision Record (ADR) in `docs/adr/` and, if so, validate it
against the MADR (Markdown Architectural Decision Records) format. Valid ADRs
are ingested into the DuckDB knowledge database and used to guide future coding
sessions — the same pattern used for errata.

This is a **process audit** feature, not a code quality audit. The system
partially automates ADR quality checks (structural validation, option count)
while the human owner can spot-check content quality as needed.

## Goals

1. **Detect** new or modified ADR files after each session by comparing
   `touched_files` against the `docs/adr/` directory.
2. **Validate** that each ADR follows the MADR format with at least 3
   considered options and a stated rationale.
3. **Ingest** valid ADRs into DuckDB so they become queryable knowledge.
4. **Supersede** old database entries when an ADR file is modified.
5. **Retrieve** relevant ADR summaries during session context assembly,
   matched by spec name and topic keywords.
6. **Inject** concise ADR summaries (not full documents) into session prompts
   so coding agents respect established architectural decisions.

## Non-Goals

- Generating ADRs (handled by the `/af-adr` skill).
- Blocking the pipeline on validation failures (warnings only).
- Making the ADR directory path configurable (hardcoded to `docs/adr/`).
- Periodic manual review scheduling.

## Design Decisions

1. **"After an eval run" → after each session.** ADR detection runs in the
   post-session ingest flow, checking `touched_files` for `docs/adr/*.md`
   paths. This reuses the existing `KnowledgeProvider.ingest()` hook.

2. **ADR relevance scoping → match by spec and topic.** At ingestion time,
   extract spec references (e.g., `42-REQ-`, `spec 42`, `42_rate_limiting`)
   and title keywords. At retrieval time, match against the current
   `spec_name` and `task_description`.

3. **MADR format only.** Enforce MADR 4.0.0 structural validation. Mandatory
   sections: `Context and Problem Statement`, `Considered Options`,
   `Decision Outcome`. Accept common synonyms (`Options Considered`,
   `Considered Alternatives`, `Decision`, `Context`) for backward
   compatibility with existing ADRs, but canonical MADR names are preferred.

4. **ADR detection via touched_files.** After harvest, `touched_files`
   contains relative paths of files changed by the session. Filter for
   `docs/adr/*.md` to detect new/modified ADRs. This is reliable because
   harvest produces a git-based file list.

5. **Validation failures → warning only.** Emit a log WARNING and an audit
   event when an ADR fails structural validation. Do not block the session
   or the pipeline. The ADR is not ingested.

6. **Prompt injection → summarized version only.** Inject a concise
   one-line summary per ADR: title, chosen option, rejected alternatives,
   and rationale. No content size limit.

7. **Supersession on content change.** Compute SHA-256 of file content at
   ingestion. If the hash matches an existing entry for the same file path,
   skip re-ingestion. If the hash differs, mark the old entry as superseded
   and insert a new one.

8. **ADR directory hardcoded to `docs/adr/`.** Matches the project convention
   documented in `CLAUDE.md`.

## Source

Source: Input provided by user via interactive prompt.
