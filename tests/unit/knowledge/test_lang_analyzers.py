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

    def test_python_entities_via_analyze_codebase(
        self, tmp_path: Path, entity_conn: duckdb.DuckDBPyConnection
    ) -> None:
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
        c_file.write_text('#include <stdio.h>\n\nvoid main() {}\n')
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
        java_file.write_text(
            "package com.example;\npublic class UserService {\n    public void createUser() {}\n}\n"
        )
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
