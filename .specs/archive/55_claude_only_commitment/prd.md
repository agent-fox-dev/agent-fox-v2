# PRD: Claude-Only Commitment

## Problem Statement

Agent-Fox currently has an `AgentBackend` protocol abstraction and a
platform-aware client factory that could theoretically support multiple LLM
providers. This creates ambiguity about whether Google Gemini, OpenAI, or other
providers will be supported in the future. The generic `get_backend(name)`
factory accepts an arbitrary string, suggesting extensibility that will never be
used for coding agents.

Agent-Fox is **all-in with Claude** for coding agent workloads. The codebase
should reflect this commitment explicitly — in documentation, architecture
decisions, and code — so contributors don't waste effort on multi-provider
abstractions and users understand the product's positioning.

## Goals

1. **Document the decision** — Create an ADR stating that agent-fox uses Claude
   exclusively for all coding agent archetypes (coder, oracle, skeptic,
   verifier, auditor, librarian, cartographer, coordinator).
2. **Simplify the backend factory** — Remove the generic name-dispatch pattern
   in `get_backend()`. The only supported backend is `ClaudeBackend`.
3. **Preserve testability** — Keep the `AgentBackend` protocol so that tests
   can inject mock backends without touching the SDK.
4. **Preserve Claude platform flexibility** — Vertex AI and Bedrock are Claude
   delivery platforms, not alternative providers. The platform-aware client
   factory in `core/client.py` stays.
5. **Acknowledge future non-coding use** — The codebase may integrate non-Claude
   models for non-coding tasks in the future (e.g., embeddings, summarisation).
   This spec does not build infrastructure for that — it only carves out the
   conceptual space in documentation.

## Non-Goals

- Removing the `AgentBackend` protocol (it remains for mock injection).
- Removing Vertex/Bedrock support (these are Claude platforms).
- Building infrastructure for non-coding provider extensibility.
- Changing any runtime behavior — this is a documentation, policy, and
  dead-code-removal spec.

## Clarifications

- **Q: Should the protocol be removed?**
  A: No. The protocol enables test mocking. The commitment is that the only
  *production* implementation is `ClaudeBackend`.
- **Q: What about Vertex and Bedrock?**
  A: These are Claude platforms (Anthropic models on GCP/AWS). They stay.
- **Q: What about future non-coding uses of other models?**
  A: Out of scope. The ADR should mention this as a future possibility but
  this spec builds nothing for it.
