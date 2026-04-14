# Implementation Plan: Multi-Language Entity Graph

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The multi-language entity graph is built in six task groups. Group 1 writes
failing tests. Group 2 creates the framework and refactors Python extraction.
Group 3 implements Go, Rust, and Java analyzers. Group 4 implements
TypeScript/JavaScript, C/C++, and Ruby analyzers. Group 5 integrates
everything into the orchestrator and adds the schema migration. Group 6
verifies wiring.

## Test Commands

- Framework tests: `uv run pytest -q tests/unit/knowledge/test_lang_framework.py`
- Analyzer tests: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py`
- Orchestration tests: `uv run pytest -q tests/unit/knowledge/test_multilang_analysis.py`
- Property tests: `uv run pytest -q tests/property/knowledge/test_multilang_props.py`
- Smoke tests: `uv run pytest -q tests/integration/knowledge/test_multilang_smoke.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/knowledge/test_lang_framework.py`
    - Protocol compliance (TS-102-1)
    - Registry extension mapping (TS-102-2)
    - Language detection (TS-102-3)
    - File scanning with gitignore (TS-102-4)
    - Unregistered extension skipped (TS-102-E3)
    - Non-git repo fallback (TS-102-E4)
    - _Test Spec: TS-102-1, TS-102-2, TS-102-3, TS-102-4, TS-102-E3,
      TS-102-E4_

  - [x] 1.2 Create `tests/unit/knowledge/test_lang_analyzers.py`
    - Python entities and edges (TS-102-5)
    - Go entities and edges (TS-102-6)
    - Rust entities and edges (TS-102-7)
    - TypeScript entities and edges (TS-102-8)
    - JavaScript entities and edges (TS-102-9)
    - Java entities and edges (TS-102-10)
    - C entities and edges (TS-102-11)
    - C++ entities and edges (TS-102-12)
    - Ruby entities and edges (TS-102-13)
    - Module map per language (TS-102-14)
    - Qualified name construction (TS-102-22)
    - Unparseable file (TS-102-E1)
    - Missing grammar package (TS-102-E2)
    - Unresolvable import (TS-102-E7)
    - _Test Spec: TS-102-5 through TS-102-14, TS-102-22, TS-102-E1,
      TS-102-E2, TS-102-E7_

  - [x] 1.3 Create `tests/unit/knowledge/test_multilang_analysis.py`
    - Mixed-language analysis (TS-102-15)
    - Languages analyzed field (TS-102-16)
    - Soft-delete across languages (TS-102-17)
    - Migration v9 (TS-102-18)
    - Language column backfill (TS-102-19)
    - New entity language tag (TS-102-20)
    - Python backward compatibility (TS-102-21)
    - No source files found (TS-102-E5)
    - Analyzer crash isolation (TS-102-E6)
    - _Test Spec: TS-102-15 through TS-102-21, TS-102-E5, TS-102-E6_

  - [x] 1.4 Create `tests/property/knowledge/test_multilang_props.py`
    - Entity validity (TS-102-P1)
    - Edge referential integrity (TS-102-P2)
    - Upsert idempotency (TS-102-P3)
    - Scan subset (TS-102-P4)
    - _Test Spec: TS-102-P1 through TS-102-P4_

  - [x] 1.5 Create `tests/integration/knowledge/test_multilang_smoke.py`
    - Full multi-language analysis (TS-102-SMOKE-1)
    - Python backward compatibility E2E (TS-102-SMOKE-2)
    - Incremental analysis with language changes (TS-102-SMOKE-3)
    - _Test Spec: TS-102-SMOKE-1 through TS-102-SMOKE-3_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Language analyzer framework and Python refactoring
  - [ ] 2.1 Create `agent_fox/knowledge/lang/__init__.py`
    - Package init with exports
  - [ ] 2.2 Create `agent_fox/knowledge/lang/base.py`
    - `LanguageAnalyzer` protocol with `language_name`, `file_extensions`,
      `make_parser()`, `extract_entities()`, `extract_edges()`,
      `build_module_map()`
    - _Requirements: 102-REQ-1.1_
  - [ ] 2.3 Create `agent_fox/knowledge/lang/registry.py`
    - `LanguageRegistry` class with `register()`, `get_analyzer()`,
      `all_analyzers()`
    - `get_default_registry()` factory
    - `detect_languages(repo_root)` function
    - `_scan_files(repo_root, extensions)` function with .gitignore support
      and non-git fallback
    - _Requirements: 102-REQ-1.2, 102-REQ-1.3, 102-REQ-1.4, 102-REQ-1.E1,
      102-REQ-1.E2_
  - [ ] 2.4 Create `agent_fox/knowledge/lang/python_lang.py`
    - `PythonAnalyzer` class implementing `LanguageAnalyzer`
    - Refactor `_extract_entities`, `_extract_edges`, `_build_module_map`,
      `_make_parser` from `static_analysis.py` into this module
    - Preserve exact behavior for backward compatibility
    - _Requirements: 102-REQ-6.1, 102-REQ-6.2_
  - [ ] 2.5 Refactor `agent_fox/knowledge/static_analysis.py`
    - Replace inline Python extraction with `PythonAnalyzer` usage
    - Update `_scan_python_files` to use `_scan_files` from registry
    - Preserve `analyze_codebase()` signature and behavior
    - _Requirements: 102-REQ-4.5, 102-REQ-6.1_

  - [ ] 2.V Verify task group 2
    - [ ] Framework tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_framework.py`
    - [ ] Python analyzer tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k python`
    - [ ] Python backward compat tests pass: `uv run pytest -q tests/unit/knowledge/test_multilang_analysis.py -k backward`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/lang/ agent_fox/knowledge/static_analysis.py`

- [ ] 3. Go, Rust, and Java analyzers
  - [ ] 3.1 Create `agent_fox/knowledge/lang/go_lang.py`
    - `GoAnalyzer` class implementing `LanguageAnalyzer`
    - Entity extraction: struct, interface, function, method
    - Edge extraction: contains, imports (package resolution)
    - Module map: package directory mapping
    - _Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1_
  - [ ] 3.2 Create `agent_fox/knowledge/lang/rust_lang.py`
    - `RustAnalyzer` class implementing `LanguageAnalyzer`
    - Entity extraction: struct, enum, trait, function, impl methods
    - Edge extraction: contains, imports (use declarations)
    - Module map: crate-relative mod resolution
    - _Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1_
  - [ ] 3.3 Create `agent_fox/knowledge/lang/java_lang.py`
    - `JavaAnalyzer` class implementing `LanguageAnalyzer`
    - Entity extraction: class, interface, enum, method, package
    - Edge extraction: contains, imports, extends, implements
    - Module map: fully qualified class name to file path
    - _Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3_
  - [ ] 3.4 Register Go, Rust, Java analyzers in default registry
  - [ ] 3.5 Add `tree-sitter-go`, `tree-sitter-rust`, `tree-sitter-java`
    to `pyproject.toml`

  - [ ] 3.V Verify task group 3
    - [ ] Go analyzer tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k go`
    - [ ] Rust analyzer tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k rust`
    - [ ] Java analyzer tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k java`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/lang/`

- [ ] 4. TypeScript/JavaScript, C/C++, and Ruby analyzers
  - [ ] 4.1 Create `agent_fox/knowledge/lang/typescript_lang.py`
    - `TypeScriptAnalyzer` class (`.ts`, `.tsx`)
    - `JavaScriptAnalyzer` class (`.js`, `.jsx`)
    - Shared extraction logic for ES module patterns
    - Entity extraction: class, interface (TS only), function, arrow function
    - Edge extraction: contains, imports, extends
    - Module map: relative path resolution with extension guessing
    - _Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3_
  - [ ] 4.2 Create `agent_fox/knowledge/lang/c_lang.py`
    - `CAnalyzer` class (`.c`, `.h`)
    - `CppAnalyzer` class (`.cpp`, `.hpp`, `.cc`, `.cxx`, `.hh`)
    - Entity extraction: struct (C), class/struct/namespace (C++), function
    - Edge extraction: contains, includes, extends (C++ only)
    - Module map: header path resolution
    - _Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3,
      102-REQ-3.E1_
  - [ ] 4.3 Create `agent_fox/knowledge/lang/ruby_lang.py`
    - `RubyAnalyzer` class (`.rb`)
    - Entity extraction: module, class, method
    - Edge extraction: contains, require/require_relative, extends
    - Module map: require path resolution
    - _Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3_
  - [ ] 4.4 Register TS, JS, C, C++, Ruby analyzers in default registry
  - [ ] 4.5 Add `tree-sitter-javascript`, `tree-sitter-typescript`,
    `tree-sitter-c`, `tree-sitter-cpp`, `tree-sitter-ruby`
    to `pyproject.toml`

  - [ ] 4.V Verify task group 4
    - [ ] TypeScript analyzer tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k typescript`
    - [ ] JavaScript analyzer tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k javascript`
    - [ ] C analyzer tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k "c_entities"`
    - [ ] C++ analyzer tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k cpp`
    - [ ] Ruby analyzer tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k ruby`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/lang/`

- [ ] 5. Schema migration and orchestrator integration
  - [ ] 5.1 Add migration v9 to `agent_fox/knowledge/migrations.py`
    - Add nullable `language` VARCHAR column to `entity_graph`
    - Backfill existing entities with `language = 'python'`
    - _Requirements: 102-REQ-5.1, 102-REQ-5.2, 102-REQ-5.E1_
  - [ ] 5.2 Update `agent_fox/knowledge/entity_store.py`
    - `upsert_entities()`: accept optional `language` parameter, write to
      column on insert, update NULL language on existing entities
    - `_row_to_entity()`: read `language` column (ignored in Entity
      dataclass but stored in DB)
    - _Requirements: 102-REQ-5.3, 102-REQ-6.3_
  - [ ] 5.3 Update `agent_fox/knowledge/entities.py`
    - Add `languages_analyzed: tuple[str, ...] = ()` to `AnalysisResult`
    - _Requirements: 102-REQ-4.3_
  - [ ] 5.4 Update `agent_fox/knowledge/static_analysis.py`
    - Refactor `analyze_codebase()` to use `detect_languages()` and
      dispatch to per-language analyzers
    - Aggregate entity/edge counts across all languages
    - Pass language name to `upsert_entities()`
    - Populate `languages_analyzed` in `AnalysisResult`
    - Isolate per-language failures (try/except per analyzer)
    - _Requirements: 102-REQ-4.1, 102-REQ-4.2, 102-REQ-4.4, 102-REQ-4.5,
      102-REQ-4.E1, 102-REQ-4.E2_

  - [ ] 5.V Verify task group 5
    - [ ] Orchestration tests pass: `uv run pytest -q tests/unit/knowledge/test_multilang_analysis.py`
    - [ ] Property tests pass: `uv run pytest -q tests/property/knowledge/test_multilang_props.py`
    - [ ] Smoke tests pass: `uv run pytest -q tests/integration/knowledge/test_multilang_smoke.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/ tests/`

- [ ] 6. Wiring verification
  - [ ] 6.1 Trace execution paths from design.md
    - Path 1: analyze_codebase -> detect_languages -> per-language dispatch
      -> upsert -> soft-delete -> AnalysisResult
    - Path 2: Python-only codebase -> PythonAnalyzer -> identical output
    - Path 3: Mixed-language -> all analyzers -> aggregated result
    - Confirm no function in the chain is a stub

  - [ ] 6.2 Verify cross-module imports
    - `static_analysis.py` imports from `lang.registry` and `lang.base`
    - Each analyzer imports from `lang.base`
    - `registry.py` imports all analyzer classes
    - No circular imports introduced

  - [ ] 6.3 Run integration smoke tests
    - TS-102-SMOKE-1 through TS-102-SMOKE-3 pass
    - `uv run pytest -q tests/integration/knowledge/test_multilang_smoke.py`

  - [ ] 6.4 Stub / dead-code audit
    - Search touched files for stubs, TODOs, NotImplementedError
    - Verify no dead code introduced
    - Verify `_scan_python_files` is either removed or delegates to
      `_scan_files`

  - [ ] 6.5 Backward compatibility verification
    - Run existing Spec 95 tests: `uv run pytest -q tests/unit/knowledge/test_static_analysis.py tests/unit/knowledge/test_entity_store.py tests/unit/knowledge/test_entity_query.py tests/unit/knowledge/test_entity_linker.py`
    - All must pass without modification

  - [ ] 6.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live
    - [ ] All cross-module imports work without circular dependencies
    - [ ] All existing Spec 95 tests pass unchanged
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 102-REQ-1.1 | TS-102-1 | 2.2 | test_lang_framework::test_protocol_compliance |
| 102-REQ-1.2 | TS-102-2 | 2.3 | test_lang_framework::test_registry_mapping |
| 102-REQ-1.3 | TS-102-3 | 2.3 | test_lang_framework::test_language_detection |
| 102-REQ-1.4 | TS-102-4 | 2.3 | test_lang_framework::test_file_scanning |
| 102-REQ-1.E1 | TS-102-E3 | 2.3 | test_lang_framework::test_unregistered_extension |
| 102-REQ-1.E2 | TS-102-E4 | 2.3 | test_lang_framework::test_non_git_fallback |
| 102-REQ-2.1 | TS-102-5 through TS-102-13 | 2.4, 3.1-3.3, 4.1-4.3 | test_lang_analyzers::test_*_entities |
| 102-REQ-2.2 | TS-102-5 | 2.4 | test_lang_analyzers::test_python_entities |
| 102-REQ-2.3 | TS-102-22 | 2.4, 3.1-3.3, 4.1-4.3 | test_lang_analyzers::test_qualified_names |
| 102-REQ-2.4 | TS-102-20 | 5.2, 5.4 | test_multilang_analysis::test_entity_language_tag |
| 102-REQ-2.E1 | TS-102-E1 | 2.4 | test_lang_analyzers::test_unparseable_file |
| 102-REQ-2.E2 | TS-102-E2 | 2.3 | test_lang_analyzers::test_missing_grammar |
| 102-REQ-3.1 | TS-102-5 through TS-102-13 | 2.4, 3.1-3.3, 4.1-4.3 | test_lang_analyzers::test_*_edges |
| 102-REQ-3.2 | TS-102-14 | 2.4, 3.1-3.3, 4.1-4.3 | test_lang_analyzers::test_module_map |
| 102-REQ-3.3 | TS-102-8, TS-102-9, TS-102-10, TS-102-12, TS-102-13 | 3.3, 4.1-4.3 | test_lang_analyzers::test_*_extends |
| 102-REQ-3.4 | TS-102-E7 | 2.4, 3.1-3.3, 4.1-4.3 | test_lang_analyzers::test_unresolvable_import |
| 102-REQ-3.E1 | TS-102-6, TS-102-7, TS-102-11 | 3.1, 3.2, 4.2 | test_lang_analyzers::test_no_extends |
| 102-REQ-4.1 | TS-102-15 | 5.4 | test_multilang_analysis::test_mixed_language |
| 102-REQ-4.2 | TS-102-15 | 5.4 | test_multilang_analysis::test_mixed_language |
| 102-REQ-4.3 | TS-102-16 | 5.3, 5.4 | test_multilang_analysis::test_languages_analyzed |
| 102-REQ-4.4 | TS-102-17 | 5.4 | test_multilang_analysis::test_soft_delete_across_languages |
| 102-REQ-4.5 | TS-102-21 | 2.5, 5.4 | test_multilang_analysis::test_backward_compat |
| 102-REQ-4.E1 | TS-102-E5 | 5.4 | test_multilang_analysis::test_no_source_files |
| 102-REQ-4.E2 | TS-102-E6 | 5.4 | test_multilang_analysis::test_analyzer_crash |
| 102-REQ-5.1 | TS-102-18 | 5.1 | test_multilang_analysis::test_migration_v9 |
| 102-REQ-5.2 | TS-102-19 | 5.1 | test_multilang_analysis::test_backfill |
| 102-REQ-5.3 | TS-102-20 | 5.2 | test_multilang_analysis::test_entity_language_tag |
| 102-REQ-5.E1 | TS-102-18 | 5.1 | test_multilang_analysis::test_migration_v9 |
| 102-REQ-6.1 | TS-102-21 | 2.4, 2.5 | test_multilang_analysis::test_backward_compat |
| 102-REQ-6.2 | TS-102-5 | 2.4 | test_lang_analyzers::test_python_entities |
| 102-REQ-6.3 | TS-102-21 | 5.2 | test_multilang_analysis::test_backward_compat |
| Property 1 | TS-102-P1 | 2.4, 3.1-3.3, 4.1-4.3 | test_multilang_props::test_entity_validity |
| Property 2 | TS-102-P2 | 2.4, 3.1-3.3, 4.1-4.3 | test_multilang_props::test_edge_integrity |
| Property 3 | TS-102-P3 | 5.4 | test_multilang_props::test_upsert_idempotency |
| Property 4 | TS-102-P4 | 2.3 | test_multilang_props::test_scan_subset |
| Path 1 | TS-102-SMOKE-1 | 5.4 | test_multilang_smoke::test_full_analysis |
| Path 2 | TS-102-SMOKE-2 | 2.4, 2.5 | test_multilang_smoke::test_python_compat |
| Path 3 | TS-102-SMOKE-3 | 5.4 | test_multilang_smoke::test_incremental |

## Notes

- **Tree-sitter grammar availability:** Before implementing each language
  analyzer, verify the grammar package exists on PyPI with tree-sitter>=0.23
  compatibility. If unavailable, defer that language and protect with the
  graceful-skip behavior (102-REQ-2.E2).
- **Python refactoring:** The PythonAnalyzer must produce byte-for-byte
  identical entity/edge output as the original `static_analysis.py` code.
  Test this by comparing natural keys and edge triples.
- **Sentinel edge resolution:** The existing sentinel pattern (`path:` and
  `class:` prefixed IDs) is reused across all languages. Cross-language
  sentinel resolution is supported (e.g., a TS import resolving to a JS
  file entity).
- **DuckDB test fixtures:** All tests requiring a database connection should
  use the shared DuckDB fixture with migrations through v9 applied.
- **Hypothesis for property tests:** Use
  `suppress_health_check=[HealthCheck.function_scoped_fixture]` for
  property tests using pytest fixtures.
- **File scanning:** The `_scan_files()` function uses `pathspec` for
  .gitignore support (same library already used by the existing code). In
  non-git directories, it falls back to `Path.rglob()` with directory
  exclusions.
- **Existing Spec 95 tests:** These tests must continue to pass without
  modification. They test the `analyze_codebase()` function and entity_store
  operations. The refactoring must not break any of them.
