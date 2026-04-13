# Test Specification: Multi-Language Entity Graph

## Test Environment

- **Framework:** pytest with `tmp_path` fixtures for isolated repo structures
- **Mocking:** Tree-sitter grammars are real (not mocked); test inputs are
  small source snippets written to `tmp_path`
- **DuckDB:** Reuse existing DuckDB test fixtures with all migrations applied
  (through v9)
- **Assertion style:** Exact entity/edge counts and natural key matching

## Unit Tests

### Framework Tests

#### TS-102-1: Protocol Compliance

**Requirement:** 102-REQ-1.1

**Contract:** Every registered analyzer is an instance of `LanguageAnalyzer`
protocol and exposes `language_name: str`, `file_extensions: set[str]`,
`make_parser()`, `extract_entities()`, `extract_edges()`, and
`build_module_map()`.

**Preconditions:** Default registry is initialized.

**Assertions:**
- Each analyzer in the registry satisfies `isinstance(a, LanguageAnalyzer)`
- `language_name` is a non-empty string
- `file_extensions` is a non-empty set of strings, each starting with `.`

---

#### TS-102-2: Registry Extension Mapping

**Requirement:** 102-REQ-1.2

**Contract:** The registry maps each file extension to exactly one analyzer.
Registering a duplicate extension raises `ValueError`.

**Preconditions:** Empty registry.

**Steps:**
1. Register analyzer A with extensions `{".py"}`
2. Assert `get_analyzer(".py")` returns A
3. Register analyzer B with extensions `{".py"}` -- expect `ValueError`
4. Assert `get_analyzer(".rs")` returns `None`

---

#### TS-102-3: Language Detection

**Requirement:** 102-REQ-1.3

**Contract:** `detect_languages(repo_root)` returns only analyzers whose
extensions match files present in the repository.

**Preconditions:** `tmp_path` with `main.go` and `lib.rs` files.

**Assertions:**
- Returned list includes `GoAnalyzer` and `RustAnalyzer`
- Does not include `PythonAnalyzer`, `JavaAnalyzer`, etc.

---

#### TS-102-4: File Scanning

**Requirement:** 102-REQ-1.4

**Contract:** `_scan_files(repo_root, extensions)` returns files matching
extensions, sorted alphabetically, respecting `.gitignore`.

**Preconditions:** `tmp_path` with `a.py`, `b.py`, `c.txt`, and a
`.gitignore` containing `b.py`.

**Assertions:**
- Returns `[a.py]` (b.py excluded by gitignore, c.txt wrong extension)
- Paths are sorted

---

### Per-Language Entity Extraction

#### TS-102-5: Python Entities and Edges

**Requirement:** 102-REQ-2.1, 102-REQ-3.1, 102-REQ-6.1, 102-REQ-6.2

**Contract:** PythonAnalyzer produces identical entities and edges as the
pre-refactoring `static_analysis.py` for the same input.

**Preconditions:** `tmp_path` with a Python file containing a class with a
method, a top-level function, and an import statement. A second file is
imported by the first.

**Input:**
```python
# models.py
class User:
    def validate(self):
        pass

def helper():
    pass
```
```python
# views.py
from models import User
class UserView(User):
    def render(self):
        pass
```

**Assertions:**
- Entities: 2 FILE, 2 CLASS (`User`, `UserView`), 3 FUNCTION
  (`User.validate`, `helper`, `UserView.render`)
- Edges: CONTAINS (file->class, file->function, class->method),
  IMPORTS (views.py -> models.py), EXTENDS (UserView -> User)
- `language_name` is `"python"`

---

#### TS-102-6: Go Entities and Edges

**Requirement:** 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2

**Contract:** GoAnalyzer extracts struct, interface, function, and method
entities with correct containment and import edges.

**Input:**
```go
package main

import "fmt"

type Server struct {}

type Handler interface {
    Handle()
}

func NewServer() *Server { return nil }

func (s *Server) Start() {}
```

**Assertions:**
- Entities: 1 FILE, 1 MODULE (`main`), 2 CLASS (`Server`, `Handler`),
  2 FUNCTION (`NewServer`, `Server.Start`)
- Edges: CONTAINS (file->struct, file->interface, file->func),
  IMPORTS edge for `"fmt"` is skipped (external package, not in repo)
- No EXTENDS edges

---

#### TS-102-7: Rust Entities and Edges

**Requirement:** 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2

**Contract:** RustAnalyzer extracts struct, enum, trait, function entities
with containment and use edges.

**Input:**
```rust
mod utils;

pub struct Config {
    pub name: String,
}

pub enum Status {
    Active,
    Inactive,
}

pub trait Processor {
    fn process(&self);
}

pub fn initialize() {}

impl Config {
    pub fn new() -> Self { todo!() }
}
```

**Assertions:**
- Entities: 1 FILE, 1 MODULE (`utils`), 3 CLASS (`Config`, `Status`,
  `Processor`), 2 FUNCTION (`initialize`, `Config.new`)
- Edges: CONTAINS edges for all parent-child relationships
- `use` statements generate IMPORTS edges when resolvable
- No EXTENDS edges

---

#### TS-102-8: TypeScript Entities and Edges

**Requirement:** 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3

**Contract:** TypeScriptAnalyzer extracts class, interface, function entities
with imports and extends edges.

**Input:**
```typescript
import { Base } from './base';

interface Renderable {
    render(): void;
}

class Component extends Base {
    update(): void {}
}

export function createApp(): void {}
```

**Assertions:**
- Entities: 1 FILE, 2 CLASS (`Renderable`, `Component`), 2 FUNCTION
  (`Component.update`, `createApp`)
- Edges: IMPORTS (file -> base.ts), EXTENDS (Component -> Base),
  CONTAINS edges
- `language_name` is `"typescript"`

---

#### TS-102-9: JavaScript Entities and Edges

**Requirement:** 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.3

**Contract:** JavaScriptAnalyzer extracts class, function entities with
imports and extends edges. No interface extraction.

**Input:**
```javascript
import { EventEmitter } from './events';

class App extends EventEmitter {
    start() {}
}

function bootstrap() {}

const init = () => {};
```

**Assertions:**
- Entities: 1 FILE, 1 CLASS (`App`), 3 FUNCTION (`App.start`, `bootstrap`,
  `init`)
- Edges: IMPORTS (file -> events.js), EXTENDS (App -> EventEmitter),
  CONTAINS edges
- `language_name` is `"javascript"`

---

#### TS-102-10: Java Entities and Edges

**Requirement:** 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3

**Contract:** JavaAnalyzer extracts class, interface, enum, method entities
with package, import, and extends/implements edges.

**Input:**
```java
package com.example;

import com.example.base.BaseService;

public class UserService extends BaseService {
    public void createUser() {}
}

interface Auditable {
    void audit();
}

enum Role {
    ADMIN, USER
}
```

**Assertions:**
- Entities: 1 FILE, 1 MODULE (`com.example`), 3 CLASS (`UserService`,
  `Auditable`, `Role`), 1 FUNCTION (`UserService.createUser`)
- Edges: IMPORTS, EXTENDS (UserService -> BaseService), CONTAINS
- `language_name` is `"java"`

---

#### TS-102-11: C Entities and Edges

**Requirement:** 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2

**Contract:** CAnalyzer extracts struct and function entities with include
edges. No module or extends extraction.

**Input:**
```c
#include "utils.h"
#include <stdio.h>

struct Config {
    int port;
};

void initialize(struct Config *cfg) {}
```

**Assertions:**
- Entities: 1 FILE, 1 CLASS (`Config`), 1 FUNCTION (`initialize`)
- Edges: IMPORTS (file -> utils.h, if exists), CONTAINS
- Angle-bracket include (`<stdio.h>`) is skipped
- No EXTENDS edges, no MODULE entities

---

#### TS-102-12: C++ Entities and Edges

**Requirement:** 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.3

**Contract:** CppAnalyzer extracts class, struct, namespace, function
entities with include and extends edges.

**Input:**
```cpp
#include "base.hpp"

namespace app {

class Server : public Base {
public:
    void start();
};

void configure() {}

}
```

**Assertions:**
- Entities: 1 FILE, 1 MODULE (`app`), 1 CLASS (`Server`),
  2 FUNCTION (`Server.start`, `configure`)
- Edges: IMPORTS (file -> base.hpp), EXTENDS (Server -> Base),
  CONTAINS (namespace->class, class->method)
- `language_name` is `"cpp"`

---

#### TS-102-13: Ruby Entities and Edges

**Requirement:** 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.3

**Contract:** RubyAnalyzer extracts module, class, method entities with
require and extends edges.

**Input:**
```ruby
require_relative 'base'

module Services
  class UserService < Base
    def create_user
    end
  end
end

def standalone_helper
end
```

**Assertions:**
- Entities: 1 FILE, 1 MODULE (`Services`), 1 CLASS (`UserService`),
  2 FUNCTION (`UserService.create_user`, `standalone_helper`)
- Edges: IMPORTS (file -> base.rb), EXTENDS (UserService -> Base),
  CONTAINS (module->class, class->method, file->function)
- `language_name` is `"ruby"`

---

### Module Map and Import Resolution

#### TS-102-14: Module Map Per Language

**Requirement:** 102-REQ-3.2

**Contract:** Each language analyzer's `build_module_map()` returns a
dictionary that maps import identifiers to repo-relative file paths.

**Assertions per language:**
- **Python:** `"pkg.module"` -> `"pkg/module.py"` (dotted path)
- **Go:** `"server"` -> `"pkg/server"` (package directory)
- **Rust:** `"crate::utils"` -> `"src/utils.rs"` (crate path)
- **TypeScript:** `"./components/button"` -> `"src/components/button.ts"`
- **Java:** `"com.example.Foo"` -> `"src/com/example/Foo.java"`
- **C/C++:** `"utils/math.h"` -> `"utils/math.h"` (relative header)
- **Ruby:** `"services/user"` -> `"lib/services/user.rb"`

---

### Orchestration Tests

#### TS-102-15: Mixed-Language Analysis

**Requirement:** 102-REQ-4.1, 102-REQ-4.2

**Contract:** `analyze_codebase()` on a repo with Python and Go files
produces entities from both languages in a single `AnalysisResult`.

**Preconditions:** `tmp_path` with `main.py` (class + function) and
`main.go` (struct + function).

**Assertions:**
- `entities_upserted` includes entities from both languages
- `languages_analyzed` contains `("go", "python")` (sorted)

---

#### TS-102-16: Languages Analyzed Field

**Requirement:** 102-REQ-4.3

**Contract:** `AnalysisResult.languages_analyzed` lists exactly the languages
that were analyzed.

**Assertions:**
- Python-only repo: `("python",)`
- Mixed Python+Go: `("go", "python")` (sorted alphabetically)
- No source files: `()`

---

#### TS-102-17: Soft-Delete Across Languages

**Requirement:** 102-REQ-4.4

**Contract:** When a file is removed between analysis runs, its entities are
soft-deleted regardless of language.

**Preconditions:**
1. Run `analyze_codebase` with `main.py` and `main.go`
2. Remove `main.go`
3. Run `analyze_codebase` again

**Assertions:**
- Go entities from `main.go` are soft-deleted (`deleted_at IS NOT NULL`)
- Python entities from `main.py` remain active

---

### Schema Tests

#### TS-102-18: Migration v9

**Requirement:** 102-REQ-5.1

**Contract:** Migration v9 adds a nullable `language` VARCHAR column to
`entity_graph`.

**Preconditions:** DuckDB with migrations through v8 applied.

**Assertions:**
- After v9: `entity_graph` has a `language` column
- Column is nullable
- Existing queries continue to work

---

#### TS-102-19: Language Column Backfill

**Requirement:** 102-REQ-5.2

**Contract:** Migration v9 backfills existing entities with
`language = 'python'`.

**Preconditions:** DuckDB with v8 migrations, 3 existing entities.

**Assertions:**
- After v9: all 3 entities have `language = 'python'`

---

#### TS-102-20: New Entity Language Tag

**Requirement:** 102-REQ-5.3, 102-REQ-2.4

**Contract:** New entities created after v9 have the correct language value
set by the analyzer.

**Preconditions:** DuckDB with v9 migrations.

**Steps:**
1. Run `analyze_codebase` on a repo with `main.go` and `app.py`

**Assertions:**
- Go file entities have `language = 'go'`
- Python file entities have `language = 'python'`

---

### Backward Compatibility Tests

#### TS-102-21: Python Backward Compatibility

**Requirement:** 102-REQ-6.1, 102-REQ-6.2

**Contract:** For a Python-only codebase, the entity natural keys and edge
triples produced by the refactored code are identical to those produced by
the pre-Spec-102 `static_analysis.py`.

**Preconditions:** `tmp_path` with a non-trivial Python project (3+ files,
classes, imports, inheritance).

**Assertions:**
- Same set of `(entity_type, entity_path, entity_name)` tuples
- Same set of `(source_type+path+name, target_type+path+name, relationship)`
  edge triples
- `AnalysisResult.entities_upserted` and `edges_upserted` match

---

#### TS-102-22: Qualified Name Construction

**Requirement:** 102-REQ-2.3

**Contract:** Nested constructs use `Parent.child` qualified names across all
languages.

**Assertions per language:**
- Python method: `User.validate`
- Go method: `Server.Start`
- Rust impl method: `Config.new`
- TypeScript method: `Component.update`
- Java method: `UserService.createUser`
- C++ method: `Server.start`
- Ruby method: `UserService.create_user`

---

## Edge Case Tests

#### TS-102-E1: Unparseable File

**Requirement:** 102-REQ-2.E1

**Contract:** A source file with syntax errors is logged and skipped.

**Preconditions:** `tmp_path` with a syntactically invalid Go file.

**Assertions:**
- File is skipped, no entities extracted
- Warning logged
- Other valid files in the same repo are still processed

---

#### TS-102-E2: Missing Grammar Package

**Requirement:** 102-REQ-2.E2

**Contract:** If a tree-sitter grammar package is not installed, the language
is skipped with an info log.

**Preconditions:** Mock the grammar import to raise `ImportError`.

**Assertions:**
- Language is skipped
- Info message logged
- Other languages still analyzed

---

#### TS-102-E3: Unregistered Extension

**Requirement:** 102-REQ-1.E1

**Contract:** Files with unregistered extensions are not analyzed.

**Preconditions:** `tmp_path` with `file.xyz` (unregistered extension).

**Assertions:**
- No entities created for `file.xyz`
- No error raised

---

#### TS-102-E4: Non-Git Repo Fallback

**Requirement:** 102-REQ-1.E2

**Contract:** `_scan_files()` works in a non-git directory by falling back
to directory walk.

**Preconditions:** `tmp_path` (not a git repo) with `main.py` and a
`node_modules/dep.py` file.

**Assertions:**
- `main.py` is returned
- `node_modules/dep.py` is excluded

---

#### TS-102-E5: No Source Files Found

**Requirement:** 102-REQ-4.E1

**Contract:** When no registered extensions match any files, analysis returns
zero counts.

**Preconditions:** `tmp_path` with only `.txt` and `.md` files.

**Assertions:**
- `AnalysisResult(0, 0, 0, ())`

---

#### TS-102-E6: Analyzer Crash Isolation

**Requirement:** 102-REQ-4.E2

**Contract:** If one language analyzer raises an exception, other languages
are still analyzed.

**Preconditions:** `tmp_path` with Go and Python files. Mock GoAnalyzer to
raise `RuntimeError`.

**Assertions:**
- Python entities are still created
- Error logged for Go
- `languages_analyzed` contains only `"python"`

---

#### TS-102-E7: Unresolvable Import

**Requirement:** 102-REQ-3.4

**Contract:** An import referencing an external dependency creates no edge.

**Preconditions:** Go file with `import "github.com/pkg/errors"`.

**Assertions:**
- No IMPORTS edge created for the external package
- No error or warning

---

## Property Tests

#### TS-102-P1: Entity Validity

**Requirement:** 102-REQ-2.2, 102-REQ-2.3

**Contract:** For any source input and any language, `extract_entities()`
produces entities where every entity has a non-empty `entity_name`, a
non-empty `entity_path`, and a valid `EntityType`.

**Strategy:** Generate random small source snippets per language using
Hypothesis text strategy filtered to valid syntax patterns.

---

#### TS-102-P2: Edge Referential Integrity

**Requirement:** 102-REQ-3.1

**Contract:** For any source input, every edge's `source_id` and `target_id`
references an entity from the same extraction run (or a sentinel ID matching
the `path:` or `class:` pattern).

**Strategy:** Extract entities and edges from generated source files; verify
all edge IDs are in the entity set or match sentinel patterns.

---

#### TS-102-P3: Upsert Idempotency

**Requirement:** 102-REQ-4.4, CP-3

**Contract:** Running `analyze_codebase()` twice on the same repo produces
the same entity count and no duplicate natural keys.

**Strategy:** Generate a small multi-language repo, run analysis twice,
assert `entities_upserted` is the same and no duplicates in DB.

---

#### TS-102-P4: Scan Subset

**Requirement:** 102-REQ-1.4

**Contract:** `_scan_files(repo_root, extensions)` returns a subset of all
files in the repository, and every returned file has an extension in the
given set.

**Strategy:** Generate a directory with random files, call `_scan_files`,
verify the subset property.

---

## Integration / Smoke Tests

#### TS-102-SMOKE-1: Full Multi-Language Analysis

**Requirement:** All

**Contract:** End-to-end analysis of a mixed-language repository (Python +
Go + TypeScript) produces entities, edges, and correct `languages_analyzed`.

**Preconditions:** `tmp_path` with:
- `app.py` (class, function, import)
- `server.go` (struct, function)
- `client.ts` (class, function, import)

**Assertions:**
- Entity count >= 3 files + classes + functions
- Edge count >= contains edges + at least 1 import
- `languages_analyzed` includes `"python"`, `"go"`, `"typescript"`
- DB `language` column populated correctly

---

#### TS-102-SMOKE-2: Python Backward Compatibility End-to-End

**Requirement:** 102-REQ-6.1

**Contract:** Running analysis on a Python-only repo with the refactored
code produces DB state identical to the pre-refactoring code.

**Preconditions:** `tmp_path` with a Python package (3 files, __init__.py,
imports between them, class inheritance).

**Assertions:**
- Entity natural keys match pre-refactoring output
- Edge triples match
- `languages_analyzed == ("python",)`

---

#### TS-102-SMOKE-3: Incremental Analysis with Language Changes

**Requirement:** 102-REQ-4.4

**Contract:** Adding a new language's files and re-running analysis adds
new entities without disrupting existing ones; removing a language's files
soft-deletes its entities.

**Steps:**
1. Create `tmp_path` with `app.py`, run analysis
2. Add `server.go`, run analysis again
3. Assert Python entities unchanged, Go entities added
4. Remove `server.go`, run analysis again
5. Assert Go entities soft-deleted, Python entities unchanged
