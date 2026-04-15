# Implementation Plan: Additional Language Analyzers

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Each of the four new languages (C#, Elixir, Kotlin, Dart) is implemented as
an independent task group after the initial test-writing group. Languages are
ordered by dependency complexity: C# and Kotlin have established tree-sitter
grammars and familiar OOP patterns; Elixir has unique semantics (no classes);
Dart uses a community fork grammar. A checkpoint after all four languages
precedes the final wiring verification.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py tests/property/knowledge/test_multilang_props.py -k "107 or csharp or elixir or kotlin or dart"`
- Unit tests: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py`
- Property tests: `uv run pytest -q tests/property/knowledge/test_multilang_props.py`
- Integration tests: `uv run pytest -q tests/integration/knowledge/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Add C# unit tests to test_lang_analyzers.py
    - TestCSharpAnalyzerProperties (TS-107-1)
    - TestCSharpEntitiesAndEdges (TS-107-2, TS-107-3)
    - TestCSharpModuleMap (TS-107-4)
    - TestCSharpExternalUsingSkipped (TS-107-E1)
    - TestCSharpMultipleNamespaces (TS-107-E2)
    - _Test Spec: TS-107-1 through TS-107-4, TS-107-E1, TS-107-E2_

  - [x] 1.2 Add Elixir unit tests to test_lang_analyzers.py
    - TestElixirAnalyzerProperties (TS-107-5)
    - TestElixirEntitiesAndEdges (TS-107-6, TS-107-7)
    - TestElixirModuleMap (TS-107-8)
    - TestElixirNestedDefmodule (TS-107-E3)
    - TestElixirExternalImportSkipped (TS-107-E4)
    - _Test Spec: TS-107-5 through TS-107-8, TS-107-E3, TS-107-E4_

  - [x] 1.3 Add Kotlin unit tests to test_lang_analyzers.py
    - TestKotlinAnalyzerProperties (TS-107-9)
    - TestKotlinEntitiesAndEdges (TS-107-10, TS-107-11)
    - TestKotlinModuleMap (TS-107-12)
    - TestKotlinCompanionObjectMethods (TS-107-E5)
    - TestKotlinExternalImportSkipped (TS-107-E6)
    - _Test Spec: TS-107-9 through TS-107-12, TS-107-E5, TS-107-E6_

  - [x] 1.4 Add Dart unit tests to test_lang_analyzers.py
    - TestDartAnalyzerProperties (TS-107-13)
    - TestDartEntitiesAndEdges (TS-107-14, TS-107-16)
    - TestDartLibraryDirective (TS-107-15)
    - TestDartModuleMap (TS-107-17)
    - TestDartNoLibraryDirective (TS-107-E8)
    - TestDartSdkImportSkipped (TS-107-E7)
    - _Test Spec: TS-107-13 through TS-107-17, TS-107-E7, TS-107-E8_

  - [x] 1.5 Add property tests to test_multilang_props.py
    - TS-107-P1: Protocol conformance (all four)
    - TS-107-P2: C# entity validity
    - TS-107-P3: Kotlin entity validity
    - TS-107-P4: Dart entity validity
    - TS-107-P5: Elixir no-class invariant
    - TS-107-P6: Extension uniqueness
    - TS-107-P7: Module map path format
    - Add language-specific keyword filters for strategies
    - _Test Spec: TS-107-P1 through TS-107-P7_

  - [x] 1.6 Add registry and integration tests
    - TestRegistryIntegration (TS-107-18)
    - TestDetectLanguages (TS-107-19)
    - TestGrammarNotInstalled (TS-107-E9)
    - Integration smoke test (TS-107-SMOKE-1)
    - _Test Spec: TS-107-18, TS-107-19, TS-107-E9, TS-107-SMOKE-1_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/`

- [x] 2. Add dependencies and implement C# analyzer
  - [x] 2.1 Add `tree-sitter-c-sharp>=0.23` to pyproject.toml dependencies
    - Run `uv sync` to install
    - _Requirements: 107-REQ-6.1_

  - [x] 2.2 Create `agent_fox/knowledge/lang/csharp_lang.py`
    - Implement `CSharpAnalyzer` class with protocol properties
    - Implement `make_parser()` using `tree_sitter_c_sharp`
    - _Requirements: 107-REQ-1.1, 107-REQ-1.2_

  - [x] 2.3 Implement C# entity extraction
    - Extract FILE, MODULE (namespace), CLASS (class/struct/interface/enum/record),
      FUNCTION (methods with qualified names)
    - Handle multiple namespaces per file
    - _Requirements: 107-REQ-1.3, 107-REQ-1.E2_

  - [x] 2.4 Implement C# edge extraction and module map
    - CONTAINS edges (namespace->class, class->method)
    - IMPORTS edges from `using` directives
    - EXTENDS edges from `:` inheritance clause
    - Module map: namespace.class -> file path
    - Skip unresolvable using directives silently
    - _Requirements: 107-REQ-1.4, 107-REQ-1.5, 107-REQ-1.E1_

  - [x] 2.5 Register CSharpAnalyzer in registry.py
    - Add `_try_register(registry, CSharpAnalyzer, "csharp")` in
      `_build_default_registry()`
    - Handle ImportError gracefully
    - _Requirements: 107-REQ-5.1, 107-REQ-5.3_

  - [x] 2.V Verify task group 2
    - [x] C# spec tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k "CSharp"`
    - [x] C# property tests pass: `uv run pytest -q tests/property/knowledge/test_multilang_props.py -k "csharp"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`
    - [x] Requirements 107-REQ-1.* acceptance criteria met

- [x] 3. Implement Elixir analyzer
  - [x] 3.1 Add `tree-sitter-elixir>=0.3.4` to pyproject.toml dependencies
    - Run `uv sync` to install
    - _Requirements: 107-REQ-6.1_

  - [x] 3.2 Create `agent_fox/knowledge/lang/elixir_lang.py`
    - Implement `ElixirAnalyzer` class with protocol properties
    - Implement `make_parser()` using `tree_sitter_elixir`
    - _Requirements: 107-REQ-2.1, 107-REQ-2.2_

  - [x] 3.3 Implement Elixir entity extraction
    - Extract FILE, MODULE (defmodule with dotted names),
      FUNCTION (def/defp with qualified names)
    - No CLASS entities
    - Handle nested defmodule with fully-qualified names
    - Note: Elixir tree-sitter represents keywords as `call` nodes
    - _Requirements: 107-REQ-2.3, 107-REQ-2.4, 107-REQ-2.E1_

  - [x] 3.4 Implement Elixir edge extraction and module map
    - CONTAINS edges (file->module, module->function)
    - IMPORTS edges from `use`, `import`, `alias`, `require` (all `call` nodes)
    - No EXTENDS edges
    - Module map: dotted module name -> file path (MyApp.Foo -> lib/my_app/foo.ex)
    - Skip unresolvable imports silently
    - _Requirements: 107-REQ-2.5, 107-REQ-2.6, 107-REQ-2.E2_

  - [x] 3.5 Register ElixirAnalyzer in registry.py
    - Add `_try_register(registry, ElixirAnalyzer, "elixir")`
    - _Requirements: 107-REQ-5.1, 107-REQ-5.3_

  - [x] 3.V Verify task group 3
    - [x] Elixir spec tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k "Elixir"`
    - [x] Elixir property tests pass: `uv run pytest -q tests/property/knowledge/test_multilang_props.py -k "elixir"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`
    - [x] Requirements 107-REQ-2.* acceptance criteria met

- [x] 4. Implement Kotlin analyzer
  - [x] 4.1 Add `tree-sitter-kotlin>=1.0` to pyproject.toml dependencies
    - Run `uv sync` to install
    - _Requirements: 107-REQ-6.1_

  - [x] 4.2 Create `agent_fox/knowledge/lang/kotlin_lang.py`
    - Implement `KotlinAnalyzer` class with protocol properties
    - Implement `make_parser()` using `tree_sitter_kotlin`
    - _Requirements: 107-REQ-3.1, 107-REQ-3.2_

  - [x] 4.3 Implement Kotlin entity extraction
    - Extract FILE, MODULE (package), CLASS (class/interface/object/enum class/data class),
      FUNCTION (fun with qualified names)
    - Companion object methods qualified as `ClassName.methodName`
    - _Requirements: 107-REQ-3.3, 107-REQ-3.E1_

  - [x] 4.4 Implement Kotlin edge extraction and module map
    - CONTAINS edges (file->class, class->method, file->function)
    - IMPORTS edges from `import` statements
    - EXTENDS edges from `:` clause
    - Module map: package.class -> file path
    - Skip unresolvable imports silently
    - _Requirements: 107-REQ-3.4, 107-REQ-3.5, 107-REQ-3.E2_

  - [x] 4.5 Register KotlinAnalyzer in registry.py
    - Add `_try_register(registry, KotlinAnalyzer, "kotlin")`
    - _Requirements: 107-REQ-5.1, 107-REQ-5.3_

  - [x] 4.V Verify task group 4
    - [x] Kotlin spec tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k "Kotlin"`
    - [x] Kotlin property tests pass: `uv run pytest -q tests/property/knowledge/test_multilang_props.py -k "kotlin"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`
    - [x] Requirements 107-REQ-3.* acceptance criteria met

- [x] 5. Implement Dart analyzer
  - [x] 5.1 Add `tree-sitter-dart-orchard>=0.3.1` to pyproject.toml dependencies
    - Run `uv sync` to install
    - Note: package name differs from grammar module name; verify import path
    - _Requirements: 107-REQ-6.1_

  - [x] 5.2 Create `agent_fox/knowledge/lang/dart_lang.py`
    - Implement `DartAnalyzer` class with protocol properties
    - Implement `make_parser()` using `tree_sitter_dart_orchard` from `tree-sitter-dart-orchard`
    - _Requirements: 107-REQ-4.1, 107-REQ-4.2_

  - [x] 5.3 Implement Dart entity extraction
    - Extract FILE, MODULE (library directive only), CLASS (class/mixin/enum/extension),
      FUNCTION (top-level + methods with qualified names)
    - No MODULE entity when library directive absent
    - _Requirements: 107-REQ-4.3, 107-REQ-4.E2_

  - [x] 5.4 Implement Dart edge extraction and module map
    - CONTAINS edges (file->class, class->method, file->function)
    - IMPORTS edges from `import` statements
    - EXTENDS edges from `extends`, `implements`, `with` clauses
    - Module map: import path -> file path
    - Skip `dart:` and external `package:` imports
    - _Requirements: 107-REQ-4.4, 107-REQ-4.5, 107-REQ-4.E1_

  - [x] 5.5 Register DartAnalyzer in registry.py
    - Add `_try_register(registry, DartAnalyzer, "dart")`
    - _Requirements: 107-REQ-5.1, 107-REQ-5.3_

  - [x] 5.V Verify task group 5
    - [x] Dart spec tests pass: `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k "Dart"`
    - [x] Dart property tests pass: `uv run pytest -q tests/property/knowledge/test_multilang_props.py -k "dart"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/ && uv run ruff format --check agent_fox/`
    - [x] Requirements 107-REQ-4.* acceptance criteria met

- [x] 6. Checkpoint — All Languages Complete
  - [x] 6.1 Run full test suite including all new and existing tests
    - `make check`
  - [x] 6.2 Verify all four analyzers appear in default registry
    - `uv run pytest -q tests/unit/knowledge/test_lang_analyzers.py -k "Registry"`
  - [x] 6.3 Run integration smoke test
    - `uv run pytest -q tests/integration/knowledge/test_new_lang_smoke.py`
  - [x] 6.4 Verify extension uniqueness property test passes
    - `uv run pytest -q tests/property/knowledge/test_multilang_props.py -k "extension"`

- [x] 7. Wiring verification

  - [x] 7.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - Every path must be live in production code — errata or deferrals do not
      satisfy this check
    - _Requirements: all_
    - Path 1 verified: analyze_codebase (line 90) → detect_languages →
      _build_default_registry (all 4 new analyzers registered) → for each
      analyzer: _analyze_language → build_module_map (line 281) →
      make_parser (line 282) → extract_entities (line 297) →
      extract_edges (line 300) → upsert_entities (line 146) →
      upsert_edges (line 237). All live, no stubs.
    - Path 2 verified: _build_default_registry wraps each import in
      try/except ImportError + _try_register wraps make_parser() probe
      in try/except Exception. Missing grammar → info log, skip.

  - [x] 7.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Grep for callers of each such function; confirm none discards the return
    - _Requirements: all_
    - detect_languages() → stored in `analyzers` → iterated at line 108.
    - _analyze_language appends to caller-provided lists (lang_entities,
      lang_edges); results collected in lang_entity_batches/all_sentinel_edges.
    - upsert_entities() → lang_ids extended into all_upserted_ids at line 147;
      used for edge resolution at line 157.
    - build_module_map() → stored in module_map → passed to extract_edges at
      line 300.

  - [x] 7.3 Run the integration smoke tests
    - All `TS-107-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-107-SMOKE-1_
    - TS-107-SMOKE-1: 3/3 tests pass (languages_analyzed, entities_inserted,
      total entity count all verified).

  - [x] 7.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale
    - Audit result: Zero `return []`, zero `pass`, zero `# TODO`/`# stub`/
      `NotImplementedError` in any of the four new analyzer files. All
      `return None` hits are in private helper functions with `Optional`
      return types (e.g., `_get_namespace_name`, `_get_using_name`,
      `_find_first_child_by_types`), which is correct behavior.

  - [x] 7.5 Cross-spec entry point verification
    - Verify that `analyze_codebase()` in `static_analysis.py` calls
      `_analyze_language()` for the new analyzers when their files are present
    - Verify that `detect_languages()` returns the new analyzers
    - Verify that `get_default_registry()` includes all four new analyzers
    - These entry points are owned by spec 102 and must be live
    - _Requirements: all_
    - analyze_codebase() calls detect_languages() at static_analysis.py:90,
      then calls _analyze_language() for each analyzer at lines 112-117.
    - detect_languages() calls _build_default_registry() and scans files for
      each analyzer (registry.py:131-137).
    - get_default_registry() / _build_default_registry() registers all four
      new analyzers (registry.py:234-264) — confirmed live with uv run.

  - [x] 7.V Verify wiring group
    - [x] All smoke tests pass
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live (traceable in code)
    - [x] All cross-spec entry points are called from production code
    - [x] All existing tests still pass: `uv run pytest -q`

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 107-REQ-1.1 | TS-107-1, TS-107-P1 | 2.2 | test_csharp_properties |
| 107-REQ-1.2 | TS-107-1 | 2.2 | test_csharp_properties |
| 107-REQ-1.3 | TS-107-2, TS-107-P2 | 2.3 | test_csharp_entities, test_csharp_entity_validity |
| 107-REQ-1.4 | TS-107-3 | 2.4 | test_csharp_edges |
| 107-REQ-1.5 | TS-107-4, TS-107-P7 | 2.4 | test_csharp_module_map |
| 107-REQ-1.E1 | TS-107-E1 | 2.4 | test_csharp_external_using_skipped |
| 107-REQ-1.E2 | TS-107-E2 | 2.3 | test_csharp_multiple_namespaces |
| 107-REQ-2.1 | TS-107-5, TS-107-P1 | 3.2 | test_elixir_properties |
| 107-REQ-2.2 | TS-107-5 | 3.2 | test_elixir_properties |
| 107-REQ-2.3 | TS-107-6, TS-107-P5 | 3.3 | test_elixir_entities |
| 107-REQ-2.4 | TS-107-6, TS-107-P5 | 3.3 | test_elixir_entities, test_elixir_no_class |
| 107-REQ-2.5 | TS-107-7 | 3.4 | test_elixir_edges |
| 107-REQ-2.6 | TS-107-8, TS-107-P7 | 3.4 | test_elixir_module_map |
| 107-REQ-2.E1 | TS-107-E3 | 3.3 | test_elixir_nested_defmodule |
| 107-REQ-2.E2 | TS-107-E4 | 3.4 | test_elixir_external_import_skipped |
| 107-REQ-3.1 | TS-107-9, TS-107-P1 | 4.2 | test_kotlin_properties |
| 107-REQ-3.2 | TS-107-9 | 4.2 | test_kotlin_properties |
| 107-REQ-3.3 | TS-107-10, TS-107-P3 | 4.3 | test_kotlin_entities |
| 107-REQ-3.4 | TS-107-11 | 4.4 | test_kotlin_edges |
| 107-REQ-3.5 | TS-107-12, TS-107-P7 | 4.4 | test_kotlin_module_map |
| 107-REQ-3.E1 | TS-107-E5 | 4.3 | test_kotlin_companion_object |
| 107-REQ-3.E2 | TS-107-E6 | 4.4 | test_kotlin_external_import_skipped |
| 107-REQ-4.1 | TS-107-13, TS-107-P1 | 5.2 | test_dart_properties |
| 107-REQ-4.2 | TS-107-13 | 5.2 | test_dart_properties |
| 107-REQ-4.3 | TS-107-14, TS-107-15, TS-107-P4 | 5.3 | test_dart_entities |
| 107-REQ-4.4 | TS-107-16 | 5.4 | test_dart_edges |
| 107-REQ-4.5 | TS-107-17, TS-107-P7 | 5.4 | test_dart_module_map |
| 107-REQ-4.E1 | TS-107-E7 | 5.4 | test_dart_sdk_import_skipped |
| 107-REQ-4.E2 | TS-107-15, TS-107-E8 | 5.3 | test_dart_no_library_directive |
| 107-REQ-5.1 | TS-107-18 | 2.5, 3.5, 4.5, 5.5 | test_registry_integration |
| 107-REQ-5.2 | TS-107-18, TS-107-P6 | 2.5, 3.5, 4.5, 5.5 | test_extension_uniqueness |
| 107-REQ-5.3 | TS-107-E9 | 2.5, 3.5, 4.5, 5.5 | test_grammar_not_installed |
| 107-REQ-5.4 | TS-107-19 | 2.5, 3.5, 4.5, 5.5 | test_detect_languages |
| 107-REQ-5.E1 | TS-107-E9 | 2.5, 3.5, 4.5, 5.5 | test_grammar_not_installed |
| 107-REQ-6.1 | TS-107-18 | 2.1, 3.1, 4.1, 5.1 | test_registry_integration |
| 107-REQ-6.2 | TS-107-SMOKE-1 | 7.1 | test_analyze_codebase_smoke |
| Property 1 | TS-107-P1 | 2.2, 3.2, 4.2, 5.2 | test_protocol_conformance |
| Property 2 | TS-107-P2, P3, P4 | 2.3, 4.3, 5.3 | test_entity_validity_* |
| Property 4 | TS-107-P6 | 2.5, 3.5, 4.5, 5.5 | test_extension_uniqueness |
| Property 6 | TS-107-P7 | 2.4, 3.4, 4.4, 5.4 | test_module_map_path_format |
| Property 7 | TS-107-P5 | 3.3, 3.4 | test_elixir_no_class_invariant |

## Notes

- Each language is self-contained: task groups 2-5 can be worked on in any
  order if parallelism is desired.
- The Dart grammar comes from `tree-sitter-dart-orchard`, a community fork.
  The import path may differ from the package name — verify with
  `python -c "import tree_sitter_dart"` after install.
- Elixir's tree-sitter grammar represents keywords (`defmodule`, `def`,
  `use`, etc.) as `call` nodes. The analyzer must match on the called
  identifier text, not the node type.
- Property tests for generated source code must filter out language keywords
  to avoid producing unparseable source (same pattern as the Go/Python
  keyword filters in existing property tests).
