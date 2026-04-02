# PRD: Prompt Caching for Auxiliary API Calls

## Problem

Agent-fox makes ~10 auxiliary API calls to Anthropic's Messages API via direct
`client.messages.create()` invocations (knowledge extraction, triage, critic,
assessor, spec validation, etc.). None of these calls use Anthropic's prompt
caching feature (`cache_control`), even though many share stable system
prompts or instruction blocks across invocations within a session.

Prompt caching can reduce input token costs by up to 90% on cache hits and
improve latency. The infrastructure to *track* cache tokens already exists
(cost accounting in `core/models.py`, pricing in `core/config.py`), but
nothing actively *requests* caching.

## Goal

Enable prompt caching on all auxiliary `client.messages.create()` calls by:

1. Adding a configurable cache policy (NONE / DEFAULT / EXTENDED) to
   `config.toml`.
2. Creating a shared helper in `core/client.py` that wraps `messages.create()`
   and injects `cache_control` markers based on the active policy.
3. Migrating all 9 auxiliary modules to use the helper.

## Scope

**In scope:**

- Auxiliary calls that use `client.messages.create()` directly:
  - `knowledge/extraction.py`
  - `engine/knowledge_harvest.py`
  - `knowledge/query_oracle.py`
  - `fix/clusterer.py`
  - `nightshift/critic.py`
  - `nightshift/staleness.py`
  - `nightshift/triage.py`
  - `routing/assessor.py`
  - `spec/ai_validation.py` (2 call sites)

- Configuration model additions to `core/config.py`.
- Helper function(s) in `core/client.py`.
- All calls should use the helper for consistency, even one-shot calls
  unlikely to get cache hits.

**Out of scope:**

- The main session path via `ClaudeSDKClient` / Agent SDK (auto-manages
  caching internally; no exposed control surface).
- Changes to cost accounting or token tracking (already works).

## Cache Policies

| Policy     | TTL    | Write Cost | Read Cost | Use Case                          |
|------------|--------|------------|-----------|-----------------------------------|
| `NONE`     | —      | —          | —         | Disable caching entirely          |
| `DEFAULT`  | 5 min  | 1.25×      | 0.1×      | Short-lived sessions (default)    |
| `EXTENDED` | 1 hour | 2.0×       | 0.1×      | Long-running batch / night-shift  |

Default policy: `DEFAULT`.

## Token Threshold Awareness

Anthropic requires a minimum number of tokens for caching to take effect
(2,048 for Sonnet, 4,096 for Opus/Haiku). If the check is simple to
implement, the helper should skip adding `cache_control` when the content
is below the model-specific threshold. Otherwise, add `cache_control`
unconditionally (the API silently ignores it when under threshold).

## Clarifications

- **Q: Should the Agent SDK path be included?** No — only auxiliary
  `messages.create()` calls.
- **Q: Should one-shot calls be cached?** Yes, for consistency. The API
  ignores caching on content below the minimum token threshold, so the
  overhead is negligible.
- **Q: How should the helper handle calls without a `system=` parameter?**
  Most auxiliary calls put instructions in the first user message rather than
  `system=`. The helper should support adding `cache_control` to either
  location. Callers that already use `system=` get it cached there; callers
  that embed instructions in user messages should be refactored to use
  `system=` where practical, or the helper caches the first user message
  block.
