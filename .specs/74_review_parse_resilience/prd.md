# PRD: Review Parse Resilience

## Problem Statement

Review archetypes (skeptic, verifier, auditor, oracle) complete sessions
reliably but the harvester fails to parse their structured JSON output **57% of
the time**. This means the system pays for reviews it cannot act on
programmatically — blocking logic, severity gating, and verifier-driven retries
all operate at roughly 50% effectiveness.

**Data source:** 14 orchestrator runs, 40 review sessions, 23 parse failures
(see `docs/archetype-effectiveness-assessment.md`).

## Root Cause

The review archetypes' prompts ask for JSON output, but Claude sometimes:

- Wraps JSON in markdown fences with extra prose around it
- Uses slightly different field names (e.g., `finding` vs `findings`)
- Adds commentary before/after the JSON block
- Produces JSON objects instead of arrays (or vice versa)
- Omits optional fields that downstream parsers expect

The existing extraction pipeline (`json_extraction.py`) already handles markdown
fences and bracket-scanning, and `_unwrap_items()` handles some wrapper
variants. Despite this, 57% of review sessions produce unparseable output.

## Goals

1. **Reduce parse failure rate from 57% to <10%** across all review archetypes.
2. Achieve this through two complementary strategies:
   - **(a) Stricter prompts:** Tighten the output format instructions in review
     archetype templates to reduce format variance at the source.
   - **(b) More tolerant parser + retry loop:** Make the harvester more forgiving
     of common format deviations, and when parsing still fails, re-prompt the
     agent with a specific formatting correction request.
3. Handle partial parse results in multi-instance convergence — if some
   instances produce parseable output and others don't, use what's available.

## Non-Goals

- Switching to structured tool calls for review output (staying with free-form
  JSON in response text).
- Changing the review archetype responsibilities or review dimensions.
- Modifying the convergence algorithms themselves (union, majority vote, etc.)
  beyond handling partial input.

## Scope

All four review archetypes: **skeptic**, **verifier**, **auditor**, **oracle**.

## Approach

### Strategy A: Stricter Prompts

Add explicit format enforcement instructions to each review archetype template:

- "Output ONLY the JSON block — no prose before or after."
- "Do NOT wrap the JSON in markdown fences."
- "Use EXACTLY the field names shown in the schema."
- Add a negative example showing common mistakes.
- Repeat the schema constraint near the end of the prompt (recency bias).

### Strategy B: Tolerant Parser + Retry

1. **Fuzzy field matching:** Accept common field name variants (e.g.,
   `finding`/`findings`, `verdict`/`verdicts`, `result`/`results`).
2. **Case-insensitive keys:** Normalize JSON keys to lowercase before matching.
3. **Object-in-array unwrapping:** If the top-level JSON is a single object
   containing array-valued fields, try known wrapper keys.
4. **Retry on parse failure:** When all extraction strategies fail, re-prompt
   the agent (up to 1 retry) with a short message explaining the formatting
   error and requesting just the JSON block. The retry uses the same session
   (appends a user message), not a new session.

### Convergence with Partial Results

When running multi-instance review archetypes, some instances may produce
parseable results while others fail. The convergence logic should:

- Proceed with whatever instances produced valid results.
- Log a warning for instances that failed parsing.
- Only emit `REVIEW_PARSE_FAILURE` if ALL instances fail parsing.

## Clarifications

- **Retry cost:** The retry appends a short user message to the existing
  session context. This costs minimal additional tokens (the context is already
  loaded). Maximum 1 retry per review session.
- **Auditor output:** The auditor uses the same approach as other archetypes
  (stricter prompts + tolerant parsing + retry). Its richer schema
  (`audit` array + `overall_verdict` + `summary`) is handled by the same
  fuzzy matching and retry mechanism.
- **Oracle inclusion:** The oracle archetype is in scope and receives the same
  treatment as the other three review archetypes.
- **Backward compatibility:** No format switch is happening. Old transcripts
  remain parseable — the parser is being made MORE tolerant, not less.
