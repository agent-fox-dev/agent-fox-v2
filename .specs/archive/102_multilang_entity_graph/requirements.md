# Requirements Document

## Introduction

This specification extends the entity graph static analysis (Spec 95) from
Python-only to multi-language support. It introduces a language analyzer
framework, implements analyzers for nine languages, and adds a language
column to the entity_graph schema.

## Glossary

- **Language analyzer**: A component implementing the `LanguageAnalyzer`
  protocol that can parse, extract entities, and extract edges for a specific
  programming language using tree-sitter.
- **Entity mapping**: The correspondence between a language-specific construct
  (e.g., Go struct, Rust trait) and an EntityType value (file, module, class,
  function).
- **Module map**: A language-specific dictionary mapping import identifiers to
  repo-relative file paths, used to resolve import edges to entity graph nodes.
- **Language registry**: A mapping from file extensions to language analyzers,
  used to detect which languages are present and dispatch analysis.
- **Tier 1 language**: A supported language with full entity extraction,
  edge extraction, and import resolution: Python, Go, TypeScript, JavaScript,
  Rust, Java.
- **Tier 2 language**: A supported language with entity extraction and basic
  edge extraction (contains, includes/requires): C, C++, Ruby.

## Requirements

### Requirement 1: Language Analyzer Framework

**User Story:** As a developer extending agent-fox to new languages, I want a
well-defined protocol for language analyzers so that adding support for a new
language is straightforward and consistent.

#### Acceptance Criteria

[102-REQ-1.1] THE system SHALL define a `LanguageAnalyzer` protocol with the
following methods: `extract_entities(tree, rel_path) -> list[Entity]`,
`extract_edges(tree, rel_path, entities, module_map) -> list[EntityEdge]`,
`build_module_map(repo_root, files) -> dict[str, str]`, and a `make_parser()`
factory, AND properties `language_name: str` and `file_extensions: set[str]`.

[102-REQ-1.2] THE system SHALL provide a language registry that maps file
extensions to `LanguageAnalyzer` instances AND SHALL reject registration of
an extension already claimed by another analyzer.

[102-REQ-1.3] THE system SHALL provide a `detect_languages(repo_root)`
function that scans the repository for files matching registered extensions
AND returns the set of `LanguageAnalyzer` instances whose extensions match
at least one file.

[102-REQ-1.4] THE system SHALL provide a `_scan_files(repo_root, extensions)`
function that returns all files matching the given extensions, respecting
`.gitignore` via the `pathspec` library, AND returns paths sorted
alphabetically.

#### Edge Cases

[102-REQ-1.E1] IF a file extension is not registered with any analyzer, THEN
THE system SHALL skip that file during analysis.

[102-REQ-1.E2] IF the project root is not a git repository AND the `pathspec`
library is not available, THEN the `_scan_files()` function SHALL fall back to
a recursive directory walk excluding common non-source directories
(`node_modules`, `.git`, `__pycache__`, `vendor`, `target`, `build`, `dist`).

### Requirement 2: Multi-Language Entity Extraction

**User Story:** As a developer using agent-fox on a Go, Rust, TypeScript, or
Java codebase, I want entity graph analysis to extract structural entities from
my source files so that knowledge linking and graph queries work.

#### Acceptance Criteria

[102-REQ-2.1] WHEN analyzing source files, THE system SHALL extract entities
using the following language-to-EntityType mappings:

| Language | file | module | class | function |
|----------|------|--------|-------|----------|
| Python | `.py` | `__init__.py` packages | `class` | `def` |
| Go | `.go` | `package` decl | `struct`, `interface` | `func`, method |
| Rust | `.rs` | `mod` | `struct`, `enum`, `trait` | `fn` |
| TypeScript | `.ts`, `.tsx` | ES module | `class`, `interface` | function decl, arrow fn |
| JavaScript | `.js`, `.jsx` | ES module | `class` | function decl, arrow fn |
| Java | `.java` | `package` decl | `class`, `interface`, `enum` | method |
| C | `.c`, `.h` | -- | `struct` | function def |
| C++ | `.cpp`, `.hpp`, `.cc`, `.cxx`, `.hh` | `namespace` | `class`, `struct` | function/method |
| Ruby | `.rb` | `module` | `class` | `def` |

[102-REQ-2.2] WHEN extracting entities, THE system SHALL create one `file`
entity per source file with `entity_name` set to the filename and
`entity_path` set to the repo-relative path.

[102-REQ-2.3] WHEN extracting entities, THE system SHALL use qualified names
for nested constructs (e.g., `ClassName.method_name` for methods inside
classes) consistent with the existing Python behavior.

[102-REQ-2.4] WHEN creating entities, THE system SHALL set the `language`
column to the analyzer's `language_name` value.

#### Edge Cases

[102-REQ-2.E1] IF a source file cannot be parsed by tree-sitter (syntax
errors, encoding issues), THEN THE system SHALL log a warning AND skip the
file.

[102-REQ-2.E2] IF a tree-sitter grammar package is not installed for a
registered language, THEN THE system SHALL skip that language AND log an
info message.

### Requirement 3: Multi-Language Edge Extraction

**User Story:** As a developer, I want import relationships and containment
hierarchies extracted from my source files so that graph traversal and
import-count-based file prioritization work across all languages.

#### Acceptance Criteria

[102-REQ-3.1] WHEN analyzing source files, THE system SHALL extract `contains`
edges from parent to child entities (file->class, file->function,
class->method, module->class, namespace->class) for all supported languages.

[102-REQ-3.2] WHEN analyzing source files, THE system SHALL extract `imports`
edges representing import/include/require/use statements, resolving the target
to an entity graph node using the language-specific module map when possible.

[102-REQ-3.3] WHEN analyzing source files for languages that support
inheritance (Python, TypeScript, JavaScript, Java, C++, Ruby), THE system
SHALL extract `extends` edges from the derived class to the base class.

[102-REQ-3.4] WHEN an import target cannot be resolved to an entity graph
node (external dependency, unresolvable path), THE system SHALL silently
skip that import edge.

#### Edge Cases

[102-REQ-3.E1] IF a language does not have a clear inheritance mechanism
(Go, Rust, C), THEN THE system SHALL not extract `extends` edges for that
language.

### Requirement 4: Codebase Analysis Orchestration

**User Story:** As a developer with a mixed-language repository, I want
`analyze_codebase()` to detect and analyze all languages present so that the
entity graph covers the entire codebase.

#### Acceptance Criteria

[102-REQ-4.1] WHEN `analyze_codebase()` is called, THE system SHALL detect
all languages with registered analyzers present in the repository AND analyze
files for each detected language.

[102-REQ-4.2] WHEN analyzing a mixed-language repository, THE system SHALL
aggregate entity and edge counts across all languages into a single
`AnalysisResult`.

[102-REQ-4.3] THE `AnalysisResult` dataclass SHALL include a
`languages_analyzed` field (tuple of language name strings) listing all
languages that were analyzed AND SHALL return the field to the caller, with
a default value of `()` for backward compatibility.

[102-REQ-4.4] WHEN `analyze_codebase()` is called, THE system SHALL
soft-delete entities that were previously created but whose source files no
longer exist, consistent with existing Spec 95 behavior, across all
languages.

[102-REQ-4.5] THE `analyze_codebase()` function SHALL preserve its existing
signature `(repo_root: Path, conn: DuckDBPyConnection) -> AnalysisResult`
AND SHALL remain backward-compatible with all existing callers.

#### Edge Cases

[102-REQ-4.E1] IF no registered language analyzers detect any source files,
THEN THE system SHALL return an `AnalysisResult` with all counts at zero AND
an empty `languages_analyzed` tuple.

[102-REQ-4.E2] IF analysis of one language fails (e.g., grammar crash), THEN
THE system SHALL log the error AND continue with remaining languages.

### Requirement 5: Schema Evolution

**User Story:** As a developer querying the entity graph, I want each entity
tagged with its source language so that I can filter and group entities by
language.

#### Acceptance Criteria

[102-REQ-5.1] THE system SHALL add a nullable `language` VARCHAR column to
the `entity_graph` table via database migration v9.

[102-REQ-5.2] WHEN migration v9 runs on a database with existing entities,
THE system SHALL backfill all existing entity rows with
`language = 'python'`.

[102-REQ-5.3] WHEN new entities are created via `upsert_entities`, THE
system SHALL populate the `language` column with the language value provided
by the caller.

#### Edge Cases

[102-REQ-5.E1] IF migration v9 encounters a table without existing entities,
THEN THE system SHALL complete without error (backfill is a no-op on empty
tables).

### Requirement 6: Backward Compatibility

**User Story:** As an existing user of agent-fox on a Python codebase, I want
the entity graph analysis to continue working identically so that my existing
knowledge graph is not disrupted.

#### Acceptance Criteria

[102-REQ-6.1] WHEN analyzing a Python-only codebase, THE system SHALL produce
the same entities and edges as the pre-Spec-102 implementation.

[102-REQ-6.2] THE Python analyzer SHALL use the same tree-sitter node type
mappings, qualified name construction, module map building, and import
resolution as the original `static_analysis.py`.

[102-REQ-6.3] THE system SHALL NOT modify the signatures or return types of
any existing public functions in `entity_store.py`, `entity_query.py`, or
`entity_linker.py`.
