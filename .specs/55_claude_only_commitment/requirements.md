# Requirements Document

## Introduction

This specification formalises agent-fox's commitment to Claude as the exclusive
LLM provider for all coding agent workloads. It covers documentation (ADR),
code simplification (removing dead extensibility), and policy enforcement
(lint/test guards).

## Glossary

- **ADR** — Architecture Decision Record; a structured document in `docs/adr/`
  capturing a significant design decision, its context, and consequences.
- **AgentBackend** — The runtime-checkable protocol in
  `agent_fox/session/backends/protocol.py` that defines the contract for
  backend adapters.
- **ClaudeBackend** — The sole production implementation of `AgentBackend`,
  wrapping `claude_code_sdk`.
- **Backend factory** — The `get_backend()` function in
  `agent_fox/session/backends/__init__.py` that instantiates a backend by name.
- **Claude platform** — Any delivery channel for Anthropic models: direct API,
  Vertex AI (GCP), or Bedrock (AWS).
- **Coding agent** — Any archetype that participates in the spec-driven task
  graph (coder, oracle, skeptic, verifier, auditor, librarian, cartographer,
  coordinator).

## Requirements

### Requirement 1: Architecture Decision Record

**User Story:** As a contributor, I want a formal ADR documenting the
Claude-only decision, so that I don't spend effort on multi-provider support.

#### Acceptance Criteria

[55-REQ-1.1] THE system SHALL include an ADR in `docs/adr/` titled
"Use Claude exclusively for coding agents" that states Claude is the only
supported LLM provider for coding agent workloads.

[55-REQ-1.2] THE ADR SHALL list the considered alternatives (multi-provider
abstraction, OpenAI support, Gemini support) and the reasons they were
rejected.

[55-REQ-1.3] THE ADR SHALL note that non-coding uses of other models (e.g.,
embeddings, summarisation) remain a future possibility outside this decision's
scope.

#### Edge Cases

[55-REQ-1.E1] IF the next available ADR number conflicts with an existing file,
THEN THE system SHALL use the next available non-conflicting number.

### Requirement 2: Backend Factory Simplification

**User Story:** As a developer, I want the backend factory to reflect the
Claude-only commitment, so that the code doesn't suggest unused extensibility.

#### Acceptance Criteria

[55-REQ-2.1] THE `get_backend()` function SHALL return a `ClaudeBackend`
instance without accepting a backend name parameter.

[55-REQ-2.2] THE `get_backend()` function SHALL NOT raise `ValueError` for
unrecognised backend names (the name parameter is removed).

[55-REQ-2.3] WHEN any caller previously passed a name argument to
`get_backend()`, THE system SHALL be updated so that no call site passes a
name argument.

#### Edge Cases

[55-REQ-2.E1] IF test code depends on `get_backend("claude")`, THEN THE
system SHALL update those call sites to use `get_backend()` with no arguments.

### Requirement 3: Protocol Preservation

**User Story:** As a test author, I want the `AgentBackend` protocol to remain
available, so that I can inject mock backends in tests.

#### Acceptance Criteria

[55-REQ-3.1] THE `AgentBackend` protocol in `protocol.py` SHALL remain
unchanged and continue to be exported from the `backends` package.

[55-REQ-3.2] THE `AgentBackend` protocol SHALL include a docstring stating
that `ClaudeBackend` is the only production implementation and that the
protocol exists for test mock injection.

#### Edge Cases

[55-REQ-3.E1] IF a test creates a mock implementing `AgentBackend`, THEN THE
mock SHALL still pass `isinstance(mock, AgentBackend)` checks.

### Requirement 4: Platform Client Factory Preservation

**User Story:** As an operator deploying on Vertex AI or Bedrock, I want the
platform-aware client factory to remain functional, so that I can run
agent-fox on my cloud platform.

#### Acceptance Criteria

[55-REQ-4.1] THE platform-aware client factory in `core/client.py` SHALL
continue to support Vertex AI, Bedrock, and direct Anthropic API access.

[55-REQ-4.2] THE client factory SHALL NOT be modified by this spec except
for adding a docstring note that all three platforms serve Claude models.

### Requirement 5: Documentation Updates

**User Story:** As a user, I want the README and docs to clearly state that
agent-fox is Claude-only, so that I understand the product's positioning.

#### Acceptance Criteria

[55-REQ-5.1] THE `README.md` SHALL include a statement in its introduction
or "Overview" section that agent-fox is built exclusively for Claude.

[55-REQ-5.2] THE `docs/memory.md` or an appropriate documentation file SHALL
NOT be modified to add this decision (it belongs in the ADR).
