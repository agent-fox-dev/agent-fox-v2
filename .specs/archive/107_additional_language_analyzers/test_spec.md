# Test Specification: Additional Language Analyzers

## Overview

Tests are organized per-language, following the established pattern in
`test_lang_analyzers.py` and `test_multilang_props.py`. Each language has
unit tests for properties, entity extraction, edge extraction, and module
map. Property tests verify entity validity and edge referential integrity.
One integration smoke test covers all four languages together.

## Test Cases

### TS-107-1: C# Analyzer Properties

**Requirement:** 107-REQ-1.1
**Type:** unit
**Description:** CSharpAnalyzer reports correct language_name and file_extensions.

**Preconditions:**
- `tree-sitter-c-sharp` is installed.

**Input:**
- Instantiate `CSharpAnalyzer`.

**Expected:**
- `language_name` == `"csharp"`
- `file_extensions` == `{".cs"}`

**Assertion pseudocode:**
```
analyzer = CSharpAnalyzer()
ASSERT analyzer.language_name == "csharp"
ASSERT analyzer.file_extensions == {".cs"}
```

### TS-107-2: C# Entity Extraction

**Requirement:** 107-REQ-1.3
**Type:** unit
**Description:** CSharpAnalyzer extracts FILE, MODULE, CLASS, and FUNCTION entities with qualified names.

**Preconditions:**
- A `.cs` file with a namespace, class, interface, struct, enum, and method.

**Input:**
```csharp
namespace MyApp.Services
{
    public interface IService { }
    public class UserService : IService
    {
        public void CreateUser(string name) { }
    }
    public struct Point { }
    public enum Status { Active, Inactive }
}
```

**Expected:**
- FILE entity: name == filename
- MODULE entity: name == "MyApp.Services"
- CLASS entities: "IService", "UserService", "Point", "Status"
- FUNCTION entity: "UserService.CreateUser"

**Assertion pseudocode:**
```
entities = analyzer.extract_entities(tree, "Services.cs")
names = {e.entity_name for e in entities}
types = {e.entity_name: e.entity_type for e in entities}
ASSERT "Services.cs" in names AND types["Services.cs"] == FILE
ASSERT "MyApp.Services" in names AND types["MyApp.Services"] == MODULE
ASSERT "UserService" in names AND types["UserService"] == CLASS
ASSERT "IService" in names AND types["IService"] == CLASS
ASSERT "Point" in names AND types["Point"] == CLASS
ASSERT "Status" in names AND types["Status"] == CLASS
ASSERT "UserService.CreateUser" in names AND types["UserService.CreateUser"] == FUNCTION
```

### TS-107-3: C# Edge Extraction

**Requirement:** 107-REQ-1.4
**Type:** unit
**Description:** CSharpAnalyzer extracts CONTAINS, IMPORTS, and EXTENDS edges.

**Preconditions:**
- Same C# source as TS-107-2, with a `using` directive added.

**Input:**
```csharp
using System.Collections.Generic;
namespace MyApp.Services
{
    public class UserService : IService
    {
        public void CreateUser(string name) { }
    }
}
```

**Expected:**
- CONTAINS edges: namespace->class, class->method
- EXTENDS edge: UserService -> IService
- IMPORTS edge (or silently skipped if not in module map)

**Assertion pseudocode:**
```
edges = analyzer.extract_edges(tree, "Services.cs", entities, module_map)
contains = [e for e in edges if e.relationship == CONTAINS]
extends = [e for e in edges if e.relationship == EXTENDS]
ASSERT len(contains) >= 2  # namespace->class, class->method
ASSERT len(extends) >= 1   # UserService -> IService
```

### TS-107-4: C# Module Map

**Requirement:** 107-REQ-1.5
**Type:** unit
**Description:** CSharpAnalyzer builds a module map from namespace+class to file path.

**Preconditions:**
- A directory with `.cs` files containing namespace declarations.

**Input:**
- `src/Services/UserService.cs` with `namespace MyApp.Services` and `class UserService`

**Expected:**
- Module map contains `"MyApp.Services.UserService"` -> `"src/Services/UserService.cs"`
- All values are POSIX paths (no backslashes, no leading `/`)

**Assertion pseudocode:**
```
mm = analyzer.build_module_map(repo_root, files)
ASSERT "MyApp.Services.UserService" in mm
ASSERT "\\" not in mm["MyApp.Services.UserService"]
ASSERT not mm["MyApp.Services.UserService"].startswith("/")
```

### TS-107-5: Elixir Analyzer Properties

**Requirement:** 107-REQ-2.1
**Type:** unit
**Description:** ElixirAnalyzer reports correct language_name and file_extensions.

**Preconditions:**
- `tree-sitter-elixir` is installed.

**Input:**
- Instantiate `ElixirAnalyzer`.

**Expected:**
- `language_name` == `"elixir"`
- `file_extensions` == `{".ex", ".exs"}`

**Assertion pseudocode:**
```
analyzer = ElixirAnalyzer()
ASSERT analyzer.language_name == "elixir"
ASSERT analyzer.file_extensions == {".ex", ".exs"}
```

### TS-107-6: Elixir Entity Extraction

**Requirement:** 107-REQ-2.3, 107-REQ-2.4
**Type:** unit
**Description:** ElixirAnalyzer extracts FILE, MODULE, and FUNCTION entities; no CLASS entities.

**Preconditions:**
- An `.ex` file with a module and functions.

**Input:**
```elixir
defmodule MyApp.Accounts.User do
  def changeset(user, attrs) do
    user
  end

  defp validate_email(changeset) do
    changeset
  end
end
```

**Expected:**
- FILE entity: name == filename
- MODULE entity: name == "MyApp.Accounts.User"
- FUNCTION entities: "MyApp.Accounts.User.changeset", "MyApp.Accounts.User.validate_email"
- No CLASS entities

**Assertion pseudocode:**
```
entities = analyzer.extract_entities(tree, "user.ex")
names = {e.entity_name for e in entities}
types = {e.entity_name: e.entity_type for e in entities}
ASSERT "MyApp.Accounts.User" in names AND types["MyApp.Accounts.User"] == MODULE
ASSERT "MyApp.Accounts.User.changeset" in names
ASSERT "MyApp.Accounts.User.validate_email" in names
ASSERT not any(e.entity_type == CLASS for e in entities)
```

### TS-107-7: Elixir Edge Extraction

**Requirement:** 107-REQ-2.5
**Type:** unit
**Description:** ElixirAnalyzer extracts CONTAINS and IMPORTS edges; no EXTENDS.

**Preconditions:**
- An Elixir file with `use`, `import`, and `alias` statements.

**Input:**
```elixir
defmodule MyApp.Accounts.User do
  use Ecto.Schema
  import Ecto.Changeset
  alias MyApp.Repo

  def changeset(user, attrs), do: user
end
```

**Expected:**
- CONTAINS edges: file->module, module->function
- IMPORTS edges for use/import/alias (resolved or sentinel)
- No EXTENDS edges

**Assertion pseudocode:**
```
edges = analyzer.extract_edges(tree, "user.ex", entities, module_map)
contains = [e for e in edges if e.relationship == CONTAINS]
imports = [e for e in edges if e.relationship == IMPORTS]
extends = [e for e in edges if e.relationship == EXTENDS]
ASSERT len(contains) >= 2
ASSERT len(imports) >= 1
ASSERT len(extends) == 0
```

### TS-107-8: Elixir Module Map

**Requirement:** 107-REQ-2.6
**Type:** unit
**Description:** ElixirAnalyzer maps dotted module names to file paths.

**Preconditions:**
- An Elixir project with `lib/my_app/accounts/user.ex` containing
  `defmodule MyApp.Accounts.User`.

**Input:**
- Files: `[lib/my_app/accounts/user.ex]`

**Expected:**
- `"MyApp.Accounts.User"` -> `"lib/my_app/accounts/user.ex"`

**Assertion pseudocode:**
```
mm = analyzer.build_module_map(repo_root, files)
ASSERT "MyApp.Accounts.User" in mm
ASSERT mm["MyApp.Accounts.User"] == "lib/my_app/accounts/user.ex"
```

### TS-107-9: Kotlin Analyzer Properties

**Requirement:** 107-REQ-3.1
**Type:** unit
**Description:** KotlinAnalyzer reports correct language_name and file_extensions.

**Preconditions:**
- `tree-sitter-kotlin` is installed.

**Input:**
- Instantiate `KotlinAnalyzer`.

**Expected:**
- `language_name` == `"kotlin"`
- `file_extensions` == `{".kt", ".kts"}`

**Assertion pseudocode:**
```
analyzer = KotlinAnalyzer()
ASSERT analyzer.language_name == "kotlin"
ASSERT analyzer.file_extensions == {".kt", ".kts"}
```

### TS-107-10: Kotlin Entity Extraction

**Requirement:** 107-REQ-3.3
**Type:** unit
**Description:** KotlinAnalyzer extracts FILE, MODULE, CLASS, and FUNCTION entities.

**Preconditions:**
- A `.kt` file with package, class, interface, object, data class, and functions.

**Input:**
```kotlin
package com.example.models

class User(val name: String) {
    fun validate(): Boolean = name.isNotEmpty()
}

interface Serializable {
    fun serialize(): String
}

object AppConfig {
    val version = "1.0"
}

data class UserDTO(val name: String, val email: String)

fun topLevelFunction() {}
```

**Expected:**
- FILE entity: name == filename
- MODULE entity: name == "com.example.models"
- CLASS entities: "User", "Serializable", "AppConfig", "UserDTO"
- FUNCTION entities: "User.validate", "Serializable.serialize", "topLevelFunction"

**Assertion pseudocode:**
```
entities = analyzer.extract_entities(tree, "Models.kt")
names = {e.entity_name for e in entities}
types = {e.entity_name: e.entity_type for e in entities}
ASSERT "com.example.models" in names AND types["com.example.models"] == MODULE
ASSERT "User" in names AND types["User"] == CLASS
ASSERT "Serializable" in names AND types["Serializable"] == CLASS
ASSERT "AppConfig" in names AND types["AppConfig"] == CLASS
ASSERT "UserDTO" in names AND types["UserDTO"] == CLASS
ASSERT "User.validate" in names AND types["User.validate"] == FUNCTION
ASSERT "topLevelFunction" in names AND types["topLevelFunction"] == FUNCTION
```

### TS-107-11: Kotlin Edge Extraction

**Requirement:** 107-REQ-3.4
**Type:** unit
**Description:** KotlinAnalyzer extracts CONTAINS, IMPORTS, and EXTENDS edges.

**Preconditions:**
- A Kotlin file with inheritance and import.

**Input:**
```kotlin
package com.example

import com.example.models.BaseModel

class User : BaseModel() {
    fun validate() {}
}
```

**Expected:**
- CONTAINS edges: file->class, class->method
- IMPORTS edge for BaseModel (resolved or sentinel)
- EXTENDS edge: User -> BaseModel

**Assertion pseudocode:**
```
edges = analyzer.extract_edges(tree, "User.kt", entities, module_map)
contains = [e for e in edges if e.relationship == CONTAINS]
extends = [e for e in edges if e.relationship == EXTENDS]
ASSERT len(contains) >= 2
ASSERT len(extends) >= 1
```

### TS-107-12: Kotlin Module Map

**Requirement:** 107-REQ-3.5
**Type:** unit
**Description:** KotlinAnalyzer maps package-qualified class names to file paths.

**Preconditions:**
- A Kotlin project with `src/com/example/models/User.kt`.

**Input:**
- Files: `[src/com/example/models/User.kt]`

**Expected:**
- `"com.example.models.User"` -> `"src/com/example/models/User.kt"`

**Assertion pseudocode:**
```
mm = analyzer.build_module_map(repo_root, files)
ASSERT "com.example.models.User" in mm
```

### TS-107-13: Dart Analyzer Properties

**Requirement:** 107-REQ-4.1
**Type:** unit
**Description:** DartAnalyzer reports correct language_name and file_extensions.

**Preconditions:**
- `tree-sitter-dart-orchard` is installed.

**Input:**
- Instantiate `DartAnalyzer`.

**Expected:**
- `language_name` == `"dart"`
- `file_extensions` == `{".dart"}`

**Assertion pseudocode:**
```
analyzer = DartAnalyzer()
ASSERT analyzer.language_name == "dart"
ASSERT analyzer.file_extensions == {".dart"}
```

### TS-107-14: Dart Entity Extraction

**Requirement:** 107-REQ-4.3
**Type:** unit
**Description:** DartAnalyzer extracts FILE, CLASS, and FUNCTION entities; MODULE only with explicit library directive.

**Preconditions:**
- A `.dart` file with class, mixin, enum, extension, and functions.

**Input:**
```dart
class User {
  String name;
  void save() {}
}

mixin Printable {
  void printInfo() {}
}

enum Status { active, inactive }

extension StringExt on String {
  bool get isEmail => contains('@');
}

void topLevelFunction() {}
```

**Expected:**
- FILE entity: name == filename
- No MODULE entity (no library directive)
- CLASS entities: "User", "Printable", "Status", "StringExt"
- FUNCTION entities: "User.save", "Printable.printInfo", "topLevelFunction"

**Assertion pseudocode:**
```
entities = analyzer.extract_entities(tree, "models.dart")
names = {e.entity_name for e in entities}
types = {e.entity_name: e.entity_type for e in entities}
ASSERT not any(e.entity_type == MODULE for e in entities)
ASSERT "User" in names AND types["User"] == CLASS
ASSERT "Printable" in names AND types["Printable"] == CLASS
ASSERT "User.save" in names AND types["User.save"] == FUNCTION
ASSERT "topLevelFunction" in names AND types["topLevelFunction"] == FUNCTION
```

### TS-107-15: Dart Entity Extraction with Library Directive

**Requirement:** 107-REQ-4.3, 107-REQ-4.E2
**Type:** unit
**Description:** DartAnalyzer creates MODULE entity when library directive is present.

**Preconditions:**
- A `.dart` file with an explicit `library` directive.

**Input:**
```dart
library my_library;

class Widget {}
```

**Expected:**
- MODULE entity: name == "my_library"
- CLASS entity: "Widget"

**Assertion pseudocode:**
```
entities = analyzer.extract_entities(tree, "widget.dart")
modules = [e for e in entities if e.entity_type == MODULE]
ASSERT len(modules) == 1
ASSERT modules[0].entity_name == "my_library"
```

### TS-107-16: Dart Edge Extraction

**Requirement:** 107-REQ-4.4
**Type:** unit
**Description:** DartAnalyzer extracts CONTAINS, IMPORTS, and EXTENDS edges.

**Preconditions:**
- A Dart file with imports, inheritance, and mixins.

**Input:**
```dart
import 'models/base.dart';

class User extends BaseModel with Printable implements Serializable {
  void save() {}
}
```

**Expected:**
- CONTAINS edges: file->class, class->method
- IMPORTS edge for base.dart
- EXTENDS edges for BaseModel, Printable (with), Serializable (implements)

**Assertion pseudocode:**
```
edges = analyzer.extract_edges(tree, "user.dart", entities, module_map)
contains = [e for e in edges if e.relationship == CONTAINS]
extends = [e for e in edges if e.relationship == EXTENDS]
imports = [e for e in edges if e.relationship == IMPORTS]
ASSERT len(contains) >= 2
ASSERT len(extends) >= 1
ASSERT len(imports) >= 1
```

### TS-107-17: Dart Module Map

**Requirement:** 107-REQ-4.5
**Type:** unit
**Description:** DartAnalyzer maps import paths to file paths, skipping SDK/external imports.

**Preconditions:**
- A Dart project with `lib/models/user.dart`.

**Input:**
- Files: `[lib/models/user.dart]`

**Expected:**
- Relative imports resolve to repo-relative paths
- SDK imports (`dart:*`) not in module map
- Package imports for external packages not in module map

**Assertion pseudocode:**
```
mm = analyzer.build_module_map(repo_root, files)
ASSERT "models/user.dart" in mm or any("user.dart" in v for v in mm.values())
ASSERT not any(k.startswith("dart:") for k in mm)
```

### TS-107-18: Registry Integration

**Requirement:** 107-REQ-5.1, 107-REQ-5.2, 107-REQ-5.4
**Type:** unit
**Description:** All four analyzers are registered without extension conflicts.

**Preconditions:**
- All grammar packages installed.

**Input:**
- Call `get_default_registry()`.

**Expected:**
- Registry contains analyzers for "csharp", "elixir", "kotlin", "dart"
- No extension conflicts

**Assertion pseudocode:**
```
registry = get_default_registry()
lang_names = {a.language_name for a in registry.all_analyzers()}
ASSERT {"csharp", "elixir", "kotlin", "dart"}.issubset(lang_names)
ASSERT registry.get_analyzer(".cs") is not None
ASSERT registry.get_analyzer(".ex") is not None
ASSERT registry.get_analyzer(".kt") is not None
ASSERT registry.get_analyzer(".dart") is not None
```

### TS-107-19: Detect Languages

**Requirement:** 107-REQ-5.4
**Type:** integration
**Description:** detect_languages() discovers new languages when matching files exist.

**Preconditions:**
- A temp directory with `.cs`, `.ex`, `.kt`, and `.dart` files.

**Input:**
- Call `detect_languages(tmp_path)`.

**Expected:**
- Returned analyzers include ones with language_name in {"csharp", "elixir", "kotlin", "dart"}.

**Assertion pseudocode:**
```
analyzers = detect_languages(tmp_path)
detected = {a.language_name for a in analyzers}
ASSERT {"csharp", "elixir", "kotlin", "dart"}.issubset(detected)
```

## Property Test Cases

### TS-107-P1: Protocol Conformance

**Property:** Property 1 from design.md
**Validates:** 107-REQ-1.1, 107-REQ-2.1, 107-REQ-3.1, 107-REQ-4.1
**Type:** property
**Description:** All four analyzers satisfy the LanguageAnalyzer protocol.

**For any:** analyzer in {CSharpAnalyzer, ElixirAnalyzer, KotlinAnalyzer, DartAnalyzer}
**Invariant:** isinstance(analyzer, LanguageAnalyzer), language_name is non-empty, file_extensions is non-empty

**Assertion pseudocode:**
```
FOR analyzer_cls IN [CSharpAnalyzer, ElixirAnalyzer, KotlinAnalyzer, DartAnalyzer]:
    a = analyzer_cls()
    ASSERT isinstance(a, LanguageAnalyzer)
    ASSERT len(a.language_name) > 0
    ASSERT len(a.file_extensions) > 0
```

### TS-107-P2: C# Entity Validity

**Property:** Property 2 from design.md
**Validates:** 107-REQ-1.3
**Type:** property
**Description:** For any valid C# source, entities have non-empty names and valid types.

**For any:** class_name in `[A-Z][a-zA-Z0-9]{1,10}` (excluding C# keywords), method_name in `[A-Z][a-zA-Z0-9]{1,10}`
**Invariant:** All entities have non-empty entity_name, valid entity_type, non-empty entity_path.

**Assertion pseudocode:**
```
FOR ANY class_name, method_name IN strategies:
    source = f"namespace Ns {{ class {class_name} {{ void {method_name}() {{}} }} }}"
    tree = parse(source)
    entities = analyzer.extract_entities(tree, "gen.cs")
    FOR e IN entities:
        ASSERT len(e.entity_name) > 0
        ASSERT e.entity_type in EntityType
        ASSERT len(e.entity_path) > 0
```

### TS-107-P3: Kotlin Entity Validity

**Property:** Property 2 from design.md
**Validates:** 107-REQ-3.3
**Type:** property
**Description:** For any valid Kotlin source, entities have valid types and names.

**For any:** class_name in `[A-Z][a-zA-Z0-9]{1,10}` (excluding Kotlin keywords), func_name in `[a-z][a-zA-Z0-9]{1,10}` (excluding Kotlin keywords)
**Invariant:** All entities have non-empty entity_name, valid entity_type.

**Assertion pseudocode:**
```
FOR ANY class_name, func_name IN strategies:
    source = f"class {class_name} {{ fun {func_name}() {{}} }}"
    tree = parse(source)
    entities = analyzer.extract_entities(tree, "gen.kt")
    FOR e IN entities:
        ASSERT len(e.entity_name) > 0
        ASSERT e.entity_type in EntityType
```

### TS-107-P4: Dart Entity Validity

**Property:** Property 2 from design.md
**Validates:** 107-REQ-4.3
**Type:** property
**Description:** For any valid Dart source, entities have valid types and names.

**For any:** class_name in `[A-Z][a-zA-Z0-9]{1,10}` (excluding Dart keywords), method_name in `[a-z][a-zA-Z0-9]{1,10}` (excluding Dart keywords)
**Invariant:** All entities have non-empty entity_name, valid entity_type.

**Assertion pseudocode:**
```
FOR ANY class_name, method_name IN strategies:
    source = f"class {class_name} {{ void {method_name}() {{}} }}"
    tree = parse(source)
    entities = analyzer.extract_entities(tree, "gen.dart")
    FOR e IN entities:
        ASSERT len(e.entity_name) > 0
        ASSERT e.entity_type in EntityType
```

### TS-107-P5: Elixir No-Class Invariant

**Property:** Property 7 from design.md
**Validates:** 107-REQ-2.4
**Type:** property
**Description:** Elixir analyzer never produces CLASS entities or EXTENDS edges.

**For any:** module_name in `[A-Z][a-zA-Z]{1,10}`, func_name in `[a-z][a-z_]{1,10}`
**Invariant:** No entity has type CLASS; no edge has relationship EXTENDS.

**Assertion pseudocode:**
```
FOR ANY module_name, func_name IN strategies:
    source = f"defmodule {module_name} do\n  def {func_name}(x), do: x\nend"
    tree = parse(source)
    entities = analyzer.extract_entities(tree, "gen.ex")
    ASSERT not any(e.entity_type == CLASS for e in entities)
    edges = analyzer.extract_edges(tree, "gen.ex", entities, {})
    ASSERT not any(e.relationship == EXTENDS for e in edges)
```

### TS-107-P6: Extension Uniqueness

**Property:** Property 4 from design.md
**Validates:** 107-REQ-5.2
**Type:** property
**Description:** No two registered analyzers share a file extension.

**For any:** N/A (deterministic check over registry)
**Invariant:** All extension sets are pairwise disjoint.

**Assertion pseudocode:**
```
registry = get_default_registry()
all_exts = []
FOR a IN registry.all_analyzers():
    FOR ext IN a.file_extensions:
        ASSERT ext not in all_exts
        all_exts.append(ext)
```

### TS-107-P7: Module Map Path Format

**Property:** Property 6 from design.md
**Validates:** 107-REQ-1.5, 107-REQ-2.6, 107-REQ-3.5, 107-REQ-4.5
**Type:** property
**Description:** Module map values are valid POSIX-style repo-relative paths.

**For any:** analyzer in new analyzers, files in a temp directory
**Invariant:** All values are non-empty, contain no backslash, do not start with `/`.

**Assertion pseudocode:**
```
FOR analyzer IN [CSharpAnalyzer, ElixirAnalyzer, KotlinAnalyzer, DartAnalyzer]:
    mm = analyzer.build_module_map(repo_root, files)
    FOR key, val IN mm.items():
        ASSERT len(val) > 0
        ASSERT "\\" not in val
        ASSERT not val.startswith("/")
```

## Edge Case Tests

### TS-107-E1: C# External Using Skipped

**Requirement:** 107-REQ-1.E1
**Type:** unit
**Description:** Using directive for external namespace is silently skipped.

**Preconditions:**
- A C# file with `using System;` and an empty module map.

**Input:**
- `using System;` with `module_map = {}`

**Expected:**
- No IMPORTS edge for System; no exception raised.

**Assertion pseudocode:**
```
edges = analyzer.extract_edges(tree, "test.cs", entities, {})
imports = [e for e in edges if e.relationship == IMPORTS]
ASSERT len(imports) == 0
```

### TS-107-E2: C# Multiple Namespaces

**Requirement:** 107-REQ-1.E2
**Type:** unit
**Description:** Multiple namespaces in one file produce separate MODULE entities.

**Preconditions:**
- A C# file with two namespace declarations.

**Input:**
```csharp
namespace Ns1 { class A {} }
namespace Ns2 { class B {} }
```

**Expected:**
- Two MODULE entities: "Ns1" and "Ns2"

**Assertion pseudocode:**
```
entities = analyzer.extract_entities(tree, "multi.cs")
modules = [e for e in entities if e.entity_type == MODULE]
ASSERT len(modules) == 2
```

### TS-107-E3: Elixir Nested defmodule

**Requirement:** 107-REQ-2.E1
**Type:** unit
**Description:** Nested defmodule creates fully-qualified MODULE entity.

**Preconditions:**
- An Elixir file with nested modules.

**Input:**
```elixir
defmodule MyApp do
  defmodule Inner do
    def hello, do: :world
  end
end
```

**Expected:**
- MODULE entities include "MyApp" and "MyApp.Inner"

**Assertion pseudocode:**
```
entities = analyzer.extract_entities(tree, "app.ex")
module_names = {e.entity_name for e in entities if e.entity_type == MODULE}
ASSERT "MyApp" in module_names
ASSERT "MyApp.Inner" in module_names
```

### TS-107-E4: Elixir External Import Skipped

**Requirement:** 107-REQ-2.E2
**Type:** unit
**Description:** External use/import/alias/require silently skipped.

**Preconditions:**
- An Elixir file with `use Ecto.Schema` and empty module map.

**Input:**
- `use Ecto.Schema` with `module_map = {}`

**Expected:**
- No IMPORTS edge; no exception raised.

**Assertion pseudocode:**
```
edges = analyzer.extract_edges(tree, "test.ex", entities, {})
imports = [e for e in edges if e.relationship == IMPORTS]
ASSERT len(imports) == 0
```

### TS-107-E5: Kotlin Companion Object Methods

**Requirement:** 107-REQ-3.E1
**Type:** unit
**Description:** Companion object methods are qualified as ClassName.methodName.

**Preconditions:**
- A Kotlin file with a companion object.

**Input:**
```kotlin
class User {
    companion object {
        fun create(name: String): User = User()
    }
}
```

**Expected:**
- FUNCTION entity: "User.create" (not "User.Companion.create")

**Assertion pseudocode:**
```
entities = analyzer.extract_entities(tree, "User.kt")
func_names = {e.entity_name for e in entities if e.entity_type == FUNCTION}
ASSERT "User.create" in func_names
ASSERT "User.Companion.create" not in func_names
```

### TS-107-E6: Kotlin External Import Skipped

**Requirement:** 107-REQ-3.E2
**Type:** unit
**Description:** External import silently skipped.

**Preconditions:**
- Kotlin file with `import java.util.List` and empty module map.

**Expected:**
- No IMPORTS edge; no exception.

**Assertion pseudocode:**
```
edges = analyzer.extract_edges(tree, "test.kt", entities, {})
imports = [e for e in edges if e.relationship == IMPORTS]
ASSERT len(imports) == 0
```

### TS-107-E7: Dart SDK Import Skipped

**Requirement:** 107-REQ-4.E1
**Type:** unit
**Description:** Dart SDK and external package imports are skipped.

**Preconditions:**
- A Dart file with `import 'dart:async';` and `import 'package:flutter/material.dart';`.

**Expected:**
- No IMPORTS edges for SDK or external package imports.

**Assertion pseudocode:**
```
edges = analyzer.extract_edges(tree, "test.dart", entities, {})
imports = [e for e in edges if e.relationship == IMPORTS]
ASSERT len(imports) == 0
```

### TS-107-E8: Dart No Library Directive

**Requirement:** 107-REQ-4.E2
**Type:** unit
**Description:** No MODULE entity when library directive is absent.

**Preconditions:**
- A Dart file with no `library` directive.

**Input:**
- `class Widget {}`

**Expected:**
- No MODULE entities.

**Assertion pseudocode:**
```
entities = analyzer.extract_entities(tree, "widget.dart")
ASSERT not any(e.entity_type == MODULE for e in entities)
```

### TS-107-E9: Grammar Not Installed

**Requirement:** 107-REQ-5.3, 107-REQ-5.E1
**Type:** unit
**Description:** Missing grammar package causes graceful skip, not crash.

**Preconditions:**
- Mock the grammar import to raise ImportError.

**Input:**
- Build registry with mocked import failure for one analyzer.

**Expected:**
- Registry does not contain the failed analyzer.
- Other analyzers still registered.
- No exception propagated.

**Assertion pseudocode:**
```
WITH mock_import_error("tree_sitter_c_sharp"):
    registry = _build_default_registry()
    ASSERT registry.get_analyzer(".cs") is None
    ASSERT registry.get_analyzer(".py") is not None  # others unaffected
```

## Integration Smoke Tests

### TS-107-SMOKE-1: Full Analysis with New Languages

**Execution Path:** Path 1 from design.md
**Description:** analyze_codebase() on a repo with all four new language files produces correct languages_analyzed.

**Setup:** Temp directory with minimal source files for C#, Elixir, Kotlin, and Dart. In-memory DuckDB with full schema. No mocks on analyzers or entity pipeline.

**Trigger:** `analyze_codebase(tmp_path, conn)`

**Expected side effects:**
- `result.languages_analyzed` includes "csharp", "elixir", "kotlin", "dart"
- Entities inserted into DuckDB (query entity_graph table)
- Entity count > 0 for each language

**Must NOT satisfy with:** Mocking any analyzer's extract_entities or extract_edges.

**Assertion pseudocode:**
```
conn = duckdb.connect(":memory:")
apply_schema_and_migrations(conn)
create_files(tmp_path, {".cs": CS_SOURCE, ".ex": EX_SOURCE, ".kt": KT_SOURCE, ".dart": DART_SOURCE})
result = analyze_codebase(tmp_path, conn)
ASSERT "csharp" in result.languages_analyzed
ASSERT "elixir" in result.languages_analyzed
ASSERT "kotlin" in result.languages_analyzed
ASSERT "dart" in result.languages_analyzed
rows = conn.execute("SELECT language, COUNT(*) FROM entity_graph GROUP BY language").fetchall()
lang_counts = {r[0]: r[1] for r in rows}
ASSERT lang_counts.get("csharp", 0) > 0
ASSERT lang_counts.get("elixir", 0) > 0
ASSERT lang_counts.get("kotlin", 0) > 0
ASSERT lang_counts.get("dart", 0) > 0
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 107-REQ-1.1 | TS-107-1, TS-107-P1 | unit, property |
| 107-REQ-1.2 | TS-107-1 | unit |
| 107-REQ-1.3 | TS-107-2, TS-107-P2 | unit, property |
| 107-REQ-1.4 | TS-107-3 | unit |
| 107-REQ-1.5 | TS-107-4, TS-107-P7 | unit, property |
| 107-REQ-1.E1 | TS-107-E1 | unit |
| 107-REQ-1.E2 | TS-107-E2 | unit |
| 107-REQ-2.1 | TS-107-5, TS-107-P1 | unit, property |
| 107-REQ-2.2 | TS-107-5 | unit |
| 107-REQ-2.3 | TS-107-6, TS-107-P5 | unit, property |
| 107-REQ-2.4 | TS-107-6, TS-107-P5 | unit, property |
| 107-REQ-2.5 | TS-107-7 | unit |
| 107-REQ-2.6 | TS-107-8, TS-107-P7 | unit, property |
| 107-REQ-2.E1 | TS-107-E3 | unit |
| 107-REQ-2.E2 | TS-107-E4 | unit |
| 107-REQ-3.1 | TS-107-9, TS-107-P1 | unit, property |
| 107-REQ-3.2 | TS-107-9 | unit |
| 107-REQ-3.3 | TS-107-10, TS-107-P3 | unit, property |
| 107-REQ-3.4 | TS-107-11 | unit |
| 107-REQ-3.5 | TS-107-12, TS-107-P7 | unit, property |
| 107-REQ-3.E1 | TS-107-E5 | unit |
| 107-REQ-3.E2 | TS-107-E6 | unit |
| 107-REQ-4.1 | TS-107-13, TS-107-P1 | unit, property |
| 107-REQ-4.2 | TS-107-13 | unit |
| 107-REQ-4.3 | TS-107-14, TS-107-15, TS-107-P4 | unit, property |
| 107-REQ-4.4 | TS-107-16 | unit |
| 107-REQ-4.5 | TS-107-17, TS-107-P7 | unit, property |
| 107-REQ-4.E1 | TS-107-E7 | unit |
| 107-REQ-4.E2 | TS-107-15, TS-107-E8 | unit |
| 107-REQ-5.1 | TS-107-18 | unit |
| 107-REQ-5.2 | TS-107-18, TS-107-P6 | unit, property |
| 107-REQ-5.3 | TS-107-E9 | unit |
| 107-REQ-5.4 | TS-107-19 | integration |
| 107-REQ-5.E1 | TS-107-E9 | unit |
| 107-REQ-6.1 | TS-107-18 | unit |
| 107-REQ-6.2 | TS-107-SMOKE-1 | integration |
| Property 1 | TS-107-P1 | property |
| Property 2 | TS-107-P2, P3, P4 | property |
| Property 3 | (covered by TS-107-3, 7, 11, 16) | unit |
| Property 4 | TS-107-P6 | property |
| Property 5 | TS-107-E9 | unit |
| Property 6 | TS-107-P7 | property |
| Property 7 | TS-107-P5 | property |
