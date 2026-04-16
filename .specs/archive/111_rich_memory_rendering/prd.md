# PRD: Rich Memory Rendering

## Problem Statement

The current `docs/memory.md` is a flat bullet list of facts grouped by category.
Each fact shows only its content, spec name, and confidence score. The knowledge
system stores significantly richer data -- causal chains between facts, entity
links to code files, supersession history, and timestamps -- but none of this
is surfaced in the rendered document.

This means:
- **Agents** (non-agent-fox) reading `memory.md` for context miss causal
  relationships ("X happened because of Y") and can't tell which facts are
  stale vs. fresh.
- **Humans** inspecting the knowledge base see an undifferentiated wall of
  bullets with no way to trace how facts relate to code or to each other.

## Goal

Enrich `docs/memory.md` rendering to surface causal chains, entity links,
supersession history, and relative age from the DuckDB knowledge store, while
keeping the format readable for both humans and agents.

## Scope

- Modify `agent_fox/knowledge/rendering.py` only.
- No DuckDB schema changes. All enrichment data already exists in `fact_causes`,
  `fact_entities`, `entity_graph`, and `memory_facts` tables.
- No changes to fact ingestion, harvesting, or retrieval logic.

## Out of Scope

- Interactive or web-based rendering.
- Rendering keywords, session_id, or commit_sha (not actionable enough for the
  document's audience).
- Changes to CLAUDE.md auto-memory (separate system).

## User Stories

1. As an agent reading `memory.md`, I want to see which facts caused or were
   caused by other facts, so I can understand the causal context behind a
   learning.
2. As a human reviewing memory, I want to see which code files are associated
   with each fact, so I can locate the relevant code.
3. As a reader of memory.md, I want to know how old each fact is, so I can
   judge whether it's still relevant.
4. As a reader, I want to see what a fact replaced, so I understand the
   evolution of knowledge.
5. As a reader, I want facts ordered by importance (confidence) within each
   category, so the most reliable facts appear first.

## Design Decisions

1. **Causal chain depth**: Depth 1 only (direct causes and effects). Deeper
   chains add noise. Max 2 causes + 2 effects per fact, each truncated to 60
   characters. Rendered as indented sub-bullets under the fact.

2. **Entity links**: File paths only (no function/class granularity). Max 3
   paths per fact with "+N more" overflow indicator. Rendered as indented
   sub-bullets.

3. **Age display**: Relative age computed from `created_at` timestamp. Format:
   "Xd ago" (days), "Xmo ago" (months), "Xy ago" (years). Shown inline in
   the metadata parenthetical.

4. **Supersession**: When a fact superseded an older fact, show a brief snippet
   of the old content truncated to 80 characters. Rendered as an indented
   sub-bullet.

5. **Ordering**: Facts within each category sorted by confidence descending,
   then by created_at descending (newest first among equal confidence).

6. **Summary header**: Add a total fact count and last-updated timestamp at the
   top of the document.

7. **Graceful degradation**: If enrichment queries fail (missing tables, query
   errors), fall back to the current basic format without sub-bullets. Log
   warnings but never crash rendering.

8. **Single format**: One markdown format for both humans and agents. Sub-bullets
   are parseable by LLMs and readable by humans.

## Dependencies

None. This spec modifies only `rendering.py` and its existing dependencies.
