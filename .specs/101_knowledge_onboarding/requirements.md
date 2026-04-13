# Requirements Document

## Introduction

This specification creates a CLI command that seeds the knowledge store for
existing codebases not originally developed with agent-fox. It composes
existing capabilities (entity graph analysis, ADR/errata/git ingestion) with
new git pattern mining and LLM-powered analysis to produce a thoroughly
populated knowledge store in a single invocation.

## Glossary

- **Onboarding**: The process of populating the knowledge store from existing
  codebase artifacts without running coding sessions.
- **Entity graph**: The tree-sitter-derived structural graph of files, classes,
  functions, and their relationships (Spec 95).
- **Bootstrap ingestion**: Bulk ingestion of ADRs, errata, and git commits
  using existing `KnowledgeIngestor` functions.
- **Git pattern mining**: Deterministic extraction of fragile areas and
  co-change patterns from git history.
- **Fragile area**: A file modified frequently enough to signal instability
  or high churn, represented as a `fragile_area` category fact.
- **Co-change pattern**: A pair of files modified together frequently enough
  to signal coupling, represented as a `pattern` category fact.
- **LLM code analysis**: LLM-powered extraction of architectural decisions,
  conventions, patterns, and anti-patterns from source code files.
- **Documentation mining**: LLM-powered extraction of conventions, design
  rationale, and guidelines from project markdown documentation.
- **Phase**: A discrete step in the onboarding pipeline (entity graph,
  ingestion, mining, code analysis, doc mining, embeddings).
- **OnboardResult**: The summary dataclass returned by the onboarding
  pipeline, containing per-phase counts.
- **Fingerprint keyword**: A structured keyword stored in a fact's keywords
  list used to detect duplicate facts across onboard runs (e.g.
  `onboard:fragile:src/hot.py`).

## Requirements

### Requirement 1: Onboard CLI Command

**User Story:** As a developer adopting agent-fox on an existing codebase,
I want a single command to populate the knowledge store so that AI-driven
analysis has context from the first session.

#### Acceptance Criteria

[101-REQ-1.1] THE system SHALL provide an `onboard` CLI command registered
in the main CLI group.

[101-REQ-1.2] WHEN `onboard` is invoked without `--path`, THE system SHALL
use the current working directory as the project root.

[101-REQ-1.3] WHEN `onboard` is invoked with `--path <dir>`, THE system
SHALL use the specified directory as the project root.

[101-REQ-1.4] WHEN `onboard` completes successfully, THE system SHALL print
a human-readable summary to stderr showing per-phase results AND return exit
code 0.

[101-REQ-1.5] WHEN `--json` is active, THE system SHALL output the
`OnboardResult` as a JSON object to stdout.

[101-REQ-1.6] THE `onboard` command SHALL accept a `--model` option that
specifies the model tier for LLM-powered phases (default: `"STANDARD"`).

#### Edge Cases

[101-REQ-1.E1] IF the specified path does not exist or is not a directory,
THEN THE system SHALL print an error message to stderr AND return exit
code 1.

[101-REQ-1.E2] IF the project root is not a git repository, THEN THE system
SHALL skip git-dependent phases (git commit ingestion, git pattern mining)
AND log a warning.

### Requirement 2: Entity Graph Phase

**User Story:** As the onboarding pipeline, I need to populate the entity
graph so that fact-entity linking, structural queries, and code analysis
file prioritization work immediately.

#### Acceptance Criteria

[101-REQ-2.1] WHEN the onboard command runs without `--skip-entities`, THE
system SHALL call `analyze_codebase(project_root, conn)` AND include the
`AnalysisResult` counts in the `OnboardResult`.

[101-REQ-2.2] WHEN `--skip-entities` is specified, THE system SHALL skip the
entity graph phase AND record `"entities"` in the skipped phases list.

#### Edge Cases

[101-REQ-2.E1] IF entity graph analysis raises an exception, THEN THE system
SHALL log the error, record `"entities"` in the errored phases list, AND
continue with remaining phases.

### Requirement 3: Bootstrap Ingestion Phase

**User Story:** As the onboarding pipeline, I need to ingest ADRs, errata,
and git commits so that existing project knowledge is captured.

#### Acceptance Criteria

[101-REQ-3.1] WHEN the onboard command runs without `--skip-ingestion`, THE
system SHALL call the ADR, errata, and git commit ingestion functions AND
include per-source counts in the `OnboardResult`.

[101-REQ-3.2] WHEN `--skip-ingestion` is specified, THE system SHALL skip
the bootstrap ingestion phase AND record `"ingestion"` in the skipped
phases list.

[101-REQ-3.3] WHEN the project root is not a git repository, THE system
SHALL skip git commit ingestion within this phase AND still run ADR and
errata ingestion.

#### Edge Cases

[101-REQ-3.E1] IF any individual ingestion source (ADRs, errata, or git
commits) raises an exception, THEN THE system SHALL log the error for that
source AND continue with remaining sources.

### Requirement 4: Git Pattern Mining Phase

**User Story:** As a developer, I want the onboarding process to identify
fragile areas and coupling patterns from git history so that agents have
awareness of risky files from the start.

#### Acceptance Criteria

[101-REQ-4.1] WHEN the onboard command runs without `--skip-mining`, THE
system SHALL analyze git history to identify files with change frequency at
or above the fragile area threshold AND create one `fragile_area` fact per
qualifying file.

[101-REQ-4.2] WHEN the onboard command runs without `--skip-mining`, THE
system SHALL analyze git history to identify pairs of files with
co-occurrence count at or above the co-change threshold AND create one
`pattern` fact per qualifying pair.

[101-REQ-4.3] THE git pattern mining function SHALL analyze the most recent
365 days of git history by default, configurable via `--mining-days`.

[101-REQ-4.4] THE git pattern mining function SHALL use a default fragile
area threshold of 20 commits, configurable via `--fragile-threshold`.

[101-REQ-4.5] THE git pattern mining function SHALL use a default co-change
threshold of 5 co-occurrences, configurable via `--cochange-threshold`.

[101-REQ-4.6] THE git pattern mining function SHALL return a `MiningResult`
dataclass with counts of fragile areas created, co-change patterns created,
commits analyzed, and files analyzed.

[101-REQ-4.7] WHEN `--skip-mining` is specified, THE system SHALL skip the
git pattern mining phase AND record `"mining"` in the skipped phases list.

#### Edge Cases

[101-REQ-4.E1] IF the project root is not a git repository, THEN THE system
SHALL skip git pattern mining AND log a warning.

[101-REQ-4.E2] IF git history contains fewer than 10 commits in the analysis
window, THEN THE system SHALL skip pattern mining AND log an info message
explaining insufficient history.

[101-REQ-4.E3] IF a fragile area or co-change fact already exists for the
same file(s), THEN THE system SHALL skip creating a duplicate fact.

### Requirement 5: LLM Code Analysis Phase

**User Story:** As a developer, I want the onboarding process to deeply
analyze source code so that the knowledge store captures architectural
decisions, conventions, patterns, and anti-patterns that are only visible
by reading the code.

#### Acceptance Criteria

[101-REQ-5.1] WHEN the onboard command runs without `--skip-code-analysis`,
THE system SHALL read each source file in the project (matching recognized
extensions for any language: Python, Go, Rust, TypeScript, JavaScript,
Java, C/C++, Ruby, and others), send its content to the LLM, extract
structured facts (decisions, conventions, patterns, anti-patterns, fragile
areas), AND store them in the knowledge store.

[101-REQ-5.2] THE code analysis phase SHALL prioritize files by incoming
import count (most-imported first) using the entity graph, falling back
to scanning source files from disk in alphabetical order only if the
entity graph is empty (e.g., entity graph phase was skipped or no source
files were parseable).

[101-REQ-5.3] THE code analysis phase SHALL use the model tier specified by
the `--model` option (default: `"STANDARD"`) for all LLM calls.

[101-REQ-5.4] WHEN `--skip-code-analysis` is specified, THE system SHALL
skip the LLM code analysis phase AND record `"code_analysis"` in the
skipped phases list.

[101-REQ-5.5] THE code analysis function SHALL return a `CodeAnalysisResult`
dataclass with counts of facts created, files analyzed, and files skipped
AND the result SHALL be included in the `OnboardResult`.

[101-REQ-5.6] THE code analysis phase SHALL skip files that have already
been analyzed in a previous onboard run, identified by the presence of a
fingerprint keyword `onboard:code:{file_path}` on an existing fact.

#### Edge Cases

[101-REQ-5.E1] IF an LLM call fails for a specific file, THEN THE system
SHALL log the error, increment the files-skipped count, AND continue with
remaining files.

[101-REQ-5.E2] IF the entity graph is empty (no file entities exist), THEN
THE system SHALL fall back to scanning source files directly from the
project root (by recognized extensions) AND log an info message.

[101-REQ-5.E3] IF the LLM returns unparseable output for a file, THEN THE
system SHALL log a warning, skip the file, AND continue.

### Requirement 6: Documentation Mining Phase

**User Story:** As a developer, I want the onboarding process to extract
knowledge from project documentation so that conventions, design rationale,
and guidelines captured in markdown files are available to agents.

#### Acceptance Criteria

[101-REQ-6.1] WHEN the onboard command runs without `--skip-doc-mining`,
THE system SHALL scan for markdown documentation files, send each to the
LLM, extract structured facts (conventions, decisions, patterns, guidelines),
AND store them in the knowledge store.

[101-REQ-6.2] THE documentation mining phase SHALL scan: `README.md`,
`CONTRIBUTING.md`, `CHANGELOG.md` at the project root, and all `*.md` files
under `docs/` — excluding `docs/adr/` and `docs/errata/` (which are
handled by bootstrap ingestion).

[101-REQ-6.3] WHEN `--skip-doc-mining` is specified, THE system SHALL skip
the documentation mining phase AND record `"doc_mining"` in the skipped
phases list.

[101-REQ-6.4] THE doc mining function SHALL return a `DocMiningResult`
dataclass with counts of facts created, docs analyzed, and docs skipped
AND the result SHALL be included in the `OnboardResult`.

[101-REQ-6.5] THE documentation mining phase SHALL use the model tier
specified by the `--model` option for all LLM calls.

[101-REQ-6.6] THE documentation mining phase SHALL skip documents that have
already been mined in a previous onboard run, identified by the presence of
a fingerprint keyword `onboard:doc:{doc_path}` on an existing fact.

#### Edge Cases

[101-REQ-6.E1] IF an LLM call fails for a specific document, THEN THE
system SHALL log the error, increment the docs-skipped count, AND continue
with remaining documents.

[101-REQ-6.E2] IF no markdown documentation files are found (after
exclusions), THEN THE system SHALL skip the phase AND log an info message.

[101-REQ-6.E3] IF the LLM returns unparseable output for a document, THEN
THE system SHALL log a warning, skip the document, AND continue.

### Requirement 7: Embedding Generation Phase

**User Story:** As the knowledge system, I need embeddings for all onboarded
facts so that vector search and deduplication work immediately.

#### Acceptance Criteria

[101-REQ-7.1] WHEN the onboard command runs without `--skip-embeddings`, THE
system SHALL generate embeddings for all facts in the knowledge store that
do not yet have embeddings AND include the count in the `OnboardResult`.

[101-REQ-7.2] WHEN `--skip-embeddings` is specified, THE system SHALL skip
the embedding generation phase AND record `"embeddings"` in the skipped
phases list.

#### Edge Cases

[101-REQ-7.E1] IF embedding generation fails for individual facts, THEN THE
system SHALL log a warning for each failure AND continue with remaining
facts (best-effort).

### Requirement 8: Onboard Result and Idempotency

**User Story:** As a developer, I want to re-run onboard safely and see
what was done so that I can verify the knowledge store state.

#### Acceptance Criteria

[101-REQ-8.1] THE `run_onboard()` function SHALL return an `OnboardResult`
dataclass containing: entity graph counts, per-source ingestion counts,
mining counts, code analysis counts, doc mining counts, embedding counts,
lists of skipped and errored phases, and elapsed time in seconds.

[101-REQ-8.2] WHEN the onboard command is run multiple times on the same
codebase, THE system SHALL NOT create duplicate facts — relying on existing
deduplication in ingestion functions, fingerprint-based dedup in git mining,
and fingerprint-based dedup in LLM phases.

[101-REQ-8.3] THE `OnboardResult` dataclass SHALL be serializable to JSON
via `dataclasses.asdict()`.
