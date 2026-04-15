"""Tests for per-language entity and edge extraction.

Test Spec: TS-102-5 through TS-102-14, TS-102-22, TS-102-E1, TS-102-E2, TS-102-E7
Requirements: 102-REQ-2.1, 102-REQ-2.3, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3,
              102-REQ-3.4, 102-REQ-6.1, 102-REQ-6.2
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from agent_fox.knowledge.entities import EdgeType, EntityType
from agent_fox.knowledge.static_analysis import _parse_file
from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with base schema and all migrations applied."""
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TS-102-5: Python entities and edges
# ---------------------------------------------------------------------------


class TestPythonEntitiesAndEdges:
    """TS-102-5: PythonAnalyzer extracts correct entities and edges.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-6.1, 102-REQ-6.2
    """

    def test_python_analyzer_language_name(self) -> None:
        """PythonAnalyzer.language_name is 'python'."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

        analyzer = PythonAnalyzer()
        assert analyzer.language_name == "python"

    def test_python_analyzer_file_extensions(self) -> None:
        """PythonAnalyzer.file_extensions includes '.py'."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

        analyzer = PythonAnalyzer()
        assert ".py" in analyzer.file_extensions

    def test_python_extract_entities_class_method_function(self, tmp_path: Path) -> None:
        """PythonAnalyzer extracts FILE, CLASS, and FUNCTION entities from a Python file."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

        py_file = tmp_path / "models.py"
        py_file.write_text(
            """\
class User:
    def validate(self):
        pass

def helper():
    pass
"""
        )
        analyzer = PythonAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(py_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "models.py")
        names = {e.entity_name for e in entities}
        types = {e.entity_name: e.entity_type for e in entities}

        assert "models.py" in names
        assert types.get("models.py") == EntityType.FILE
        assert "User" in names
        assert types.get("User") == EntityType.CLASS
        assert "User.validate" in names
        assert types.get("User.validate") == EntityType.FUNCTION
        assert "helper" in names
        assert types.get("helper") == EntityType.FUNCTION

    def test_python_entities_via_analyze_codebase(self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection) -> None:
        """analyze_codebase produces correct Python entities across multiple files."""
        from agent_fox.knowledge.static_analysis import analyze_codebase

        (tmp_path / "models.py").write_text(
            """\
class User:
    def validate(self):
        pass

def helper():
    pass
"""
        )
        (tmp_path / "views.py").write_text(
            """\
from models import User

class UserView(User):
    def render(self):
        pass
"""
        )

        result = analyze_codebase(tmp_path, entity_conn)

        rows = entity_conn.execute(
            "SELECT entity_type, entity_name FROM entity_graph WHERE deleted_at IS NULL"
        ).fetchall()
        type_name_set = {(r[0], r[1]) for r in rows}

        # 2 FILE entities
        file_entities = [r for r in rows if r[0] == "file"]
        assert len(file_entities) == 2

        # 2 CLASS entities
        class_entities = [r for r in rows if r[0] == "class"]
        assert len(class_entities) == 2

        # 3 FUNCTION entities
        function_entities = [r for r in rows if r[0] == "function"]
        assert len(function_entities) == 3

        # Qualified names are correct
        assert ("function", "User.validate") in type_name_set
        assert ("function", "UserView.render") in type_name_set
        assert ("function", "helper") in type_name_set

        # languages_analyzed field is added by refactored analyze_codebase
        assert result.languages_analyzed == ("python",)

    def test_python_edges_contains_and_imports(self, tmp_path: Path) -> None:
        """PythonAnalyzer extracts CONTAINS and IMPORTS edges."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

        py_file = tmp_path / "views.py"
        py_file.write_text(
            """\
from models import User

class UserView:
    def render(self):
        pass
"""
        )
        module_map = {"models": "models.py"}

        analyzer = PythonAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(py_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "views.py")
        edges = analyzer.extract_edges(tree, "views.py", entities, module_map)
        relationships = {e.relationship for e in edges}

        assert EdgeType.CONTAINS in relationships
        assert EdgeType.IMPORTS in relationships

    def test_python_extends_edge_sentinel(self, tmp_path: Path) -> None:
        """PythonAnalyzer emits an EXTENDS sentinel edge for cross-file base classes."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

        py_file = tmp_path / "views.py"
        py_file.write_text(
            """\
class UserView(User):
    def render(self):
        pass
"""
        )
        analyzer = PythonAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(py_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "views.py")
        edges = analyzer.extract_edges(tree, "views.py", entities, {})
        relationships = {e.relationship for e in edges}

        assert EdgeType.EXTENDS in relationships


# ---------------------------------------------------------------------------
# TS-102-6: Go entities and edges
# ---------------------------------------------------------------------------


class TestGoEntitiesAndEdges:
    """TS-102-6: GoAnalyzer extracts struct, interface, function, and method entities.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1
    """

    def test_go_analyzer_language_name(self) -> None:
        """GoAnalyzer.language_name is 'go'."""
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        analyzer = GoAnalyzer()
        assert analyzer.language_name == "go"

    def test_go_extract_entities(self, tmp_path: Path) -> None:
        """GoAnalyzer extracts FILE, MODULE, CLASS (struct/interface), and FUNCTION entities."""
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        go_file = tmp_path / "server.go"
        go_file.write_text(
            """\
package main

import "fmt"

type Server struct {}

type Handler interface {
    Handle()
}

func NewServer() *Server { return nil }

func (s *Server) Start() {}
"""
        )
        analyzer = GoAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(go_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "server.go")
        names = {e.entity_name for e in entities}
        types = {e.entity_name: e.entity_type for e in entities}

        # FILE entity
        assert "server.go" in names
        assert types.get("server.go") == EntityType.FILE

        # MODULE entity for package main
        assert "main" in names
        assert types.get("main") == EntityType.MODULE

        # CLASS entities for struct and interface
        assert "Server" in names
        assert types.get("Server") == EntityType.CLASS
        assert "Handler" in names
        assert types.get("Handler") == EntityType.CLASS

        # FUNCTION entities
        assert "NewServer" in names
        assert types.get("NewServer") == EntityType.FUNCTION
        # Method is qualified as Type.Method
        assert "Server.Start" in names
        assert types.get("Server.Start") == EntityType.FUNCTION

    def test_go_contains_edges(self, tmp_path: Path) -> None:
        """GoAnalyzer extracts CONTAINS edges."""
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        go_file = tmp_path / "server.go"
        go_file.write_text(
            """\
package main

type Server struct {}

func NewServer() *Server { return nil }
"""
        )
        analyzer = GoAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(go_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "server.go")
        edges = analyzer.extract_edges(tree, "server.go", entities, {})
        relationships = {e.relationship for e in edges}

        assert EdgeType.CONTAINS in relationships

    def test_go_no_extends_edges(self, tmp_path: Path) -> None:
        """GoAnalyzer does not extract EXTENDS edges (Go uses embedding, not inheritance)."""
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        go_file = tmp_path / "server.go"
        go_file.write_text("package main\n\ntype Server struct {}\n")
        analyzer = GoAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(go_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "server.go")
        edges = analyzer.extract_edges(tree, "server.go", entities, {})
        relationships = {e.relationship for e in edges}

        assert EdgeType.EXTENDS not in relationships, "Go should not produce EXTENDS edges"

    def test_go_external_import_skipped(self, tmp_path: Path) -> None:
        """GoAnalyzer does not produce IMPORTS edges for external packages."""
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        go_file = tmp_path / "main.go"
        go_file.write_text('package main\n\nimport "fmt"\n\nfunc main() {}\n')
        analyzer = GoAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(go_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "main.go")
        # fmt is external; module_map has no entry for it
        edges = analyzer.extract_edges(tree, "main.go", entities, {})
        imports_edges = [e for e in edges if e.relationship == EdgeType.IMPORTS]

        assert len(imports_edges) == 0, "External Go package 'fmt' must not produce an IMPORTS edge"


# ---------------------------------------------------------------------------
# TS-102-7: Rust entities and edges
# ---------------------------------------------------------------------------


class TestRustEntitiesAndEdges:
    """TS-102-7: RustAnalyzer extracts struct, enum, trait, and function entities.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1
    """

    def test_rust_analyzer_language_name(self) -> None:
        """RustAnalyzer.language_name is 'rust'."""
        from agent_fox.knowledge.lang.rust_lang import RustAnalyzer

        analyzer = RustAnalyzer()
        assert analyzer.language_name == "rust"

    def test_rust_extract_entities(self, tmp_path: Path) -> None:
        """RustAnalyzer extracts FILE, MODULE, CLASS (struct/enum/trait), and FUNCTION entities."""
        from agent_fox.knowledge.lang.rust_lang import RustAnalyzer

        rs_file = tmp_path / "lib.rs"
        rs_file.write_text(
            """\
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
"""
        )
        analyzer = RustAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(rs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "lib.rs")
        names = {e.entity_name for e in entities}
        types = {e.entity_name: e.entity_type for e in entities}

        assert "lib.rs" in names
        assert types.get("lib.rs") == EntityType.FILE
        assert "utils" in names
        assert types.get("utils") == EntityType.MODULE
        assert "Config" in names
        assert types.get("Config") == EntityType.CLASS
        assert "Status" in names
        assert types.get("Status") == EntityType.CLASS
        assert "Processor" in names
        assert types.get("Processor") == EntityType.CLASS
        assert "initialize" in names
        assert types.get("initialize") == EntityType.FUNCTION
        assert "Config.new" in names
        assert types.get("Config.new") == EntityType.FUNCTION

    def test_rust_no_extends_edges(self, tmp_path: Path) -> None:
        """RustAnalyzer does not extract EXTENDS edges."""
        from agent_fox.knowledge.lang.rust_lang import RustAnalyzer

        rs_file = tmp_path / "lib.rs"
        rs_file.write_text("pub struct Foo {}\n")
        analyzer = RustAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(rs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "lib.rs")
        edges = analyzer.extract_edges(tree, "lib.rs", entities, {})
        relationships = {e.relationship for e in edges}

        assert EdgeType.EXTENDS not in relationships, "Rust should not produce EXTENDS edges"


# ---------------------------------------------------------------------------
# TS-102-8: TypeScript entities and edges
# ---------------------------------------------------------------------------


class TestTypeScriptEntitiesAndEdges:
    """TS-102-8: TypeScriptAnalyzer extracts class, interface, function entities.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    def test_typescript_analyzer_language_name(self) -> None:
        """TypeScriptAnalyzer.language_name is 'typescript'."""
        from agent_fox.knowledge.lang.typescript_lang import TypeScriptAnalyzer

        analyzer = TypeScriptAnalyzer()
        assert analyzer.language_name == "typescript"

    def test_typescript_file_extensions(self) -> None:
        """TypeScriptAnalyzer handles .ts and .tsx files."""
        from agent_fox.knowledge.lang.typescript_lang import TypeScriptAnalyzer

        analyzer = TypeScriptAnalyzer()
        assert ".ts" in analyzer.file_extensions
        assert ".tsx" in analyzer.file_extensions

    def test_typescript_extract_entities(self, tmp_path: Path) -> None:
        """TypeScriptAnalyzer extracts FILE, CLASS (interface), and FUNCTION entities."""
        from agent_fox.knowledge.lang.typescript_lang import TypeScriptAnalyzer

        ts_file = tmp_path / "component.ts"
        ts_file.write_text(
            """\
import { Base } from './base';

interface Renderable {
    render(): void;
}

class Component extends Base {
    update(): void {}
}

export function createApp(): void {}
"""
        )
        analyzer = TypeScriptAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(ts_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "component.ts")
        names = {e.entity_name for e in entities}
        types = {e.entity_name: e.entity_type for e in entities}

        assert "component.ts" in names
        assert types.get("component.ts") == EntityType.FILE
        assert "Renderable" in names
        assert types.get("Renderable") == EntityType.CLASS
        assert "Component" in names
        assert types.get("Component") == EntityType.CLASS
        assert "Component.update" in names
        assert types.get("Component.update") == EntityType.FUNCTION
        assert "createApp" in names
        assert types.get("createApp") == EntityType.FUNCTION

    def test_typescript_extends_edge(self, tmp_path: Path) -> None:
        """TypeScriptAnalyzer emits EXTENDS edges for class extension."""
        from agent_fox.knowledge.lang.typescript_lang import TypeScriptAnalyzer

        ts_file = tmp_path / "component.ts"
        ts_file.write_text(
            """\
import { Base } from './base';

class Component extends Base {
    update(): void {}
}
"""
        )
        base_file = tmp_path / "base.ts"
        base_file.write_text("export class Base {}\n")

        analyzer = TypeScriptAnalyzer()
        module_map = {"./base": "base.ts"}
        parser = analyzer.make_parser()
        tree = _parse_file(ts_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "component.ts")
        edges = analyzer.extract_edges(tree, "component.ts", entities, module_map)
        relationships = {e.relationship for e in edges}

        assert EdgeType.EXTENDS in relationships
        assert EdgeType.IMPORTS in relationships


# ---------------------------------------------------------------------------
# TS-102-9: JavaScript entities and edges
# ---------------------------------------------------------------------------


class TestJavaScriptEntitiesAndEdges:
    """TS-102-9: JavaScriptAnalyzer extracts class and function entities.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.3
    """

    def test_javascript_analyzer_language_name(self) -> None:
        """JavaScriptAnalyzer.language_name is 'javascript'."""
        from agent_fox.knowledge.lang.typescript_lang import JavaScriptAnalyzer

        analyzer = JavaScriptAnalyzer()
        assert analyzer.language_name == "javascript"

    def test_javascript_file_extensions(self) -> None:
        """JavaScriptAnalyzer handles .js and .jsx files."""
        from agent_fox.knowledge.lang.typescript_lang import JavaScriptAnalyzer

        analyzer = JavaScriptAnalyzer()
        assert ".js" in analyzer.file_extensions
        assert ".jsx" in analyzer.file_extensions

    def test_javascript_extract_entities(self, tmp_path: Path) -> None:
        """JavaScriptAnalyzer extracts FILE, CLASS, and FUNCTION entities."""
        from agent_fox.knowledge.lang.typescript_lang import JavaScriptAnalyzer

        js_file = tmp_path / "app.js"
        js_file.write_text(
            """\
import { EventEmitter } from './events';

class App extends EventEmitter {
    start() {}
}

function bootstrap() {}

const init = () => {};
"""
        )
        analyzer = JavaScriptAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(js_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "app.js")
        names = {e.entity_name for e in entities}
        types = {e.entity_name: e.entity_type for e in entities}

        assert "app.js" in names
        assert types.get("app.js") == EntityType.FILE
        assert "App" in names
        assert types.get("App") == EntityType.CLASS
        assert "App.start" in names
        assert types.get("App.start") == EntityType.FUNCTION
        assert "bootstrap" in names
        assert types.get("bootstrap") == EntityType.FUNCTION
        assert "init" in names
        assert types.get("init") == EntityType.FUNCTION

    def test_javascript_no_interface_extraction(self, tmp_path: Path) -> None:
        """JavaScriptAnalyzer does not extract interface entities (JS has no interfaces)."""
        from agent_fox.knowledge.lang.typescript_lang import JavaScriptAnalyzer

        js_file = tmp_path / "app.js"
        js_file.write_text("class App {}\n")
        analyzer = JavaScriptAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(js_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "app.js")
        # No interface entity type in JS output
        interface_names: list[str] = []
        for e in entities:
            # If any entity has a name matching a known TS-only interface pattern, fail
            if e.entity_type == EntityType.CLASS and "interface" in e.entity_name.lower():
                interface_names.append(e.entity_name)
        # This check verifies no spurious interface entities appear
        assert len(interface_names) == 0


# ---------------------------------------------------------------------------
# TS-102-10: Java entities and edges
# ---------------------------------------------------------------------------


class TestJavaEntitiesAndEdges:
    """TS-102-10: JavaAnalyzer extracts class, interface, enum, and method entities.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    def test_java_analyzer_language_name(self) -> None:
        """JavaAnalyzer.language_name is 'java'."""
        from agent_fox.knowledge.lang.java_lang import JavaAnalyzer

        analyzer = JavaAnalyzer()
        assert analyzer.language_name == "java"

    def test_java_extract_entities(self, tmp_path: Path) -> None:
        """JavaAnalyzer extracts FILE, MODULE, CLASS (class/interface/enum), and FUNCTION entities."""
        from agent_fox.knowledge.lang.java_lang import JavaAnalyzer

        java_file = tmp_path / "UserService.java"
        java_file.write_text(
            """\
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
"""
        )
        analyzer = JavaAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(java_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "UserService.java")
        names = {e.entity_name for e in entities}
        types = {e.entity_name: e.entity_type for e in entities}

        assert "UserService.java" in names
        assert types.get("UserService.java") == EntityType.FILE
        assert "com.example" in names
        assert types.get("com.example") == EntityType.MODULE
        assert "UserService" in names
        assert types.get("UserService") == EntityType.CLASS
        assert "Auditable" in names
        assert types.get("Auditable") == EntityType.CLASS
        assert "Role" in names
        assert types.get("Role") == EntityType.CLASS
        assert "UserService.createUser" in names
        assert types.get("UserService.createUser") == EntityType.FUNCTION

    def test_java_extends_edge(self, tmp_path: Path) -> None:
        """JavaAnalyzer emits EXTENDS edges for class inheritance."""
        from agent_fox.knowledge.lang.java_lang import JavaAnalyzer

        java_file = tmp_path / "UserService.java"
        java_file.write_text(
            """\
package com.example;

public class UserService extends BaseService {
    public void createUser() {}
}
"""
        )
        analyzer = JavaAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(java_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "UserService.java")
        edges = analyzer.extract_edges(tree, "UserService.java", entities, {})
        relationships = {e.relationship for e in edges}

        assert EdgeType.EXTENDS in relationships


# ---------------------------------------------------------------------------
# TS-102-11: C entities and edges
# ---------------------------------------------------------------------------


class TestCEntitiesAndEdges:
    """TS-102-11: CAnalyzer extracts struct and function entities with include edges.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2
    """

    def test_c_analyzer_language_name(self) -> None:
        """CAnalyzer.language_name is 'c'."""
        from agent_fox.knowledge.lang.c_lang import CAnalyzer

        analyzer = CAnalyzer()
        assert analyzer.language_name == "c"

    def test_c_extract_entities(self, tmp_path: Path) -> None:
        """CAnalyzer extracts FILE, CLASS (struct), and FUNCTION entities."""
        from agent_fox.knowledge.lang.c_lang import CAnalyzer

        c_file = tmp_path / "server.c"
        c_file.write_text(
            """\
#include "utils.h"
#include <stdio.h>

struct Config {
    int port;
};

void initialize(struct Config *cfg) {}
"""
        )
        analyzer = CAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(c_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "server.c")
        names = {e.entity_name for e in entities}
        types = {e.entity_name: e.entity_type for e in entities}

        assert "server.c" in names
        assert types.get("server.c") == EntityType.FILE
        assert "Config" in names
        assert types.get("Config") == EntityType.CLASS
        assert "initialize" in names
        assert types.get("initialize") == EntityType.FUNCTION

    def test_c_no_module_entities(self, tmp_path: Path) -> None:
        """CAnalyzer does not produce MODULE entities (C has no module system)."""
        from agent_fox.knowledge.lang.c_lang import CAnalyzer

        c_file = tmp_path / "main.c"
        c_file.write_text("void main() {}\n")
        analyzer = CAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(c_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "main.c")
        module_entities = [e for e in entities if e.entity_type == EntityType.MODULE]
        assert len(module_entities) == 0, "C should not produce MODULE entities"

    def test_c_no_extends_edges(self, tmp_path: Path) -> None:
        """CAnalyzer does not produce EXTENDS edges (C has no inheritance)."""
        from agent_fox.knowledge.lang.c_lang import CAnalyzer

        c_file = tmp_path / "main.c"
        c_file.write_text("struct Foo { int x; };\nvoid bar() {}\n")
        analyzer = CAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(c_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "main.c")
        edges = analyzer.extract_edges(tree, "main.c", entities, {})
        relationships = {e.relationship for e in edges}

        assert EdgeType.EXTENDS not in relationships

    def test_c_angle_bracket_include_skipped(self, tmp_path: Path) -> None:
        """Angle-bracket includes like <stdio.h> are not resolved to IMPORTS edges."""
        from agent_fox.knowledge.lang.c_lang import CAnalyzer

        c_file = tmp_path / "main.c"
        c_file.write_text("#include <stdio.h>\n\nvoid main() {}\n")
        analyzer = CAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(c_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "main.c")
        edges = analyzer.extract_edges(tree, "main.c", entities, {})
        imports_edges = [e for e in edges if e.relationship == EdgeType.IMPORTS]

        assert len(imports_edges) == 0, "<stdio.h> is external and must not produce an IMPORTS edge"


# ---------------------------------------------------------------------------
# TS-102-12: C++ entities and edges
# ---------------------------------------------------------------------------


class TestCppEntitiesAndEdges:
    """TS-102-12: CppAnalyzer extracts class, struct, namespace, and function entities.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.3
    """

    def test_cpp_analyzer_language_name(self) -> None:
        """CppAnalyzer.language_name is 'cpp'."""
        from agent_fox.knowledge.lang.c_lang import CppAnalyzer

        analyzer = CppAnalyzer()
        assert analyzer.language_name == "cpp"

    def test_cpp_file_extensions(self) -> None:
        """CppAnalyzer handles .cpp, .hpp, .cc, .cxx, and .hh files."""
        from agent_fox.knowledge.lang.c_lang import CppAnalyzer

        analyzer = CppAnalyzer()
        for ext in (".cpp", ".hpp", ".cc", ".cxx", ".hh"):
            assert ext in analyzer.file_extensions, f"CppAnalyzer must handle {ext}"

    def test_cpp_extract_entities(self, tmp_path: Path) -> None:
        """CppAnalyzer extracts FILE, MODULE (namespace), CLASS, and FUNCTION entities."""
        from agent_fox.knowledge.lang.c_lang import CppAnalyzer

        cpp_file = tmp_path / "server.cpp"
        cpp_file.write_text(
            """\
#include "base.hpp"

namespace app {

class Server : public Base {
public:
    void start();
};

void configure() {}

}
"""
        )
        analyzer = CppAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cpp_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "server.cpp")
        names = {e.entity_name for e in entities}
        types = {e.entity_name: e.entity_type for e in entities}

        assert "server.cpp" in names
        assert types.get("server.cpp") == EntityType.FILE
        assert "app" in names
        assert types.get("app") == EntityType.MODULE
        assert "Server" in names
        assert types.get("Server") == EntityType.CLASS
        assert "Server.start" in names
        assert types.get("Server.start") == EntityType.FUNCTION
        assert "configure" in names
        assert types.get("configure") == EntityType.FUNCTION

    def test_cpp_extends_edge(self, tmp_path: Path) -> None:
        """CppAnalyzer emits EXTENDS edges for class inheritance."""
        from agent_fox.knowledge.lang.c_lang import CppAnalyzer

        cpp_file = tmp_path / "server.cpp"
        cpp_file.write_text(
            """\
class Server : public Base {
public:
    void start();
};
"""
        )
        analyzer = CppAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cpp_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "server.cpp")
        edges = analyzer.extract_edges(tree, "server.cpp", entities, {})
        relationships = {e.relationship for e in edges}

        assert EdgeType.EXTENDS in relationships


# ---------------------------------------------------------------------------
# TS-102-13: Ruby entities and edges
# ---------------------------------------------------------------------------


class TestRubyEntitiesAndEdges:
    """TS-102-13: RubyAnalyzer extracts module, class, and method entities.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.3
    """

    def test_ruby_analyzer_language_name(self) -> None:
        """RubyAnalyzer.language_name is 'ruby'."""
        from agent_fox.knowledge.lang.ruby_lang import RubyAnalyzer

        analyzer = RubyAnalyzer()
        assert analyzer.language_name == "ruby"

    def test_ruby_extract_entities(self, tmp_path: Path) -> None:
        """RubyAnalyzer extracts FILE, MODULE, CLASS, and FUNCTION entities."""
        from agent_fox.knowledge.lang.ruby_lang import RubyAnalyzer

        rb_file = tmp_path / "services.rb"
        rb_file.write_text(
            """\
require_relative 'base'

module Services
  class UserService < Base
    def create_user
    end
  end
end

def standalone_helper
end
"""
        )
        analyzer = RubyAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(rb_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "services.rb")
        names = {e.entity_name for e in entities}
        types = {e.entity_name: e.entity_type for e in entities}

        assert "services.rb" in names
        assert types.get("services.rb") == EntityType.FILE
        assert "Services" in names
        assert types.get("Services") == EntityType.MODULE
        assert "UserService" in names
        assert types.get("UserService") == EntityType.CLASS
        assert "UserService.create_user" in names
        assert types.get("UserService.create_user") == EntityType.FUNCTION
        assert "standalone_helper" in names
        assert types.get("standalone_helper") == EntityType.FUNCTION

    def test_ruby_extends_edge(self, tmp_path: Path) -> None:
        """RubyAnalyzer emits EXTENDS edges for class inheritance."""
        from agent_fox.knowledge.lang.ruby_lang import RubyAnalyzer

        rb_file = tmp_path / "service.rb"
        rb_file.write_text(
            """\
class UserService < Base
  def create_user
  end
end
"""
        )
        analyzer = RubyAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(rb_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "service.rb")
        edges = analyzer.extract_edges(tree, "service.rb", entities, {})
        relationships = {e.relationship for e in edges}

        assert EdgeType.EXTENDS in relationships


# ---------------------------------------------------------------------------
# TS-102-14: Module map per language
# ---------------------------------------------------------------------------


class TestModuleMapPerLanguage:
    """TS-102-14: Each analyzer's build_module_map maps import identifiers to paths.

    Requirement: 102-REQ-3.2
    """

    def test_python_module_map(self, tmp_path: Path) -> None:
        """PythonAnalyzer maps 'pkg.module' to 'pkg/module.py'."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        mod_file = pkg / "module.py"
        mod_file.write_text("")

        analyzer = PythonAnalyzer()
        module_map = analyzer.build_module_map(tmp_path, [mod_file])

        assert "pkg.module" in module_map
        assert module_map["pkg.module"] == "pkg/module.py"

    def test_go_module_map(self, tmp_path: Path) -> None:
        """GoAnalyzer maps package name to directory path."""
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        pkg_dir = tmp_path / "pkg" / "server"
        pkg_dir.mkdir(parents=True)
        go_file = pkg_dir / "server.go"
        go_file.write_text("package server\n")

        analyzer = GoAnalyzer()
        module_map = analyzer.build_module_map(tmp_path, [go_file])

        assert "server" in module_map
        assert module_map["server"] == "pkg/server"

    def test_typescript_module_map(self, tmp_path: Path) -> None:
        """TypeScriptAnalyzer maps relative import paths to repo-relative file paths."""
        from agent_fox.knowledge.lang.typescript_lang import TypeScriptAnalyzer

        src = tmp_path / "src" / "components"
        src.mkdir(parents=True)
        btn_file = src / "button.ts"
        btn_file.write_text("export class Button {}\n")

        analyzer = TypeScriptAnalyzer()
        module_map = analyzer.build_module_map(tmp_path, [btn_file])

        # Should map a relative import path pattern to the repo-relative file
        assert any("button" in k for k in module_map), f"No button entry in module_map: {module_map}"

    def test_java_module_map(self, tmp_path: Path) -> None:
        """JavaAnalyzer maps fully qualified class name to repo-relative path."""
        from agent_fox.knowledge.lang.java_lang import JavaAnalyzer

        src = tmp_path / "src" / "com" / "example"
        src.mkdir(parents=True)
        java_file = src / "Foo.java"
        java_file.write_text("package com.example;\npublic class Foo {}\n")

        analyzer = JavaAnalyzer()
        module_map = analyzer.build_module_map(tmp_path, [java_file])

        assert "com.example.Foo" in module_map
        assert "Foo.java" in module_map["com.example.Foo"]

    def test_c_module_map(self, tmp_path: Path) -> None:
        """CAnalyzer maps quoted header paths to repo-relative paths."""
        from agent_fox.knowledge.lang.c_lang import CAnalyzer

        utils = tmp_path / "utils"
        utils.mkdir()
        h_file = utils / "math.h"
        h_file.write_text("")

        analyzer = CAnalyzer()
        module_map = analyzer.build_module_map(tmp_path, [h_file])

        assert "utils/math.h" in module_map

    def test_ruby_module_map(self, tmp_path: Path) -> None:
        """RubyAnalyzer maps require paths to repo-relative file paths."""
        from agent_fox.knowledge.lang.ruby_lang import RubyAnalyzer

        lib = tmp_path / "lib" / "services"
        lib.mkdir(parents=True)
        rb_file = lib / "user.rb"
        rb_file.write_text("")

        analyzer = RubyAnalyzer()
        module_map = analyzer.build_module_map(tmp_path, [rb_file])

        assert "services/user" in module_map


# ---------------------------------------------------------------------------
# TS-102-22: Qualified name construction
# ---------------------------------------------------------------------------


class TestQualifiedNameConstruction:
    """TS-102-22: Nested constructs use Parent.child qualified names.

    Requirement: 102-REQ-2.3
    """

    def test_python_qualified_method_name(self, tmp_path: Path) -> None:
        """Python method is qualified as 'ClassName.method_name'."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

        py_file = tmp_path / "models.py"
        py_file.write_text("class User:\n    def validate(self):\n        pass\n")
        analyzer = PythonAnalyzer()
        tree = _parse_file(py_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "models.py")
        names = {e.entity_name for e in entities}
        assert "User.validate" in names

    def test_go_qualified_method_name(self, tmp_path: Path) -> None:
        """Go method is qualified as 'Type.Method'."""
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        go_file = tmp_path / "server.go"
        go_file.write_text("package main\n\ntype Server struct {}\n\nfunc (s *Server) Start() {}\n")
        analyzer = GoAnalyzer()
        tree = _parse_file(go_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "server.go")
        names = {e.entity_name for e in entities}
        assert "Server.Start" in names

    def test_rust_qualified_impl_method(self, tmp_path: Path) -> None:
        """Rust impl method is qualified as 'Type.method'."""
        from agent_fox.knowledge.lang.rust_lang import RustAnalyzer

        rs_file = tmp_path / "lib.rs"
        rs_file.write_text("pub struct Config {}\n\nimpl Config {\n    pub fn new() -> Self { todo!() }\n}\n")
        analyzer = RustAnalyzer()
        tree = _parse_file(rs_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "lib.rs")
        names = {e.entity_name for e in entities}
        assert "Config.new" in names

    def test_typescript_qualified_method(self, tmp_path: Path) -> None:
        """TypeScript method is qualified as 'Class.method'."""
        from agent_fox.knowledge.lang.typescript_lang import TypeScriptAnalyzer

        ts_file = tmp_path / "comp.ts"
        ts_file.write_text("class Component {\n    update(): void {}\n}\n")
        analyzer = TypeScriptAnalyzer()
        tree = _parse_file(ts_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "comp.ts")
        names = {e.entity_name for e in entities}
        assert "Component.update" in names

    def test_java_qualified_method(self, tmp_path: Path) -> None:
        """Java method is qualified as 'Class.method'."""
        from agent_fox.knowledge.lang.java_lang import JavaAnalyzer

        java_file = tmp_path / "UserService.java"
        java_file.write_text("package com.example;\npublic class UserService {\n    public void createUser() {}\n}\n")
        analyzer = JavaAnalyzer()
        tree = _parse_file(java_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "UserService.java")
        names = {e.entity_name for e in entities}
        assert "UserService.createUser" in names

    def test_cpp_qualified_method(self, tmp_path: Path) -> None:
        """C++ method is qualified as 'Class.method'."""
        from agent_fox.knowledge.lang.c_lang import CppAnalyzer

        cpp_file = tmp_path / "server.cpp"
        cpp_file.write_text("class Server {\npublic:\n    void start();\n};\n")
        analyzer = CppAnalyzer()
        tree = _parse_file(cpp_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "server.cpp")
        names = {e.entity_name for e in entities}
        assert "Server.start" in names

    def test_ruby_qualified_method(self, tmp_path: Path) -> None:
        """Ruby method is qualified as 'Class.method'."""
        from agent_fox.knowledge.lang.ruby_lang import RubyAnalyzer

        rb_file = tmp_path / "service.rb"
        rb_file.write_text("class UserService\n  def create_user\n  end\nend\n")
        analyzer = RubyAnalyzer()
        tree = _parse_file(rb_file, analyzer.make_parser())
        assert tree is not None

        entities = analyzer.extract_entities(tree, "service.rb")
        names = {e.entity_name for e in entities}
        assert "UserService.create_user" in names


# ---------------------------------------------------------------------------
# TS-102-E1: Unparseable file
# ---------------------------------------------------------------------------


class TestUnparseableFile:
    """TS-102-E1: A source file with syntax errors is logged and skipped.

    Requirement: 102-REQ-2.E1
    """

    def test_syntax_error_file_skipped_with_warning(
        self,
        tmp_path: Path,
        entity_conn: duckdb.DuckDBPyConnection,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A syntactically invalid Go file is skipped with a warning; valid files are processed."""
        from agent_fox.knowledge.static_analysis import analyze_codebase

        (tmp_path / "good.go").write_text("package main\n\nfunc main() {}\n")
        (tmp_path / "bad.go").write_text("package\n\nfunc (\n  # broken syntax")

        with caplog.at_level(logging.WARNING, logger="agent_fox"):
            result = analyze_codebase(tmp_path, entity_conn)

        # good.go should produce at least one entity
        assert result.entities_upserted > 0
        # A warning about bad.go should be logged
        assert "bad.go" in caplog.text


# ---------------------------------------------------------------------------
# TS-102-E2: Missing grammar package
# ---------------------------------------------------------------------------


class TestMissingGrammarPackage:
    """TS-102-E2: If a tree-sitter grammar is not installed, the language is skipped.

    Requirement: 102-REQ-2.E2
    """

    def test_missing_grammar_skips_language_with_info_log(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When the Go grammar package is unavailable, GoAnalyzer is skipped gracefully."""
        from agent_fox.knowledge.lang.registry import detect_languages

        (tmp_path / "main.go").write_text("package main\n")
        (tmp_path / "app.py").write_text("def hello(): pass\n")

        # Patch the Go grammar import to simulate a missing package
        with patch("agent_fox.knowledge.lang.go_lang.language", side_effect=ImportError("no grammar")):
            with caplog.at_level(logging.INFO, logger="agent_fox"):
                detected = detect_languages(tmp_path)

        language_names = {a.language_name for a in detected}
        assert "go" not in language_names, "Go must be skipped when grammar is missing"


# ---------------------------------------------------------------------------
# TS-102-E7: Unresolvable import
# ---------------------------------------------------------------------------


class TestUnresolvableImport:
    """TS-102-E7: An import that cannot be resolved creates no IMPORTS edge.

    Requirement: 102-REQ-3.4
    """

    def test_external_go_import_creates_no_edge(self, tmp_path: Path) -> None:
        """An import for an external Go package does not produce an IMPORTS edge."""
        from agent_fox.knowledge.lang.go_lang import GoAnalyzer

        go_file = tmp_path / "main.go"
        go_file.write_text('package main\n\nimport "github.com/pkg/errors"\n\nfunc main() {}\n')
        analyzer = GoAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(go_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "main.go")
        # Empty module_map: external package cannot be resolved
        edges = analyzer.extract_edges(tree, "main.go", entities, {})
        imports_edges = [e for e in edges if e.relationship == EdgeType.IMPORTS]

        assert len(imports_edges) == 0, "External Go package import must not create an IMPORTS edge"

    def test_unresolvable_python_import_creates_no_edge(self, tmp_path: Path) -> None:
        """An import for an unresolvable Python module does not produce an IMPORTS edge."""
        from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

        py_file = tmp_path / "main.py"
        py_file.write_text("import os\nimport sys\n\ndef main(): pass\n")
        analyzer = PythonAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(py_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "main.py")
        # Empty module_map: 'os' and 'sys' cannot be resolved
        edges = analyzer.extract_edges(tree, "main.py", entities, {})
        imports_edges = [e for e in edges if e.relationship == EdgeType.IMPORTS]

        assert len(imports_edges) == 0, "Unresolvable stdlib imports must not create IMPORTS edges"


# ---------------------------------------------------------------------------
# TS-107-1: C# analyzer properties
# ---------------------------------------------------------------------------


class TestCSharpAnalyzerProperties:
    """TS-107-1: CSharpAnalyzer reports correct language_name and file_extensions.

    Requirements: 107-REQ-1.1, 107-REQ-1.2
    """

    def test_csharp_language_name(self) -> None:
        """CSharpAnalyzer.language_name is 'csharp'."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        analyzer = CSharpAnalyzer()
        assert analyzer.language_name == "csharp"

    def test_csharp_file_extensions(self) -> None:
        """CSharpAnalyzer.file_extensions is {'.cs'}."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        analyzer = CSharpAnalyzer()
        assert analyzer.file_extensions == {".cs"}

    def test_csharp_make_parser_returns_parser(self) -> None:
        """CSharpAnalyzer.make_parser() returns a configured tree-sitter Parser."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        analyzer = CSharpAnalyzer()
        parser = analyzer.make_parser()
        assert parser is not None


# ---------------------------------------------------------------------------
# TS-107-2 and TS-107-3: C# entity and edge extraction
# ---------------------------------------------------------------------------


class TestCSharpEntitiesAndEdges:
    """TS-107-2 and TS-107-3: CSharpAnalyzer extracts entities and edges.

    Requirements: 107-REQ-1.3, 107-REQ-1.4
    """

    _CS_SOURCE = """\
using System.Collections.Generic;
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
"""

    def test_csharp_extract_file_entity(self, tmp_path: Path) -> None:
        """CSharpAnalyzer extracts a FILE entity."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_file = tmp_path / "Services.cs"
        cs_file.write_text(self._CS_SOURCE)
        analyzer = CSharpAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Services.cs")
        names = {e.entity_name for e in entities}
        types = {e.entity_name: e.entity_type for e in entities}

        assert "Services.cs" in names
        assert types.get("Services.cs") == EntityType.FILE

    def test_csharp_extract_module_entity(self, tmp_path: Path) -> None:
        """CSharpAnalyzer extracts a MODULE entity for namespace."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_file = tmp_path / "Services.cs"
        cs_file.write_text(self._CS_SOURCE)
        analyzer = CSharpAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Services.cs")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "MyApp.Services" in types
        assert types["MyApp.Services"] == EntityType.MODULE

    def test_csharp_extract_class_entities(self, tmp_path: Path) -> None:
        """CSharpAnalyzer extracts CLASS entities for class, interface, struct, enum."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_file = tmp_path / "Services.cs"
        cs_file.write_text(self._CS_SOURCE)
        analyzer = CSharpAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Services.cs")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "UserService" in types
        assert types["UserService"] == EntityType.CLASS
        assert "IService" in types
        assert types["IService"] == EntityType.CLASS
        assert "Point" in types
        assert types["Point"] == EntityType.CLASS
        assert "Status" in types
        assert types["Status"] == EntityType.CLASS

    def test_csharp_extract_function_entity(self, tmp_path: Path) -> None:
        """CSharpAnalyzer extracts FUNCTION entities with qualified names."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_file = tmp_path / "Services.cs"
        cs_file.write_text(self._CS_SOURCE)
        analyzer = CSharpAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Services.cs")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "UserService.CreateUser" in types
        assert types["UserService.CreateUser"] == EntityType.FUNCTION

    def test_csharp_extract_contains_edges(self, tmp_path: Path) -> None:
        """CSharpAnalyzer extracts CONTAINS edges (namespace->class, class->method)."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_file = tmp_path / "Services.cs"
        cs_file.write_text(self._CS_SOURCE)
        analyzer = CSharpAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Services.cs")
        edges = analyzer.extract_edges(tree, "Services.cs", entities, {})
        contains = [e for e in edges if e.relationship == EdgeType.CONTAINS]

        assert len(contains) >= 2  # namespace->class, class->method

    def test_csharp_extract_extends_edges(self, tmp_path: Path) -> None:
        """CSharpAnalyzer extracts EXTENDS edges from inheritance clause."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_file = tmp_path / "Services.cs"
        cs_file.write_text(self._CS_SOURCE)
        analyzer = CSharpAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Services.cs")
        edges = analyzer.extract_edges(tree, "Services.cs", entities, {})
        extends = [e for e in edges if e.relationship == EdgeType.EXTENDS]

        assert len(extends) >= 1  # UserService -> IService

    def test_csharp_entity_path_is_rel_path(self, tmp_path: Path) -> None:
        """All entities from CSharpAnalyzer have entity_path equal to rel_path."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_file = tmp_path / "Services.cs"
        cs_file.write_text(self._CS_SOURCE)
        analyzer = CSharpAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Services.cs")
        for e in entities:
            if e.entity_type != EntityType.MODULE:
                assert e.entity_path == "Services.cs"


# ---------------------------------------------------------------------------
# TS-107-4: C# module map
# ---------------------------------------------------------------------------


class TestCSharpModuleMap:
    """TS-107-4: CSharpAnalyzer.build_module_map maps namespace.class -> file path.

    Requirements: 107-REQ-1.5
    """

    def test_csharp_module_map_contains_fqn(self, tmp_path: Path) -> None:
        """Module map contains 'MyApp.Services.UserService' -> path."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_dir = tmp_path / "src" / "Services"
        cs_dir.mkdir(parents=True)
        cs_file = cs_dir / "UserService.cs"
        cs_file.write_text("namespace MyApp.Services\n{\n    public class UserService { }\n}\n")

        analyzer = CSharpAnalyzer()
        mm = analyzer.build_module_map(tmp_path, [cs_file])

        assert "MyApp.Services.UserService" in mm

    def test_csharp_module_map_posix_paths(self, tmp_path: Path) -> None:
        """Module map values are POSIX-style paths (no backslashes, no leading slash)."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_dir = tmp_path / "src" / "Services"
        cs_dir.mkdir(parents=True)
        cs_file = cs_dir / "UserService.cs"
        cs_file.write_text("namespace MyApp.Services\n{\n    public class UserService { }\n}\n")

        analyzer = CSharpAnalyzer()
        mm = analyzer.build_module_map(tmp_path, [cs_file])

        for val in mm.values():
            assert "\\" not in val, f"Path {val!r} contains backslash"
            assert not val.startswith("/"), f"Path {val!r} has leading slash"
            assert len(val) > 0, "Path must be non-empty"


# ---------------------------------------------------------------------------
# TS-107-E1: C# external using skipped
# ---------------------------------------------------------------------------


class TestCSharpExternalUsingSkipped:
    """TS-107-E1: Using directive for external namespace is silently skipped.

    Requirements: 107-REQ-1.E1
    """

    def test_csharp_external_using_no_imports_edge(self, tmp_path: Path) -> None:
        """No IMPORTS edge is produced for 'using System;' with empty module map."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_file = tmp_path / "test.cs"
        cs_file.write_text("using System;\nnamespace Ns\n{\n    public class Foo { }\n}\n")
        analyzer = CSharpAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "test.cs")
        edges = analyzer.extract_edges(tree, "test.cs", entities, {})
        imports = [e for e in edges if e.relationship == EdgeType.IMPORTS]

        assert len(imports) == 0, "External using directive must not produce IMPORTS edge"


# ---------------------------------------------------------------------------
# TS-107-E2: C# multiple namespaces
# ---------------------------------------------------------------------------


class TestCSharpMultipleNamespaces:
    """TS-107-E2: Multiple namespaces in one file produce separate MODULE entities.

    Requirements: 107-REQ-1.E2
    """

    def test_csharp_multiple_namespaces_separate_modules(self, tmp_path: Path) -> None:
        """Two namespace declarations produce two MODULE entities."""
        from agent_fox.knowledge.lang.csharp_lang import CSharpAnalyzer

        cs_file = tmp_path / "multi.cs"
        cs_file.write_text("namespace Ns1\n{\n    class A { }\n}\nnamespace Ns2\n{\n    class B { }\n}\n")
        analyzer = CSharpAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(cs_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "multi.cs")
        modules = [e for e in entities if e.entity_type == EntityType.MODULE]

        assert len(modules) == 2
        module_names = {m.entity_name for m in modules}
        assert "Ns1" in module_names
        assert "Ns2" in module_names


# ---------------------------------------------------------------------------
# TS-107-5: Elixir analyzer properties
# ---------------------------------------------------------------------------


class TestElixirAnalyzerProperties:
    """TS-107-5: ElixirAnalyzer reports correct language_name and file_extensions.

    Requirements: 107-REQ-2.1, 107-REQ-2.2
    """

    def test_elixir_language_name(self) -> None:
        """ElixirAnalyzer.language_name is 'elixir'."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        analyzer = ElixirAnalyzer()
        assert analyzer.language_name == "elixir"

    def test_elixir_file_extensions(self) -> None:
        """ElixirAnalyzer.file_extensions is {'.ex', '.exs'}."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        analyzer = ElixirAnalyzer()
        assert analyzer.file_extensions == {".ex", ".exs"}

    def test_elixir_make_parser_returns_parser(self) -> None:
        """ElixirAnalyzer.make_parser() returns a configured tree-sitter Parser."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        analyzer = ElixirAnalyzer()
        parser = analyzer.make_parser()
        assert parser is not None


# ---------------------------------------------------------------------------
# TS-107-6 and TS-107-7: Elixir entity and edge extraction
# ---------------------------------------------------------------------------


class TestElixirEntitiesAndEdges:
    """TS-107-6 and TS-107-7: ElixirAnalyzer extracts entities and edges.

    Requirements: 107-REQ-2.3, 107-REQ-2.4, 107-REQ-2.5
    """

    _EX_SOURCE_BASIC = """\
defmodule MyApp.Accounts.User do
  def changeset(user, attrs) do
    user
  end

  defp validate_email(changeset) do
    changeset
  end
end
"""

    _EX_SOURCE_IMPORTS = """\
defmodule MyApp.Accounts.User do
  use Ecto.Schema
  import Ecto.Changeset
  alias MyApp.Repo

  def changeset(user, attrs), do: user
end
"""

    def test_elixir_extract_file_entity(self, tmp_path: Path) -> None:
        """ElixirAnalyzer extracts a FILE entity."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        ex_file = tmp_path / "user.ex"
        ex_file.write_text(self._EX_SOURCE_BASIC)
        analyzer = ElixirAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(ex_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "user.ex")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "user.ex" in types
        assert types["user.ex"] == EntityType.FILE

    def test_elixir_extract_module_entity(self, tmp_path: Path) -> None:
        """ElixirAnalyzer extracts a MODULE entity for defmodule."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        ex_file = tmp_path / "user.ex"
        ex_file.write_text(self._EX_SOURCE_BASIC)
        analyzer = ElixirAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(ex_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "user.ex")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "MyApp.Accounts.User" in types
        assert types["MyApp.Accounts.User"] == EntityType.MODULE

    def test_elixir_extract_function_entities(self, tmp_path: Path) -> None:
        """ElixirAnalyzer extracts FUNCTION entities for def and defp."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        ex_file = tmp_path / "user.ex"
        ex_file.write_text(self._EX_SOURCE_BASIC)
        analyzer = ElixirAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(ex_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "user.ex")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "MyApp.Accounts.User.changeset" in types
        assert types["MyApp.Accounts.User.changeset"] == EntityType.FUNCTION
        assert "MyApp.Accounts.User.validate_email" in types
        assert types["MyApp.Accounts.User.validate_email"] == EntityType.FUNCTION

    def test_elixir_no_class_entities(self, tmp_path: Path) -> None:
        """ElixirAnalyzer never produces CLASS entities."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        ex_file = tmp_path / "user.ex"
        ex_file.write_text(self._EX_SOURCE_BASIC)
        analyzer = ElixirAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(ex_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "user.ex")
        assert not any(e.entity_type == EntityType.CLASS for e in entities), "Elixir must not produce CLASS entities"

    def test_elixir_extract_contains_edges(self, tmp_path: Path) -> None:
        """ElixirAnalyzer extracts CONTAINS edges (file->module, module->function)."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        ex_file = tmp_path / "user.ex"
        ex_file.write_text(self._EX_SOURCE_IMPORTS)
        analyzer = ElixirAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(ex_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "user.ex")
        edges = analyzer.extract_edges(tree, "user.ex", entities, {})
        contains = [e for e in edges if e.relationship == EdgeType.CONTAINS]

        assert len(contains) >= 2  # file->module and module->function

    def test_elixir_no_extends_edges(self, tmp_path: Path) -> None:
        """ElixirAnalyzer never produces EXTENDS edges."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        ex_file = tmp_path / "user.ex"
        ex_file.write_text(self._EX_SOURCE_IMPORTS)
        analyzer = ElixirAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(ex_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "user.ex")
        edges = analyzer.extract_edges(tree, "user.ex", entities, {})
        extends = [e for e in edges if e.relationship == EdgeType.EXTENDS]

        assert len(extends) == 0, "Elixir must not produce EXTENDS edges"

    def test_elixir_imports_edges_with_module_map(self, tmp_path: Path) -> None:
        """ElixirAnalyzer extracts IMPORTS edges for resolved use/import/alias."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        ex_file = tmp_path / "user.ex"
        ex_file.write_text(self._EX_SOURCE_IMPORTS)
        analyzer = ElixirAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(ex_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "user.ex")
        # Populate module_map so imports can be resolved
        module_map = {
            "Ecto.Schema": "deps/ecto/lib/ecto/schema.ex",
            "Ecto.Changeset": "deps/ecto/lib/ecto/changeset.ex",
            "MyApp.Repo": "lib/my_app/repo.ex",
        }
        edges = analyzer.extract_edges(tree, "user.ex", entities, module_map)
        imports = [e for e in edges if e.relationship == EdgeType.IMPORTS]

        assert len(imports) >= 1


# ---------------------------------------------------------------------------
# TS-107-8: Elixir module map
# ---------------------------------------------------------------------------


class TestElixirModuleMap:
    """TS-107-8: ElixirAnalyzer maps dotted module names to file paths.

    Requirements: 107-REQ-2.6
    """

    def test_elixir_module_map_maps_module_to_path(self, tmp_path: Path) -> None:
        """Module map contains 'MyApp.Accounts.User' -> 'lib/my_app/accounts/user.ex'."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        lib_dir = tmp_path / "lib" / "my_app" / "accounts"
        lib_dir.mkdir(parents=True)
        ex_file = lib_dir / "user.ex"
        ex_file.write_text("defmodule MyApp.Accounts.User do\n  def changeset(u, a), do: u\nend\n")

        analyzer = ElixirAnalyzer()
        mm = analyzer.build_module_map(tmp_path, [ex_file])

        assert "MyApp.Accounts.User" in mm
        assert mm["MyApp.Accounts.User"] == "lib/my_app/accounts/user.ex"

    def test_elixir_module_map_posix_paths(self, tmp_path: Path) -> None:
        """Module map values are POSIX-style paths."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        lib_dir = tmp_path / "lib"
        lib_dir.mkdir(parents=True)
        ex_file = lib_dir / "app.ex"
        ex_file.write_text("defmodule MyApp do\ndef run, do: :ok\nend\n")

        analyzer = ElixirAnalyzer()
        mm = analyzer.build_module_map(tmp_path, [ex_file])

        for val in mm.values():
            assert "\\" not in val
            assert not val.startswith("/")
            assert len(val) > 0


# ---------------------------------------------------------------------------
# TS-107-E3: Elixir nested defmodule
# ---------------------------------------------------------------------------


class TestElixirNestedDefmodule:
    """TS-107-E3: Nested defmodule creates fully-qualified MODULE entities.

    Requirements: 107-REQ-2.E1
    """

    def test_elixir_nested_defmodule_fully_qualified(self, tmp_path: Path) -> None:
        """Nested defmodule creates 'MyApp' and 'MyApp.Inner' MODULE entities."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        ex_file = tmp_path / "app.ex"
        ex_file.write_text(
            """\
defmodule MyApp do
  defmodule Inner do
    def hello, do: :world
  end
end
"""
        )
        analyzer = ElixirAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(ex_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "app.ex")
        module_names = {e.entity_name for e in entities if e.entity_type == EntityType.MODULE}

        assert "MyApp" in module_names
        assert "MyApp.Inner" in module_names


# ---------------------------------------------------------------------------
# TS-107-E4: Elixir external import skipped
# ---------------------------------------------------------------------------


class TestElixirExternalImportSkipped:
    """TS-107-E4: External use/import/alias/require is silently skipped.

    Requirements: 107-REQ-2.E2
    """

    def test_elixir_external_use_no_imports_edge(self, tmp_path: Path) -> None:
        """No IMPORTS edge for 'use Ecto.Schema' with empty module map."""
        from agent_fox.knowledge.lang.elixir_lang import ElixirAnalyzer

        ex_file = tmp_path / "test.ex"
        ex_file.write_text("defmodule MyMod do\n  use Ecto.Schema\n  def hello, do: :ok\nend\n")
        analyzer = ElixirAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(ex_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "test.ex")
        edges = analyzer.extract_edges(tree, "test.ex", entities, {})
        imports = [e for e in edges if e.relationship == EdgeType.IMPORTS]

        assert len(imports) == 0, "External use directive must not produce IMPORTS edge"


# ---------------------------------------------------------------------------
# TS-107-9: Kotlin analyzer properties
# ---------------------------------------------------------------------------


class TestKotlinAnalyzerProperties:
    """TS-107-9: KotlinAnalyzer reports correct language_name and file_extensions.

    Requirements: 107-REQ-3.1, 107-REQ-3.2
    """

    def test_kotlin_language_name(self) -> None:
        """KotlinAnalyzer.language_name is 'kotlin'."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        analyzer = KotlinAnalyzer()
        assert analyzer.language_name == "kotlin"

    def test_kotlin_file_extensions(self) -> None:
        """KotlinAnalyzer.file_extensions is {'.kt', '.kts'}."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        analyzer = KotlinAnalyzer()
        assert analyzer.file_extensions == {".kt", ".kts"}

    def test_kotlin_make_parser_returns_parser(self) -> None:
        """KotlinAnalyzer.make_parser() returns a configured tree-sitter Parser."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        analyzer = KotlinAnalyzer()
        parser = analyzer.make_parser()
        assert parser is not None


# ---------------------------------------------------------------------------
# TS-107-10 and TS-107-11: Kotlin entity and edge extraction
# ---------------------------------------------------------------------------


class TestKotlinEntitiesAndEdges:
    """TS-107-10 and TS-107-11: KotlinAnalyzer extracts entities and edges.

    Requirements: 107-REQ-3.3, 107-REQ-3.4
    """

    _KT_SOURCE_BASIC = """\
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
"""

    _KT_SOURCE_EXTENDS = """\
package com.example

import com.example.models.BaseModel

class User : BaseModel() {
    fun validate() {}
}
"""

    def test_kotlin_extract_file_entity(self, tmp_path: Path) -> None:
        """KotlinAnalyzer extracts a FILE entity."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        kt_file = tmp_path / "Models.kt"
        kt_file.write_text(self._KT_SOURCE_BASIC)
        analyzer = KotlinAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(kt_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Models.kt")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "Models.kt" in types
        assert types["Models.kt"] == EntityType.FILE

    def test_kotlin_extract_module_entity(self, tmp_path: Path) -> None:
        """KotlinAnalyzer extracts a MODULE entity for package."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        kt_file = tmp_path / "Models.kt"
        kt_file.write_text(self._KT_SOURCE_BASIC)
        analyzer = KotlinAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(kt_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Models.kt")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "com.example.models" in types
        assert types["com.example.models"] == EntityType.MODULE

    def test_kotlin_extract_class_entities(self, tmp_path: Path) -> None:
        """KotlinAnalyzer extracts CLASS entities for class, interface, object, data class."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        kt_file = tmp_path / "Models.kt"
        kt_file.write_text(self._KT_SOURCE_BASIC)
        analyzer = KotlinAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(kt_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Models.kt")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "User" in types
        assert types["User"] == EntityType.CLASS
        assert "Serializable" in types
        assert types["Serializable"] == EntityType.CLASS
        assert "AppConfig" in types
        assert types["AppConfig"] == EntityType.CLASS
        assert "UserDTO" in types
        assert types["UserDTO"] == EntityType.CLASS

    def test_kotlin_extract_function_entities(self, tmp_path: Path) -> None:
        """KotlinAnalyzer extracts FUNCTION entities (methods and top-level)."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        kt_file = tmp_path / "Models.kt"
        kt_file.write_text(self._KT_SOURCE_BASIC)
        analyzer = KotlinAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(kt_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "Models.kt")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "User.validate" in types
        assert types["User.validate"] == EntityType.FUNCTION
        assert "topLevelFunction" in types
        assert types["topLevelFunction"] == EntityType.FUNCTION

    def test_kotlin_extract_contains_edges(self, tmp_path: Path) -> None:
        """KotlinAnalyzer extracts CONTAINS edges (file->class, class->method)."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        kt_file = tmp_path / "User.kt"
        kt_file.write_text(self._KT_SOURCE_EXTENDS)
        analyzer = KotlinAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(kt_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "User.kt")
        edges = analyzer.extract_edges(tree, "User.kt", entities, {})
        contains = [e for e in edges if e.relationship == EdgeType.CONTAINS]

        assert len(contains) >= 2  # file->class and class->method

    def test_kotlin_extract_extends_edges(self, tmp_path: Path) -> None:
        """KotlinAnalyzer extracts EXTENDS edges from ':' clause."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        kt_file = tmp_path / "User.kt"
        kt_file.write_text(self._KT_SOURCE_EXTENDS)
        analyzer = KotlinAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(kt_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "User.kt")
        edges = analyzer.extract_edges(tree, "User.kt", entities, {})
        extends = [e for e in edges if e.relationship == EdgeType.EXTENDS]

        assert len(extends) >= 1  # User -> BaseModel


# ---------------------------------------------------------------------------
# TS-107-12: Kotlin module map
# ---------------------------------------------------------------------------


class TestKotlinModuleMap:
    """TS-107-12: KotlinAnalyzer maps package-qualified class names to file paths.

    Requirements: 107-REQ-3.5
    """

    def test_kotlin_module_map_contains_fqn(self, tmp_path: Path) -> None:
        """Module map contains 'com.example.models.User' -> path."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        src_dir = tmp_path / "src" / "com" / "example" / "models"
        src_dir.mkdir(parents=True)
        kt_file = src_dir / "User.kt"
        kt_file.write_text("package com.example.models\n\nclass User(val name: String) { fun validate() = true }\n")

        analyzer = KotlinAnalyzer()
        mm = analyzer.build_module_map(tmp_path, [kt_file])

        assert "com.example.models.User" in mm

    def test_kotlin_module_map_posix_paths(self, tmp_path: Path) -> None:
        """Module map values are POSIX-style paths."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        kt_file = src_dir / "App.kt"
        kt_file.write_text("package com.example\n\nclass App { fun run() {} }\n")

        analyzer = KotlinAnalyzer()
        mm = analyzer.build_module_map(tmp_path, [kt_file])

        for val in mm.values():
            assert "\\" not in val
            assert not val.startswith("/")
            assert len(val) > 0


# ---------------------------------------------------------------------------
# TS-107-E5: Kotlin companion object methods
# ---------------------------------------------------------------------------


class TestKotlinCompanionObjectMethods:
    """TS-107-E5: Companion object methods are qualified as ClassName.methodName.

    Requirements: 107-REQ-3.E1
    """

    def test_kotlin_companion_method_qualified_as_class_method(self, tmp_path: Path) -> None:
        """Companion object 'create' is qualified as 'User.create', not 'User.Companion.create'."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        kt_file = tmp_path / "User.kt"
        kt_file.write_text(
            """\
class User {
    companion object {
        fun create(name: String): User = User()
    }
}
"""
        )
        analyzer = KotlinAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(kt_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "User.kt")
        func_names = {e.entity_name for e in entities if e.entity_type == EntityType.FUNCTION}

        assert "User.create" in func_names
        assert "User.Companion.create" not in func_names


# ---------------------------------------------------------------------------
# TS-107-E6: Kotlin external import skipped
# ---------------------------------------------------------------------------


class TestKotlinExternalImportSkipped:
    """TS-107-E6: External import silently skipped.

    Requirements: 107-REQ-3.E2
    """

    def test_kotlin_external_import_no_imports_edge(self, tmp_path: Path) -> None:
        """No IMPORTS edge for 'import java.util.List' with empty module map."""
        from agent_fox.knowledge.lang.kotlin_lang import KotlinAnalyzer

        kt_file = tmp_path / "test.kt"
        kt_file.write_text("import java.util.List\n\nclass Foo { fun bar() {} }\n")
        analyzer = KotlinAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(kt_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "test.kt")
        edges = analyzer.extract_edges(tree, "test.kt", entities, {})
        imports = [e for e in edges if e.relationship == EdgeType.IMPORTS]

        assert len(imports) == 0, "External import must not produce IMPORTS edge"


# ---------------------------------------------------------------------------
# TS-107-13: Dart analyzer properties
# ---------------------------------------------------------------------------


class TestDartAnalyzerProperties:
    """TS-107-13: DartAnalyzer reports correct language_name and file_extensions.

    Requirements: 107-REQ-4.1, 107-REQ-4.2
    """

    def test_dart_language_name(self) -> None:
        """DartAnalyzer.language_name is 'dart'."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        analyzer = DartAnalyzer()
        assert analyzer.language_name == "dart"

    def test_dart_file_extensions(self) -> None:
        """DartAnalyzer.file_extensions is {'.dart'}."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        analyzer = DartAnalyzer()
        assert analyzer.file_extensions == {".dart"}

    def test_dart_make_parser_returns_parser(self) -> None:
        """DartAnalyzer.make_parser() returns a configured tree-sitter Parser."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        assert parser is not None


# ---------------------------------------------------------------------------
# TS-107-14 and TS-107-16: Dart entity and edge extraction
# ---------------------------------------------------------------------------


class TestDartEntitiesAndEdges:
    """TS-107-14 and TS-107-16: DartAnalyzer extracts entities and edges.

    Requirements: 107-REQ-4.3, 107-REQ-4.4
    """

    _DART_SOURCE_BASIC = """\
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
"""

    _DART_SOURCE_EDGES = """\
import 'models/base.dart';

class User extends BaseModel with Printable implements Serializable {
  void save() {}
}
"""

    def test_dart_extract_file_entity(self, tmp_path: Path) -> None:
        """DartAnalyzer extracts a FILE entity."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        dart_file = tmp_path / "models.dart"
        dart_file.write_text(self._DART_SOURCE_BASIC)
        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(dart_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "models.dart")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "models.dart" in types
        assert types["models.dart"] == EntityType.FILE

    def test_dart_no_module_entity_without_library(self, tmp_path: Path) -> None:
        """DartAnalyzer does not create MODULE entity when no library directive."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        dart_file = tmp_path / "models.dart"
        dart_file.write_text(self._DART_SOURCE_BASIC)
        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(dart_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "models.dart")
        assert not any(e.entity_type == EntityType.MODULE for e in entities), (
            "No MODULE entity when library directive is absent"
        )

    def test_dart_extract_class_entities(self, tmp_path: Path) -> None:
        """DartAnalyzer extracts CLASS entities for class, mixin, enum, extension."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        dart_file = tmp_path / "models.dart"
        dart_file.write_text(self._DART_SOURCE_BASIC)
        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(dart_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "models.dart")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "User" in types
        assert types["User"] == EntityType.CLASS
        assert "Printable" in types
        assert types["Printable"] == EntityType.CLASS

    def test_dart_extract_function_entities(self, tmp_path: Path) -> None:
        """DartAnalyzer extracts FUNCTION entities for methods and top-level functions."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        dart_file = tmp_path / "models.dart"
        dart_file.write_text(self._DART_SOURCE_BASIC)
        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(dart_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "models.dart")
        types = {e.entity_name: e.entity_type for e in entities}

        assert "User.save" in types
        assert types["User.save"] == EntityType.FUNCTION
        assert "Printable.printInfo" in types
        assert types["Printable.printInfo"] == EntityType.FUNCTION
        assert "topLevelFunction" in types
        assert types["topLevelFunction"] == EntityType.FUNCTION

    def test_dart_extract_contains_edges(self, tmp_path: Path) -> None:
        """DartAnalyzer extracts CONTAINS edges (file->class, class->method)."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        dart_file = tmp_path / "user.dart"
        dart_file.write_text(self._DART_SOURCE_EDGES)
        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(dart_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "user.dart")
        edges = analyzer.extract_edges(tree, "user.dart", entities, {})
        contains = [e for e in edges if e.relationship == EdgeType.CONTAINS]

        assert len(contains) >= 2  # file->class and class->method

    def test_dart_extract_imports_edges(self, tmp_path: Path) -> None:
        """DartAnalyzer extracts IMPORTS edges for import statements."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        dart_file = tmp_path / "user.dart"
        dart_file.write_text(self._DART_SOURCE_EDGES)
        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(dart_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "user.dart")
        module_map = {"models/base.dart": "lib/models/base.dart"}
        edges = analyzer.extract_edges(tree, "user.dart", entities, module_map)
        imports = [e for e in edges if e.relationship == EdgeType.IMPORTS]

        assert len(imports) >= 1

    def test_dart_extract_extends_edges(self, tmp_path: Path) -> None:
        """DartAnalyzer extracts EXTENDS edges from extends/implements/with clauses."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        dart_file = tmp_path / "user.dart"
        dart_file.write_text(self._DART_SOURCE_EDGES)
        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(dart_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "user.dart")
        edges = analyzer.extract_edges(tree, "user.dart", entities, {})
        extends = [e for e in edges if e.relationship == EdgeType.EXTENDS]

        assert len(extends) >= 1  # BaseModel, Printable, or Serializable


# ---------------------------------------------------------------------------
# TS-107-15: Dart library directive creates MODULE entity
# ---------------------------------------------------------------------------


class TestDartLibraryDirective:
    """TS-107-15: DartAnalyzer creates MODULE entity when library directive is present.

    Requirements: 107-REQ-4.3, 107-REQ-4.E2
    """

    def test_dart_library_directive_creates_module_entity(self, tmp_path: Path) -> None:
        """MODULE entity is created when 'library my_library;' is present."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        dart_file = tmp_path / "widget.dart"
        dart_file.write_text("library my_library;\n\nclass Widget {}\n")
        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(dart_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "widget.dart")
        modules = [e for e in entities if e.entity_type == EntityType.MODULE]

        assert len(modules) == 1
        assert modules[0].entity_name == "my_library"


# ---------------------------------------------------------------------------
# TS-107-17: Dart module map
# ---------------------------------------------------------------------------


class TestDartModuleMap:
    """TS-107-17: DartAnalyzer maps import paths to file paths.

    Requirements: 107-REQ-4.5
    """

    def test_dart_module_map_maps_file_paths(self, tmp_path: Path) -> None:
        """Module map maps relative-style import paths to repo-relative file paths."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        lib_dir = tmp_path / "lib" / "models"
        lib_dir.mkdir(parents=True)
        dart_file = lib_dir / "user.dart"
        dart_file.write_text("class User {}\n")

        analyzer = DartAnalyzer()
        mm = analyzer.build_module_map(tmp_path, [dart_file])

        # The module map should map some key to the file's repo-relative path
        assert any("user.dart" in v for v in mm.values()), (
            f"Module map values must include a path containing 'user.dart', got: {mm}"
        )
        # Keys must not start with 'dart:' (SDK prefix)
        assert not any(k.startswith("dart:") for k in mm), "Module map must not include dart: SDK prefixed keys"

    def test_dart_module_map_posix_paths(self, tmp_path: Path) -> None:
        """Module map values are POSIX-style paths."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        dart_file = lib_dir / "app.dart"
        dart_file.write_text("class App {}\n")

        analyzer = DartAnalyzer()
        mm = analyzer.build_module_map(tmp_path, [dart_file])

        for val in mm.values():
            assert "\\" not in val
            assert not val.startswith("/")
            assert len(val) > 0


# ---------------------------------------------------------------------------
# TS-107-E7: Dart SDK import skipped
# ---------------------------------------------------------------------------


class TestDartSdkImportSkipped:
    """TS-107-E7: Dart SDK and external package imports are silently skipped.

    Requirements: 107-REQ-4.E1
    """

    def test_dart_sdk_import_no_imports_edge(self, tmp_path: Path) -> None:
        """No IMPORTS edge for 'dart:async' with empty module map."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        dart_file = tmp_path / "test.dart"
        dart_file.write_text("import 'dart:async';\nimport 'package:flutter/material.dart';\n\nclass Foo {}\n")
        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(dart_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "test.dart")
        edges = analyzer.extract_edges(tree, "test.dart", entities, {})
        imports = [e for e in edges if e.relationship == EdgeType.IMPORTS]

        assert len(imports) == 0, "SDK and package: imports must not produce IMPORTS edges"


# ---------------------------------------------------------------------------
# TS-107-E8: Dart no library directive
# ---------------------------------------------------------------------------


class TestDartNoLibraryDirective:
    """TS-107-E8: No MODULE entity when library directive is absent.

    Requirements: 107-REQ-4.E2
    """

    def test_dart_no_library_no_module_entity(self, tmp_path: Path) -> None:
        """No MODULE entity is created for a file without a library directive."""
        from agent_fox.knowledge.lang.dart_lang import DartAnalyzer

        dart_file = tmp_path / "widget.dart"
        dart_file.write_text("class Widget {}\n")
        analyzer = DartAnalyzer()
        parser = analyzer.make_parser()
        tree = _parse_file(dart_file, parser)
        assert tree is not None

        entities = analyzer.extract_entities(tree, "widget.dart")
        assert not any(e.entity_type == EntityType.MODULE for e in entities), (
            "No MODULE entity when library directive is absent"
        )


# ---------------------------------------------------------------------------
# TS-107-18: Registry integration
# ---------------------------------------------------------------------------


class TestRegistryIntegration107:
    """TS-107-18: All four analyzers registered without extension conflicts.

    Requirements: 107-REQ-5.1, 107-REQ-5.2, 107-REQ-6.1
    """

    def test_new_analyzers_in_registry(self) -> None:
        """Default registry contains analyzers for csharp, elixir, kotlin, dart."""
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()
        lang_names = {a.language_name for a in registry.all_analyzers()}

        assert "csharp" in lang_names, "csharp analyzer must be in registry"
        assert "elixir" in lang_names, "elixir analyzer must be in registry"
        assert "kotlin" in lang_names, "kotlin analyzer must be in registry"
        assert "dart" in lang_names, "dart analyzer must be in registry"

    def test_new_extensions_resolvable(self) -> None:
        """Registry resolves .cs, .ex, .kt, .dart extensions."""
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()

        assert registry.get_analyzer(".cs") is not None
        assert registry.get_analyzer(".ex") is not None
        assert registry.get_analyzer(".kt") is not None
        assert registry.get_analyzer(".dart") is not None

    def test_no_extension_conflicts(self) -> None:
        """No two registered analyzers share a file extension."""
        from agent_fox.knowledge.lang.registry import get_default_registry

        registry = get_default_registry()
        all_exts: list[str] = []
        for analyzer in registry.all_analyzers():
            for ext in analyzer.file_extensions:
                assert ext not in all_exts, f"Extension {ext!r} is registered by multiple analyzers"
                all_exts.append(ext)


# ---------------------------------------------------------------------------
# TS-107-19: Detect languages
# ---------------------------------------------------------------------------


class TestDetectLanguages107:
    """TS-107-19: detect_languages discovers new languages when matching files exist.

    Requirements: 107-REQ-5.4
    """

    def test_detect_new_languages(self, tmp_path: Path) -> None:
        """detect_languages returns analyzers for all four new languages."""
        from agent_fox.knowledge.lang.registry import detect_languages

        # Create one file per new language
        (tmp_path / "Main.cs").write_text("namespace App { class Main { } }")
        (tmp_path / "app.ex").write_text("defmodule App do\n  def run, do: :ok\nend")
        (tmp_path / "App.kt").write_text("package app\nclass App { fun run() {} }")
        (tmp_path / "app.dart").write_text("class App {}")

        analyzers = detect_languages(tmp_path)
        detected = {a.language_name for a in analyzers}

        assert "csharp" in detected, "csharp must be detected"
        assert "elixir" in detected, "elixir must be detected"
        assert "kotlin" in detected, "kotlin must be detected"
        assert "dart" in detected, "dart must be detected"


# ---------------------------------------------------------------------------
# TS-107-E9: Grammar not installed
# ---------------------------------------------------------------------------


class TestGrammarNotInstalled107:
    """TS-107-E9: Missing grammar package causes graceful skip, not crash.

    Requirements: 107-REQ-5.3, 107-REQ-5.E1
    """

    def test_missing_csharp_grammar_skips_gracefully(self, tmp_path: Path) -> None:
        """When C# grammar is mocked to fail, registry skips it but keeps others."""
        from agent_fox.knowledge.lang.registry import _build_default_registry

        (tmp_path / "app.py").write_text("def hello(): pass\n")

        # Patch the language attribute inside csharp_lang to simulate missing grammar.
        with patch("agent_fox.knowledge.lang.csharp_lang.language", side_effect=ImportError("no grammar")):
            registry = _build_default_registry()

        lang_names = {a.language_name for a in registry.all_analyzers()}
        assert "csharp" not in lang_names, "csharp must be skipped when grammar is missing"
        assert "python" in lang_names, "python must remain registered"
