**Read the entire codebase before writing a single word. Do not skim. Do not skip modules. Every package under `agent_fox/` must be read in full — follow imports to understand how components connect, not just what they do in isolation. Only once you have a complete mental model of the system should you begin writing.**

**Then produce a suite of architecture documents under `docs/architecture/` — split into logical parts (4 is a reasonable number, but let the natural seams of the system guide you). Each document should be self-contained but cross-reference the others where relevant.**

**Scope: cover only the following five areas. Everything else (knowledge store internals, adaptive routing, audit trail, CLI flags, config schema, hooks, reporting commands) is out of scope — do not document it.**
- Spec authoring and spec structure
- Planning (spec → task graph)
- The coding session lifecycle
- Agent archetypes and how they interact
- Night-shift mode

**Structure each document top-down: start with purpose and placement in the system, then the conceptual model, then the key abstractions and their contracts, then how components interact. The sequence across documents should follow the user's workflow: spec authoring → planning → execution → night-shift.**

**Writing rules — enforce these strictly:**
- Stay at the conceptual and architectural level throughout. No code snippets, no method signatures, no class hierarchies. This is an architecture document, not API documentation.
- Explain *why* design decisions exist, not just *what* they are. If something is designed the way it is for a specific reason (isolation, safety, determinism, cost), say so.
- Interface contracts are appropriate: describe what flows between components, what guarantees a component makes to its callers, and what it requires from its dependencies — without quoting source.
- When components interact, describe the interaction protocol and the sequencing, not the call stack.
- Avoid enumerating every config field or every CLI flag. Describe the configuration model's shape and intent; refer readers to the config reference for exhaustive detail.
- Tables are appropriate for comparing alternatives (archetypes, model tiers, hunt categories) but should not be used as a substitute for prose explanation.
- The target reader is a senior engineer joining the project who wants to understand the system's architecture before reading any code. Write for that person.

---
