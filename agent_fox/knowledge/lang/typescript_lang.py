"""TypeScript and JavaScript language analyzers for the entity graph.

Implements LanguageAnalyzer for TypeScript and JavaScript source files using
tree-sitter-typescript and tree-sitter-javascript.

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
"""

from __future__ import annotations

import uuid
from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType


class TypeScriptAnalyzer:
    """Language analyzer for TypeScript source files (.ts, .tsx).

    Extracts FILE, CLASS (class + interface), and FUNCTION entities,
    together with CONTAINS, IMPORTS, and EXTENDS edges.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    @property
    def language_name(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> set[str]:
        return {".ts", ".tsx"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for TypeScript."""
        import tree_sitter_typescript as tsts  # type: ignore[import]
        from tree_sitter import Language, Parser

        return Parser(Language(tsts.language_typescript()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, CLASS, and FUNCTION entities from a TypeScript source file."""
        return _extract_ts_entities(tree, rel_path, include_interfaces=True)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS, IMPORTS, and EXTENDS edges from a TypeScript source file."""
        return _extract_ts_edges(tree, rel_path, entities, module_map, include_interfaces=True)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a TypeScript/ES module map mapping path stems to repo-relative file paths."""
        return _build_ts_module_map(repo_root, files)


class JavaScriptAnalyzer:
    """Language analyzer for JavaScript source files (.js, .jsx).

    Extracts FILE, CLASS, and FUNCTION entities (no interfaces),
    together with CONTAINS, IMPORTS, and EXTENDS edges.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    @property
    def language_name(self) -> str:
        return "javascript"

    @property
    def file_extensions(self) -> set[str]:
        return {".js", ".jsx"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for JavaScript."""
        import tree_sitter_javascript as tsj  # type: ignore[import]
        from tree_sitter import Language, Parser

        return Parser(Language(tsj.language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, CLASS, and FUNCTION entities from a JavaScript source file."""
        return _extract_ts_entities(tree, rel_path, include_interfaces=False)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS, IMPORTS, and EXTENDS edges from a JavaScript source file."""
        return _extract_ts_edges(tree, rel_path, entities, module_map, include_interfaces=False)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a JavaScript/ES module map mapping path stems to repo-relative file paths."""
        return _build_ts_module_map(repo_root, files)


# ---------------------------------------------------------------------------
# Tree-sitter helpers
# ---------------------------------------------------------------------------


def _node_text(node) -> str | None:
    """Safely decode text from a tree-sitter node."""
    if node is None:
        return None
    return node.text.decode("utf-8") if node.text else None


def _field_text(node, field_name: str) -> str | None:
    """Get decoded text of the named field child."""
    child = node.child_by_field_name(field_name)
    return _node_text(child)


def _child_by_type(node, *types: str):
    """Return the first child whose type is in *types*, or None."""
    for child in node.children:
        if child.type in types:
            return child
    return None


def _child_text_by_type(node, *types: str) -> str | None:
    """Return text of the first child whose type is in *types*, or None."""
    return _node_text(_child_by_type(node, *types))


# ---------------------------------------------------------------------------
# TypeScript/JavaScript entity extraction
# ---------------------------------------------------------------------------


def _extract_ts_entities(tree, rel_path: str, *, include_interfaces: bool) -> list[Entity]:
    """Extract all entities from a parsed TypeScript/JavaScript source tree."""
    now = "1970-01-01T00:00:00"
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    # FILE entity
    entities.append(
        Entity(
            id=str(uuid.uuid4()),
            entity_type=EntityType.FILE,
            entity_name=file_name,
            entity_path=rel_path,
            created_at=now,
            deleted_at=None,
        )
    )

    root = tree.root_node
    for child in root.children:
        _extract_ts_node_entities(child, rel_path, entities, now, include_interfaces)

    return entities


def _extract_ts_node_entities(
    node,
    rel_path: str,
    entities: list[Entity],
    now: str,
    include_interfaces: bool,
) -> None:
    """Extract entities from a single top-level TypeScript/JavaScript AST node."""
    node_type = node.type

    # Unwrap export_statement to process the inner declaration
    if node_type == "export_statement":
        for child in node.children:
            if child.type in (
                "class_declaration",
                "function_declaration",
                "interface_declaration",
                "abstract_class_declaration",
                "lexical_declaration",
            ):
                _extract_ts_node_entities(child, rel_path, entities, now, include_interfaces)
        return

    # Class declaration → CLASS entity + methods as FUNCTION entities
    if node_type in ("class_declaration", "abstract_class_declaration"):
        class_name = _field_text(node, "name") or _child_text_by_type(node, "type_identifier", "identifier")
        if class_name:
            entities.append(
                Entity(
                    id=str(uuid.uuid4()),
                    entity_type=EntityType.CLASS,
                    entity_name=class_name,
                    entity_path=rel_path,
                    created_at=now,
                    deleted_at=None,
                )
            )
            # Extract methods from class body
            body = node.child_by_field_name("body") or _child_by_type(node, "class_body")
            if body:
                _extract_ts_class_methods(body, class_name, rel_path, entities, now)
        return

    # Interface declaration (TypeScript only) → CLASS entity
    if node_type == "interface_declaration" and include_interfaces:
        iface_name = _field_text(node, "name") or _child_text_by_type(node, "type_identifier", "identifier")
        if iface_name:
            entities.append(
                Entity(
                    id=str(uuid.uuid4()),
                    entity_type=EntityType.CLASS,
                    entity_name=iface_name,
                    entity_path=rel_path,
                    created_at=now,
                    deleted_at=None,
                )
            )
        return

    # Function declaration → FUNCTION entity
    if node_type == "function_declaration":
        func_name = _field_text(node, "name") or _child_text_by_type(node, "identifier")
        if func_name:
            entities.append(
                Entity(
                    id=str(uuid.uuid4()),
                    entity_type=EntityType.FUNCTION,
                    entity_name=func_name,
                    entity_path=rel_path,
                    created_at=now,
                    deleted_at=None,
                )
            )
        return

    # Lexical declaration: const/let with arrow function → FUNCTION entity
    if node_type == "lexical_declaration":
        for child in node.children:
            if child.type == "variable_declarator":
                var_name = _field_text(child, "name") or _child_text_by_type(child, "identifier")
                value = child.child_by_field_name("value")
                if var_name and value and value.type == "arrow_function":
                    entities.append(
                        Entity(
                            id=str(uuid.uuid4()),
                            entity_type=EntityType.FUNCTION,
                            entity_name=var_name,
                            entity_path=rel_path,
                            created_at=now,
                            deleted_at=None,
                        )
                    )
        return


def _extract_ts_class_methods(
    class_body,
    class_name: str,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Extract method FUNCTION entities from a TypeScript/JavaScript class body."""
    for child in class_body.children:
        if child.type == "method_definition":
            method_name = _field_text(child, "name") or _child_text_by_type(child, "property_identifier", "identifier")
            if method_name and not method_name.startswith("#"):
                # Skip constructor as it's not a regular method in most contexts
                qualified = f"{class_name}.{method_name}"
                entities.append(
                    Entity(
                        id=str(uuid.uuid4()),
                        entity_type=EntityType.FUNCTION,
                        entity_name=qualified,
                        entity_path=rel_path,
                        created_at=now,
                        deleted_at=None,
                    )
                )


# ---------------------------------------------------------------------------
# TypeScript/JavaScript edge extraction
# ---------------------------------------------------------------------------


def _extract_ts_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
    *,
    include_interfaces: bool,
) -> list[EntityEdge]:
    """Extract CONTAINS, IMPORTS, and EXTENDS edges from a TS/JS source tree."""
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name

    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}
    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node
    for child in root.children:
        _extract_ts_node_edges(
            child,
            rel_path,
            entity_by_name,
            file_entity,
            module_map,
            edges,
            include_interfaces,
        )

    return edges


def _extract_ts_node_edges(
    node,
    rel_path: str,
    entity_by_name: dict[str, Entity],
    file_entity: Entity,
    module_map: dict[str, str],
    edges: list[EntityEdge],
    include_interfaces: bool,
) -> None:
    """Extract edges from a single top-level TS/JS AST node."""
    node_type = node.type

    # Unwrap export_statement
    if node_type == "export_statement":
        for child in node.children:
            if child.type in (
                "class_declaration",
                "function_declaration",
                "interface_declaration",
                "abstract_class_declaration",
                "lexical_declaration",
            ):
                _extract_ts_node_edges(
                    child,
                    rel_path,
                    entity_by_name,
                    file_entity,
                    module_map,
                    edges,
                    include_interfaces,
                )
        return

    # import_statement → IMPORTS edge
    if node_type == "import_statement":
        import_path = _get_ts_import_path(node)
        if import_path:
            target_path = _resolve_ts_import(import_path, module_map)
            if target_path:
                edges.append(
                    EntityEdge(
                        source_id=file_entity.id,
                        target_id=f"path:{target_path}",
                        relationship=EdgeType.IMPORTS,
                    )
                )
        return

    # Class declaration → CONTAINS + EXTENDS + method CONTAINS
    if node_type in ("class_declaration", "abstract_class_declaration"):
        class_name = _field_text(node, "name") or _child_text_by_type(node, "type_identifier", "identifier")
        if not class_name:
            return

        class_entity = entity_by_name.get(class_name)
        if class_entity:
            # file → class CONTAINS
            edges.append(
                EntityEdge(
                    source_id=file_entity.id,
                    target_id=class_entity.id,
                    relationship=EdgeType.CONTAINS,
                )
            )

            # Check for extends clause → EXTENDS edge
            base_name = _get_ts_extends_name(node)
            if base_name:
                base_entity = entity_by_name.get(base_name)
                target_id = base_entity.id if base_entity else f"class:{base_name}"
                edges.append(
                    EntityEdge(
                        source_id=class_entity.id,
                        target_id=target_id,
                        relationship=EdgeType.EXTENDS,
                    )
                )

            # class → method CONTAINS
            body = node.child_by_field_name("body") or _child_by_type(node, "class_body")
            if body:
                for method in body.children:
                    if method.type == "method_definition":
                        method_name = _field_text(method, "name") or _child_text_by_type(
                            method, "property_identifier", "identifier"
                        )
                        if method_name and not method_name.startswith("#"):
                            qualified = f"{class_name}.{method_name}"
                            method_entity = entity_by_name.get(qualified)
                            if method_entity:
                                edges.append(
                                    EntityEdge(
                                        source_id=class_entity.id,
                                        target_id=method_entity.id,
                                        relationship=EdgeType.CONTAINS,
                                    )
                                )
        return

    # Interface declaration → file CONTAINS interface
    if node_type == "interface_declaration" and include_interfaces:
        iface_name = _field_text(node, "name") or _child_text_by_type(node, "type_identifier", "identifier")
        if iface_name:
            iface_entity = entity_by_name.get(iface_name)
            if iface_entity:
                edges.append(
                    EntityEdge(
                        source_id=file_entity.id,
                        target_id=iface_entity.id,
                        relationship=EdgeType.CONTAINS,
                    )
                )
        return

    # Function declaration → file CONTAINS function
    if node_type == "function_declaration":
        func_name = _field_text(node, "name") or _child_text_by_type(node, "identifier")
        if func_name:
            func_entity = entity_by_name.get(func_name)
            if func_entity:
                edges.append(
                    EntityEdge(
                        source_id=file_entity.id,
                        target_id=func_entity.id,
                        relationship=EdgeType.CONTAINS,
                    )
                )
        return

    # Lexical declaration with arrow function → file CONTAINS function
    if node_type == "lexical_declaration":
        for child in node.children:
            if child.type == "variable_declarator":
                var_name = _field_text(child, "name") or _child_text_by_type(child, "identifier")
                value = child.child_by_field_name("value")
                if var_name and value and value.type == "arrow_function":
                    func_entity = entity_by_name.get(var_name)
                    if func_entity:
                        edges.append(
                            EntityEdge(
                                source_id=file_entity.id,
                                target_id=func_entity.id,
                                relationship=EdgeType.CONTAINS,
                            )
                        )
        return


def _get_ts_import_path(import_stmt) -> str | None:
    """Get the module path string from an import_statement node."""
    # Try named field 'source' first (some grammar versions use this)
    source = import_stmt.child_by_field_name("source")
    if source and source.text:
        return source.text.decode("utf-8").strip("'\"")
    # Fallback: last string child
    for child in import_stmt.children:
        if child.type == "string" and child.text:
            return child.text.decode("utf-8").strip("'\"")
    return None


def _get_ts_extends_name(class_node) -> str | None:
    """Get the base class name from a TypeScript/JavaScript class declaration node."""
    # Look for class_heritage child, then extends_clause within it
    for child in class_node.children:
        if child.type == "class_heritage":
            for hchild in child.children:
                if hchild.type == "extends_clause":
                    return _extract_extends_type_name(hchild)
            return None
        # Some grammar versions have extends_clause directly as a child
        if child.type == "extends_clause":
            return _extract_extends_type_name(child)
    return None


def _extract_extends_type_name(extends_clause) -> str | None:
    """Extract the class name from an extends_clause node."""
    for child in extends_clause.children:
        if child.type in ("type_identifier", "identifier") and child.text:
            return child.text.decode("utf-8")
        if child.type == "generic_type":
            # Bar<T> → extract Bar
            inner = _child_by_type(child, "type_identifier", "identifier")
            if inner and inner.text:
                return inner.text.decode("utf-8")
        if child.type == "member_expression":
            # NS.Bar → extract Bar (property)
            prop = child.child_by_field_name("property")
            if prop and prop.text:
                return prop.text.decode("utf-8")
    return None


def _resolve_ts_import(import_path: str, module_map: dict[str, str]) -> str | None:
    """Resolve a TypeScript/JavaScript import path using the module map."""
    # Direct match (e.g., "./base" → "base.ts")
    if import_path in module_map:
        return module_map[import_path]

    # Try matching after stripping extension from import_path
    common_exts = (".ts", ".tsx", ".js", ".jsx")
    import_stem = import_path
    for ext in common_exts:
        if import_path.endswith(ext):
            import_stem = import_path[: -len(ext)]
            break

    # Try matching module_map keys by their stem
    for key, value in module_map.items():
        key_stem = key
        for ext in common_exts:
            if key.endswith(ext):
                key_stem = key[: -len(ext)]
                break
        if key_stem == import_stem:
            return value

    return None


# ---------------------------------------------------------------------------
# TypeScript/JavaScript module map construction
# ---------------------------------------------------------------------------


def _build_ts_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a module map for TypeScript/JavaScript files.

    Maps path-without-extension and file stem to the repo-relative file path,
    allowing import resolution by path stem.

    Requirements: 102-REQ-3.2
    """
    module_map: dict[str, str] = {}
    for f in files:
        try:
            rel_path = str(f.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue

        # Map the full path without extension (e.g., "src/components/button")
        last_part = rel_path.rsplit("/", 1)[-1]
        if "." in last_part:
            path_no_ext = rel_path[: -(len(last_part) - last_part.rfind("."))]
            # path_no_ext = rel_path.rsplit(".", 1)[0]
        else:
            path_no_ext = rel_path
        module_map[path_no_ext] = rel_path

        # Also map just the filename stem (e.g., "button")
        stem = f.stem
        if stem not in module_map:
            module_map[stem] = rel_path

    return module_map
