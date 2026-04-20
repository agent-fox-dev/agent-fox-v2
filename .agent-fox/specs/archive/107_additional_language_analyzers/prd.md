# PRD: Additional Language Analyzers

## Problem

The entity graph language analyzer stack currently supports Python, Go,
TypeScript, JavaScript, Rust, Java, C, C++, and Ruby. Four additional
languages with significant user-base demand are missing: **C#**, **Elixir**,
**Kotlin**, and **Dart**. Projects using these languages cannot benefit from
entity-graph-based retrieval, code navigation, or drift detection.

## Goal

Add full (Tier 1) language analyzer support for C#, Elixir, Kotlin, and Dart
to the existing multi-language entity graph infrastructure. Each language
receives its own `LanguageAnalyzer` implementation with complete entity
extraction, edge extraction, and import resolution via module maps.

## Scope

### In Scope

- One analyzer class per language, each implementing the `LanguageAnalyzer`
  protocol defined in `agent_fox/knowledge/lang/base.py`.
- Tree-sitter grammar dependencies added to `pyproject.toml`.
- Registration of all four analyzers in the default `LanguageRegistry`.
- Graceful degradation when a grammar package is not installed.
- Unit tests and property tests following the patterns in
  `tests/unit/knowledge/test_lang_analyzers.py` and
  `tests/property/knowledge/test_multilang_props.py`.

### Out of Scope

- Database schema changes (the existing `language` VARCHAR column from
  migration v9 already supports arbitrary language names).
- Changes to the `LanguageAnalyzer` protocol itself.
- Changes to `analyze_codebase()` orchestration or the entity resolution
  pipeline.
- IDE-specific or framework-specific features (e.g., Flutter widget
  detection, ASP.NET controller routing).

## Language Details

### C# (`csharp`)

- **Package:** `tree-sitter-c-sharp>=0.23`
- **Extensions:** `.cs`
- **Entity mapping:**
  - FILE: one per source file
  - MODULE: `namespace` declarations
  - CLASS: `class`, `struct`, `interface`, `enum`, `record`
  - FUNCTION: methods (qualified as `ClassName.MethodName`)
- **Edge mapping:**
  - CONTAINS: file->namespace, namespace->class, class->method
  - IMPORTS: `using` directives
  - EXTENDS: inheritance and interface implementation (`:` clause)
- **Module map:** Namespace-qualified type name -> repo-relative file path

### Elixir (`elixir`)

- **Package:** `tree-sitter-elixir>=0.3.4`
- **Extensions:** `.ex`, `.exs`
- **Entity mapping:**
  - FILE: one per source file
  - MODULE: `defmodule` declarations (dotted names, e.g. `MyApp.Accounts.User`)
  - FUNCTION: `def` and `defp` functions (qualified as `Module.function_name`)
  - No CLASS entities (Elixir has no classes)
- **Edge mapping:**
  - CONTAINS: file->module, module->function
  - IMPORTS: `use`, `import`, `alias`, `require` statements
  - No EXTENDS edges (Elixir has no inheritance)
- **Module map:** Dotted module name -> repo-relative file path
  (e.g. `MyApp.Accounts.User` -> `lib/my_app/accounts/user.ex`)

### Kotlin (`kotlin`)

- **Package:** `tree-sitter-kotlin>=1.0`
- **Extensions:** `.kt`, `.kts`
- **Entity mapping:**
  - FILE: one per source file
  - MODULE: `package` declarations
  - CLASS: `class`, `interface`, `object`, `enum class`, `data class`
  - FUNCTION: `fun` declarations (qualified as `ClassName.functionName`)
- **Edge mapping:**
  - CONTAINS: file->class, class->method, file->function
  - IMPORTS: `import` statements
  - EXTENDS: inheritance and interface implementation (`:` clause)
- **Module map:** Package-qualified class name -> repo-relative file path

### Dart (`dart`)

- **Package:** `tree-sitter-dart-orchard>=0.3.1`
  (no official `tree-sitter-dart` exists on PyPI; this is the maintained
  community fork)
- **Extensions:** `.dart`
- **Entity mapping:**
  - FILE: one per source file
  - MODULE: `library` directives (optional in modern Dart; only created
    when the directive is present)
  - CLASS: `class`, `mixin`, `enum`, `extension`
  - FUNCTION: top-level functions and methods (qualified as `ClassName.methodName`)
- **Edge mapping:**
  - CONTAINS: file->class, class->method, file->function
  - IMPORTS: `import` statements
  - EXTENDS: `extends`, `implements`, `with` (mixin application)
- **Module map:** Package-relative import path -> repo-relative file path
  (SDK and external package imports are skipped)

## Design Decisions

1. **Elixir MODULE vs CLASS:** Elixir `defmodule` maps to MODULE (not CLASS),
   since Elixir modules are namespaces that hold functions, not instantiable
   types. This means Elixir is the first language with no CLASS entities,
   which is architecturally valid since entity types are per-language.

2. **Dart grammar package:** Using `tree-sitter-dart-orchard` (community fork)
   because no official `tree-sitter-dart` exists on PyPI. This is a
   third-party dependency risk that should be revisited if an official
   package appears.

3. **Kotlin `.kts` files:** Included because Kotlin Script files (Gradle
   build scripts, etc.) contain valid Kotlin code with the same syntax.

4. **Elixir `.exs` files:** Included because Elixir script files (tests,
   config) use the same syntax as compiled `.ex` files.

5. **Dart `library` directives:** MODULE entities are only created when an
   explicit `library` directive is present. Most modern Dart files are
   implicit libraries and will have no MODULE entity, matching the pattern
   of Python files without `__init__.py`.

## Source

Source: Input provided by user via interactive prompt
