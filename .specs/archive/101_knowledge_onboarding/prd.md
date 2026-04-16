# PRD: Knowledge Onboarding

## Problem Statement

The agent-fox knowledge system accumulates facts through session-based
extraction: each coding session produces facts that flow through the harvest
pipeline into DuckDB. This means the knowledge store starts **empty** when
agent-fox is used on an existing codebase that was not developed from the
ground up with agent-fox.

The first sessions on a new codebase operate without any knowledge context —
no fragile areas, no conventions, no architectural patterns. This cold-start
problem reduces the quality of AI-driven analysis (nightshift triage, hunt
scanning, knowledge-augmented prompts) until enough sessions have run to
populate the store organically.

The codebase already has latent knowledge in several forms:

- **Structural information** — file/class/function hierarchy extractable via
  tree-sitter (Spec 95 entity graph).
- **ADRs, errata, git commits** — already supported by `KnowledgeIngestor`
  but only run as background ingestion during sessions, not as a bulk
  bootstrapping step.
- **Git history patterns** — frequently-changed files signal fragile areas;
  files changed together signal coupling. This information is not currently
  extracted.
- **Source code** — architectural decisions, conventions, patterns, and
  anti-patterns are embedded in the code itself and can be extracted by
  LLM analysis.
- **Documentation** — README files, contributor guides, and docs/ markdown
  contain conventions, design rationale, and guidelines that are not
  captured by raw ADR ingestion.

## Goals

1. Provide a CLI command (`agent-fox onboard`) that seeds the knowledge store
   for an existing codebase in a single invocation.
2. Run the entity graph analysis (Spec 95) to populate the structural graph.
3. Run existing ingestion functions (ADRs, errata, git commits) in bulk.
4. Extract fragile areas and co-change patterns from git history using
   deterministic heuristics.
5. Analyze source code files with an LLM to extract architectural decisions,
   conventions, patterns, and anti-patterns.
6. Mine project documentation with an LLM to extract conventions, design
   rationale, and guidelines.
7. Generate embeddings for all newly-created facts.
8. Produce a summary of what was onboarded (counts per phase).

## Non-Goals

- **Running knowledge consolidation.** Spec 96's consolidation pipeline
  (merging, promotion, pruning) is a separate concern. Users can run it
  after onboarding if desired.
- **Modifying existing ingestion functions.** The onboard command composes
  existing capabilities; it does not change `KnowledgeIngestor` internals.
- **Replacing session-based extraction.** Onboarding seeds the store;
  ongoing extraction continues to work as before.
- **Interactive onboarding.** The command runs autonomously — no user
  prompts during execution.

## Design Decisions

1. **Quality over cost.** The onboarding pipeline prioritizes thoroughness
   and data quality. LLM-powered phases (code analysis, doc mining) use
   the STANDARD model tier by default, configurable up to ADVANCED. There
   is no budget cap — every source file and documentation file is analyzed.
2. **Sequential phases.** Phases run in order: entity graph, bootstrap
   ingestion, git mining, LLM code analysis, LLM doc mining, embeddings.
   Entity graph must run first (code analysis uses it for file
   prioritization). Embeddings must run last (needs all facts).
3. **Each phase independently skippable.** CLI flags (`--skip-entities`,
   `--skip-ingestion`, `--skip-mining`, `--skip-code-analysis`,
   `--skip-doc-mining`, `--skip-embeddings`) allow users to run only the
   phases they need.
4. **Idempotent by design.** Re-running onboard on the same codebase is
   safe: entity graph uses upsert + soft-delete, ingestion checks for
   existing facts by identifier, git mining checks by fingerprint keyword,
   LLM phases check by fingerprint keyword per file/doc.
5. **Default thresholds for git mining.** Fragile area threshold: 20+
   commits touching a file in 365 days. Co-change threshold: 5+ commits
   modifying both files. These are configurable via CLI options.
6. **Async orchestrator.** `run_onboard()` is async because LLM phases
   use `ai_call()`. The CLI command wraps it with `asyncio.run()`.
7. **Facts tagged with source provenance.** All onboard facts use
   `spec_name="onboard"` with fingerprint keywords encoding the source
   type and file path for deduplication and traceability.
8. **Non-git repositories.** If the project root is not a git repository,
   git-dependent phases (commit ingestion, git mining) are skipped with a
   warning. All other phases still run.
9. **Language-agnostic code analysis.** The code analysis phase works on
   any codebase language (Python, Go, Rust, TypeScript, Java, etc.). It
   scans for source files by a configurable set of recognized extensions.
   The entity graph (Spec 95, extended by Spec 102 to all languages)
   provides import-count-based file prioritization for every supported
   language equally. Files are prioritized by import count (most-imported
   first). If the entity graph is empty (e.g., entity graph phase was
   skipped), files are scanned from disk in alphabetical order. All source
   files are analyzed by default.
10. **Doc mining exclusions.** Documentation mining excludes `docs/adr/`
    and `docs/errata/` since those are already handled by bootstrap
    ingestion. It focuses on README, CONTRIBUTING, and general docs.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 95_entity_graph | 3 | 5 | Calls `analyze_codebase()` for entity graph phase and uses entity graph for code analysis file prioritization; group 3 implements the `analyze_codebase` orchestrator |
