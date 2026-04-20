# Requirements Document

## Introduction

This specification adds four new language analyzers (C#, Elixir, Kotlin, Dart)
to the multi-language entity graph infrastructure established by spec 102.
Each analyzer implements the existing `LanguageAnalyzer` protocol and is
registered in the default `LanguageRegistry`. No protocol, database, or
orchestration changes are required.

## Glossary

- **Analyzer**: A class implementing the `LanguageAnalyzer` protocol that
  extracts entities and edges from source files of a specific language.
- **Entity**: A named code construct (file, module/namespace, class, function)
  stored in the entity graph with a unique ID, type, name, and path.
- **Edge**: A directional relationship between two entities (CONTAINS,
  IMPORTS, EXTENDS).
- **Module map**: A dictionary mapping language-specific import identifiers to
  repo-relative file paths, enabling IMPORTS edge resolution.
- **Sentinel ID**: A temporary edge endpoint (e.g. `path:foo.cs`,
  `class:UserService`) that is resolved to a real entity ID during the
  upsert phase in `analyze_codebase()`.
- **Qualified name**: A dot-separated name encoding containment hierarchy
  (e.g. `UserService.Validate`, `MyApp.Accounts.User.changeset`).

## Requirements

### Requirement 1: C# Language Analyzer

**User Story:** As a developer working on a C# codebase, I want agent-fox to
extract entities and relationships from `.cs` files so that knowledge
retrieval and drift detection work for my project.

#### Acceptance Criteria

[107-REQ-1.1] WHEN the C# analyzer is instantiated, THE analyzer SHALL
report `language_name` as `"csharp"` and `file_extensions` as `{".cs"}`.

[107-REQ-1.2] WHEN `make_parser()` is called, THE analyzer SHALL return a
tree-sitter `Parser` configured with the `tree_sitter_c_sharp` grammar.

[107-REQ-1.3] WHEN `extract_entities()` is called with a parsed C# tree, THE
analyzer SHALL return entities of type FILE (one per file), MODULE (one per
`namespace` declaration), CLASS (for `class`, `struct`, `interface`, `enum`,
and `record` declarations), and FUNCTION (for method declarations, qualified
as `ClassName.MethodName`).

[107-REQ-1.4] WHEN `extract_edges()` is called, THE analyzer SHALL return
CONTAINS edges (file->namespace, namespace->class, class->method), IMPORTS
edges (from `using` directives resolved via the module map), and EXTENDS edges
(from inheritance and interface implementation via the `:` clause).

[107-REQ-1.5] WHEN `build_module_map()` is called, THE analyzer SHALL return
a dictionary mapping namespace-qualified type names to repo-relative file
paths AND return only POSIX-style paths as values.

#### Edge Cases

[107-REQ-1.E1] IF a `using` directive references a namespace not present in
the module map (e.g. external dependency), THEN THE analyzer SHALL silently
skip the unresolvable import without raising an exception.

[107-REQ-1.E2] IF a C# file contains multiple `namespace` declarations, THEN
THE analyzer SHALL create one MODULE entity per namespace and assign classes
to their enclosing namespace via CONTAINS edges.

### Requirement 2: Elixir Language Analyzer

**User Story:** As a developer working on an Elixir codebase, I want agent-fox
to extract modules and functions from `.ex`/`.exs` files so that knowledge
retrieval works for my project.

#### Acceptance Criteria

[107-REQ-2.1] WHEN the Elixir analyzer is instantiated, THE analyzer SHALL
report `language_name` as `"elixir"` and `file_extensions` as
`{".ex", ".exs"}`.

[107-REQ-2.2] WHEN `make_parser()` is called, THE analyzer SHALL return a
tree-sitter `Parser` configured with the `tree_sitter_elixir` grammar.

[107-REQ-2.3] WHEN `extract_entities()` is called with a parsed Elixir tree,
THE analyzer SHALL return entities of type FILE (one per file), MODULE (one
per `defmodule` declaration, using dotted module names), and FUNCTION (for
`def` and `defp` declarations, qualified as `ModuleName.function_name`).

[107-REQ-2.4] THE analyzer SHALL NOT produce any CLASS or EXTENDS entities or
edges, since Elixir has no class or inheritance constructs.

[107-REQ-2.5] WHEN `extract_edges()` is called, THE analyzer SHALL return
CONTAINS edges (file->module, module->function) and IMPORTS edges (from
`use`, `import`, `alias`, and `require` statements resolved via the module
map).

[107-REQ-2.6] WHEN `build_module_map()` is called, THE analyzer SHALL return
a dictionary mapping dotted Elixir module names (e.g. `MyApp.Accounts.User`)
to repo-relative file paths AND return only POSIX-style paths as values.

#### Edge Cases

[107-REQ-2.E1] IF an Elixir file contains nested `defmodule` declarations,
THEN THE analyzer SHALL create MODULE entities for each nested module with
fully-qualified dotted names.

[107-REQ-2.E2] IF a `use`, `import`, `alias`, or `require` references a
module not in the module map (e.g. external dependency), THEN THE analyzer
SHALL silently skip it.

### Requirement 3: Kotlin Language Analyzer

**User Story:** As a developer working on a Kotlin codebase, I want agent-fox
to extract entities and relationships from `.kt`/`.kts` files so that
knowledge retrieval and drift detection work for my project.

#### Acceptance Criteria

[107-REQ-3.1] WHEN the Kotlin analyzer is instantiated, THE analyzer SHALL
report `language_name` as `"kotlin"` and `file_extensions` as
`{".kt", ".kts"}`.

[107-REQ-3.2] WHEN `make_parser()` is called, THE analyzer SHALL return a
tree-sitter `Parser` configured with the `tree_sitter_kotlin` grammar.

[107-REQ-3.3] WHEN `extract_entities()` is called with a parsed Kotlin tree,
THE analyzer SHALL return entities of type FILE (one per file), MODULE (one
per `package` declaration), CLASS (for `class`, `interface`, `object`,
`enum class`, and `data class` declarations), and FUNCTION (for `fun`
declarations, qualified as `ClassName.functionName` for methods).

[107-REQ-3.4] WHEN `extract_edges()` is called, THE analyzer SHALL return
CONTAINS edges (file->class, class->method, file->top-level function),
IMPORTS edges (from `import` statements resolved via the module map), and
EXTENDS edges (from the `:` clause for inheritance and interface
implementation).

[107-REQ-3.5] WHEN `build_module_map()` is called, THE analyzer SHALL return
a dictionary mapping package-qualified class names to repo-relative file
paths AND return only POSIX-style paths as values.

#### Edge Cases

[107-REQ-3.E1] WHEN a Kotlin class contains a `companion object`, THE
analyzer SHALL qualify companion methods as `ClassName.methodName` (not
`ClassName.Companion.methodName`).

[107-REQ-3.E2] IF an `import` statement references a class not in the module
map (e.g. external dependency), THEN THE analyzer SHALL silently skip it.

### Requirement 4: Dart Language Analyzer

**User Story:** As a developer working on a Dart codebase, I want agent-fox
to extract entities and relationships from `.dart` files so that knowledge
retrieval and drift detection work for my project.

#### Acceptance Criteria

[107-REQ-4.1] WHEN the Dart analyzer is instantiated, THE analyzer SHALL
report `language_name` as `"dart"` and `file_extensions` as `{".dart"}`.

[107-REQ-4.2] WHEN `make_parser()` is called, THE analyzer SHALL return a
tree-sitter `Parser` configured with the `tree_sitter_dart` grammar from the
`tree-sitter-dart-orchard` package.

[107-REQ-4.3] WHEN `extract_entities()` is called with a parsed Dart tree,
THE analyzer SHALL return entities of type FILE (one per file), MODULE (only
when an explicit `library` directive is present), CLASS (for `class`, `mixin`,
`enum`, and `extension` declarations), and FUNCTION (for top-level functions
and methods, qualified as `ClassName.methodName`).

[107-REQ-4.4] WHEN `extract_edges()` is called, THE analyzer SHALL return
CONTAINS edges (file->class, class->method, file->function), IMPORTS edges
(from `import` statements resolved via the module map), and EXTENDS edges
(from `extends`, `implements`, and `with` clauses).

[107-REQ-4.5] WHEN `build_module_map()` is called, THE analyzer SHALL return
a dictionary mapping import path strings to repo-relative file paths AND
return only POSIX-style paths as values.

#### Edge Cases

[107-REQ-4.E1] IF a Dart `import` statement uses `dart:` or `package:` prefix
referencing an external/SDK package, THEN THE analyzer SHALL silently skip the
unresolvable import.

[107-REQ-4.E2] IF a Dart file has no explicit `library` directive, THEN THE
analyzer SHALL NOT create a MODULE entity for that file.

### Requirement 5: Registry Integration

**User Story:** As an operator, I want all four new analyzers to be
automatically discovered and used when analyzing a codebase containing their
respective file types.

#### Acceptance Criteria

[107-REQ-5.1] WHEN the default `LanguageRegistry` is built, THE system SHALL
register all four analyzers (C#, Elixir, Kotlin, Dart) alongside existing
analyzers.

[107-REQ-5.2] THE system SHALL verify that file extensions for the four new
analyzers do not conflict with any existing registered extensions.

[107-REQ-5.3] IF a tree-sitter grammar package is not installed, THEN THE
system SHALL skip registration of that analyzer with an info-level log message
and SHALL NOT raise an exception.

[107-REQ-5.4] WHEN `detect_languages()` is called on a repository containing
files of the new languages, THE system SHALL include the corresponding
analyzers in the returned list.

#### Edge Cases

[107-REQ-5.E1] IF only some of the four grammar packages are installed, THEN
THE system SHALL register only the available analyzers and skip the
unavailable ones without affecting the rest of the registry.

### Requirement 6: Dependency Management

**User Story:** As a developer building agent-fox from source, I want the
tree-sitter grammar packages for the new languages to be declared as
dependencies so they install automatically.

#### Acceptance Criteria

[107-REQ-6.1] THE build configuration SHALL declare `tree-sitter-c-sharp`,
`tree-sitter-elixir`, `tree-sitter-kotlin`, and `tree-sitter-dart-orchard`
as dependencies in `pyproject.toml`.

[107-REQ-6.2] THE addition of new analyzers SHALL NOT change the behavior of
existing analyzers or the signature of `analyze_codebase()`.
