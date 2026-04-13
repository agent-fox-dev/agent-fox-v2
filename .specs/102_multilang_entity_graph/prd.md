# PRD: Multi-Language Entity Graph

## Problem Statement

The entity graph static analysis (Spec 95) only supports Python. It extracts
file, module, class, and function entities along with contains, imports, and
extends edges -- but exclusively from `.py` files using the
`tree-sitter-python` grammar.

This limitation means the entity graph is empty for non-Python codebases (Go,
Rust, TypeScript, Java, etc.). When empty, downstream consumers lose
functionality:

- **Spec 101 (Knowledge Onboarding):** The code analysis phase prioritizes
  files by incoming import count from the entity graph. Without multi-language
  support, non-Python codebases fall back to unordered disk scanning, losing
  the most-imported-first prioritization that improves LLM analysis quality.
- **Spec 96 (Knowledge Consolidation):** Entity-based fact linking only works
  for Python files, leaving facts from other languages unlinked.
- **Graph queries:** `find_related_facts()` returns nothing for non-Python
  files, making topology-based fact retrieval useless.

The entity graph schema (entity_graph, entity_edges, fact_entities tables) is
already language-agnostic. Only the extraction layer in `static_analysis.py`
is Python-specific. The fix is to create a multi-language extraction framework
and implement analyzers for each supported language.

## Goals

1. Create a language analyzer framework with a common protocol for entity and
   edge extraction across languages.
2. Refactor the existing Python analysis into the framework without changing
   behavior.
3. Implement analyzers for Go, Rust, TypeScript, JavaScript, Java, C, C++,
   and Ruby using tree-sitter grammars.
4. Support mixed-language repositories -- analyze all detected languages in a
   single `analyze_codebase()` call.
5. Add a `language` column to the entity_graph table for queryability.
6. Maintain full backward compatibility with existing Python analysis and all
   callers of `analyze_codebase()`.

## Non-Goals

- **External dependency resolution.** Import edges are resolved within the
  repository boundary only. Imports referencing external packages (pip
  packages, npm modules, Go modules outside the repo, Maven artifacts) are
  not resolved to entity graph nodes.
- **Build system integration.** No parsing of Cargo.toml, go.mod,
  package.json, pom.xml, or similar build configuration files.
- **Language-specific semantic analysis.** No type inference, control flow
  analysis, or semantic understanding beyond structural extraction.
- **New entity or edge types.** The existing EntityType (file, module, class,
  function) and EdgeType (contains, imports, extends) values are reused.
  Language-specific constructs are mapped to the nearest existing type.
- **Tree-sitter grammar development.** Uses existing published tree-sitter
  grammar packages. Does not create or modify grammars.

## Design Decisions

1. **Language analyzer protocol.** Each supported language implements a
   `LanguageAnalyzer` protocol that provides file scanning, entity extraction,
   edge extraction, and module map construction. This enables adding new
   languages without modifying the framework.

2. **Registry pattern.** A central registry maps file extensions to language
   analyzers. `analyze_codebase()` detects languages by scanning for files
   with registered extensions, then dispatches to the appropriate analyzers.

3. **Conservative entity mapping.** Language-specific constructs are mapped to
   the four existing entity types rather than creating new ones:
   - Go structs/interfaces -> `class`
   - Rust structs/enums/traits -> `class`
   - Java interfaces/enums -> `class`
   - Go packages / Rust modules / Java packages -> `module`
   - C++ namespaces -> `module`

4. **Best-effort import resolution.** Import edges are resolved using
   language-specific module maps built from the repository structure. Imports
   that cannot be resolved (external dependencies, dynamic imports) are
   silently skipped. This matches the existing Python behavior.

5. **Required grammar dependencies.** Tree-sitter grammar packages for all
   supported languages are added as required dependencies in pyproject.toml.
   This ensures multi-language support works out of the box.

6. **Single analyze_codebase() entry point.** The existing function signature
   is preserved. Internally it dispatches to per-language analyzers and
   aggregates results. Callers see no API change.

7. **Language column via migration.** A nullable `language` VARCHAR column is
   added to the entity_graph table in migration v9. Existing rows (Python
   entities) are backfilled with `'python'`. New entities are tagged with
   their language at creation time.

8. **Shared file scanning.** A generic `_scan_files()` function replaces the
   Python-specific `_scan_python_files()`, accepting any set of extensions
   and using `pathspec` for .gitignore-aware scanning. The Python analyzer
   calls this with `{".py"}`.

9. **AnalysisResult extension.** `AnalysisResult` gains an optional
   `languages_analyzed` field (tuple of language names) with a default of
   `()` for backward compatibility.

10. **Module layout.** Language analyzers live in `agent_fox/knowledge/lang/`
    with one module per language (or language family). This keeps
    `static_analysis.py` focused on orchestration.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 95_entity_graph | 3 | 2 | Refactors `static_analysis.py` and extends `entities.py` from Spec 95 group 3; group 3 is where the static analysis module and entity models were implemented |
