# Architecture Introduction

## What Agent-Fox Is

Agent-fox is an autonomous coding-agent orchestrator. You give it specifications
that describe what you want built. It reads those specifications, constructs a
dependency graph of tasks, and drives Claude coding agents through each task —
in parallel, in isolated git worktrees, with structured memory that carries
learning across sessions. You walk away; you come back to working code merged
into your develop branch across dozens of commits.

The system also runs in a second mode — a maintenance daemon called night-shift
— that continuously scans your codebase for technical debt, files GitHub issues
for what it finds, and autonomously fixes the ones you approve.

## What Makes It Different

Most AI coding tools are interactive: you sit in front of them, provide context,
and guide them turn by turn. Agent-fox is designed for unattended operation. This
changes what matters in the architecture.

**Specs replace prompts.** Instead of writing ad-hoc prompts, you author
structured specifications with requirements, design documents, test contracts,
and task plans. These specs are validated, linted, and auto-fixed before any
agent touches them. The system treats specs as contracts — machine-readable,
traceable, and immutable once planning begins. This front-loads the human
judgment and lets the machine execute without improvisation.

**Planning is deterministic.** Specs are compiled into a directed acyclic graph
of tasks with explicit dependency edges. The planner is pure computation — no
LLM inference, no probabilistic decisions. Given the same specs and
configuration, it produces the same graph every time. This means the human can
inspect the plan, predict what will happen, and trust the execution order.

**Agents have roles, not just prompts.** Five conceptual agent roles (Coder,
Skeptic, Oracle, Auditor, Verifier) define distinct responsibilities with
different tool allowlists and output contracts. Review agents cannot modify
code. Implementation agents cannot skip quality checks. The separation of
concerns is enforced by the system, not by prompt suggestions.

**Parallel execution with isolation.** Each task runs in its own git worktree
on its own feature branch. Multiple agents work simultaneously without stepping
on each other. A merge cascade (fast-forward, rebase, merge commit, AI-assisted
conflict resolution) integrates their work into a shared develop branch under
a serializing lock.

**Multi-agent convergence.** Review agents can run multiple instances on the
same task. Their outputs are merged using archetype-specific strategies —
majority-gating for the Skeptic, majority-voting for the Verifier,
worst-verdict-wins for the Auditor. This reduces the variance inherent in
single-shot LLM evaluation.

**Adaptive model routing.** The system predicts which model tier each task
needs (simple, standard, or advanced) using a feature-based assessment pipeline
that starts with heuristics and graduates to trained classifiers as historical
data accumulates. Tasks that fail escalate to stronger models automatically.

**Autonomous maintenance.** Night-shift inverts the workflow: instead of
executing human-authored specs, it discovers problems (linter debt, dead code,
stale dependencies, test gaps) and generates fix specifications on the fly. A
hunt-triage-fix pipeline with deduplication, dependency analysis, and
three-agent validation operates without human intervention.

## How the System Fits Together

The architecture follows the user's workflow: author specs, plan the work,
execute the plan, and optionally let the system maintain the codebase
autonomously. Each phase builds on the previous one and is documented in its
own part of this guide.

### [Part 1: Spec Authoring and Spec Structure](01-spec-authoring.md)

Covers the specification model — the five artifacts that make up a spec (PRD,
requirements, design, test spec, tasks), how they form a traceability chain,
and how the system discovers, validates, and auto-fixes them. This is where
human intent enters the system.

Key concepts: spec directory layout, requirement identifiers, task groups and
subtasks, cross-spec dependency declarations, the static and AI validation
pipeline, the auto-fixer, severity model, the lint command.

### [Part 2: Planning — From Specs to Task Graphs](02-planning.md)

Covers the transformation of specs into an executable plan. The planner reads
task groups and dependency declarations, builds a DAG, injects review and
validation agents at the right positions, and computes a deterministic execution
order.

Key concepts: graph construction phases (base nodes, archetype injection, tag
overrides, cross-spec edges), topological sort with deterministic tie-breaking,
fast mode, file impact analysis, critical path analysis, graph persistence,
runtime patching and hot-load discovery.

### [Part 3: Execution, Session Lifecycle, and Agent Archetypes](03-execution-and-archetypes.md)

Covers the runtime engine — the orchestrator's dispatch loop, how individual
sessions are prepared, executed, harvested, and assessed, and how the five
agent archetypes divide labor. Also covers parallel execution, the circuit
breaker, retry and escalation logic, model routing, workspace isolation, merge
integration, sync barriers, and reset.

Key concepts: streaming pool dispatch, session lifecycle (prepare, execute,
harvest, assess), context assembly (spec docs, memory facts, steering, prior
findings), archetype profiles and mode system, multi-instance convergence,
escalation ladder, merge lock, quality gate.

### [Part 4: Night-Shift Mode](04-night-shift.md)

Covers the autonomous maintenance daemon — how it discovers technical debt
across eight categories, consolidates findings through an LLM critic,
deduplicates against known issues, triages fix ordering with dependency
analysis, and executes a three-agent repair pipeline.

Key concepts: hunt categories, the critic, fingerprint-based deduplication,
batch triage with supersession detection, the fix pipeline (Skeptic, Coder,
Verifier), in-memory spec construction, engine lifecycle, cost limits,
staleness detection.

### [Part 5: Knowledge System Architecture](05-knowledge-system-architecture.md)

The knowledge system is the institutional memory of an autonomous coding
orchestrator. It captures what the coding agent learns during sessions — patterns
discovered, pitfalls encountered, architectural decisions made, conventions established
— and makes that knowledge available to future sessions so the same mistakes are
never repeated and the same discoveries never need to happen twice.

## Reading Order

The documents are numbered to follow the user's workflow:

1. **Spec authoring** — how human intent is captured
2. **Planning** — how intent becomes a machine-readable plan
3. **Execution** — how the plan is carried out
4. **Night-shift** — how the system maintains itself
5. **Knowledge System Architecture** — understand how institutional knowledge is curated

Read them in order for a complete picture, or jump to any part for a specific
topic. Each document is self-contained but cross-references the others where
concepts connect.

The target reader is a senior engineer joining the project who wants to
understand the system's architecture before reading any code. These documents
stay at the conceptual level — no code snippets, no method signatures, no class
hierarchies. For API details, consult the source under `agent_fox/`. For
configuration specifics, see the
[configuration reference](../config-reference.md). For archetype details
beyond what Part 3 covers, see the [archetypes guide](../archetypes.md).
