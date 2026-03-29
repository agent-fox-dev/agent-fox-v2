# 01. Use Claude Exclusively for Coding Agents

## Status

Accepted

## Context

agent-fox is an autonomous coding-agent orchestrator that drives LLM-powered
agents through spec-driven task graphs. The backend layer originally included
a name-dispatched factory (`get_backend(name)`) suggesting future
multi-provider extensibility, even though only Claude (via `claude_code_sdk`)
was ever implemented.

Maintaining a multi-provider abstraction imposes ongoing costs:

- Every backend feature (tool use, permission callbacks, streaming) must be
  designed provider-agnostically, even when only one provider exists.
- Contributors may invest effort building or proposing adapters for other
  providers, diverting attention from the core product.
- The factory's `ValueError` path for unknown backends is dead code that adds
  noise to the codebase.

Claude (delivered via direct Anthropic API, Vertex AI on GCP, or Bedrock on
AWS) provides all the capabilities agent-fox requires: extended thinking,
tool use, streaming, and code-generation quality that meets our bar.

## Decision

Agent-fox uses Claude as the exclusive LLM provider for all coding agent
archetypes (coder, oracle, skeptic, verifier, auditor, librarian,
cartographer, coordinator).

Specifically:

- The `get_backend()` factory returns `ClaudeBackend` unconditionally, with
  no provider-name parameter.
- The `AgentBackend` protocol is preserved for test mock injection but carries
  a docstring noting that `ClaudeBackend` is the only production
  implementation.
- The platform-aware client factory (`core/client.py`) continues to support
  Vertex AI, Bedrock, and direct Anthropic API access — these are Claude
  delivery channels, not alternative providers.

## Considered Alternatives

### Multi-provider abstraction

Maintain the name-dispatched factory and build adapters for multiple providers
(OpenAI, Gemini, etc.). Rejected because:

- No concrete requirement exists for non-Claude providers in coding workloads.
- The abstraction cost is real but the benefit is speculative.
- Claude's tool-use and extended-thinking capabilities are tightly coupled to
  agent-fox's session architecture.

### OpenAI support

Add an OpenAI-backed adapter alongside Claude. Rejected because:

- OpenAI's tool-use protocol differs enough to require significant adapter
  complexity.
- Quality and capability parity with Claude is not guaranteed.
- Supporting two providers doubles the testing and maintenance surface.

### Gemini support

Add a Gemini-backed adapter. Rejected for similar reasons to OpenAI: protocol
differences, unproven quality for agent workloads, and maintenance burden
without demonstrated demand.

## Consequences

### Positive

- Simplified codebase: the factory is a single `return ClaudeBackend()` with
  no dispatch logic or error paths.
- Contributors have a clear signal that multi-provider work is not on the
  roadmap.
- Fewer lines of dead code to maintain and test.

### Negative

- Cannot use cheaper or faster models from other providers for coding tasks
  without revisiting this decision.
- Contributors who prefer other providers must accept the Claude commitment.

### Future

Non-coding uses of other models (e.g., embeddings, summarisation, search
ranking) remain a future possibility outside this decision's scope. Such uses
would be governed by a separate ADR and would not affect the coding agent
backend layer.
