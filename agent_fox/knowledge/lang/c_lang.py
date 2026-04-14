"""C and C++ language analyzers for the entity graph.

Implements LanguageAnalyzer for C and C++ source files using
tree-sitter-c and tree-sitter-cpp.

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3, 102-REQ-3.E1
"""

from __future__ import annotations

import uuid
from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType


class CAnalyzer:
    """Language analyzer for C source and header files (.c, .h).

    Extracts FILE, CLASS (named structs), and FUNCTION entities,
    together with CONTAINS and IMPORTS (#include) edges.
    C has no inheritance, so no EXTENDS edges are produced.
    C has no module system, so no MODULE entities are produced.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1
    """

    @property
    def language_name(self) -> str:
        return "c"

    @property
    def file_extensions(self) -> set[str]:
        return {".c", ".h"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for C."""
        import tree_sitter_c as tsc  # type: ignore[import]
        from tree_sitter import Language, Parser

        return Parser(Language(tsc.language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, CLASS (struct), and FUNCTION entities from a C source file."""
        return _extract_c_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS and IMPORTS edges from a C source file. No EXTENDS."""
        return _extract_c_edges(tree, rel_path, entities, module_map, support_extends=False)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a C header include path map: repo-relative-path → repo-relative-path."""
        return _build_c_module_map(repo_root, files)


class CppAnalyzer:
    """Language analyzer for C++ source and header files (.cpp, .hpp, .cc, .cxx, .hh).

    Extracts FILE, MODULE (namespaces), CLASS (class/struct), and FUNCTION entities,
    together with CONTAINS, IMPORTS (#include), and EXTENDS edges.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    @property
    def language_name(self) -> str:
        return "cpp"

    @property
    def file_extensions(self) -> set[str]:
        return {".cpp", ".hpp", ".cc", ".cxx", ".hh"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for C++."""
        import tree_sitter_cpp as tscpp  # type: ignore[import]
        from tree_sitter import Language, Parser

        return Parser(Language(tscpp.language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, MODULE (namespace), CLASS, and FUNCTION entities from a C++ source file."""
        return _extract_cpp_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS, IMPORTS, and EXTENDS edges from a C++ source file."""
        return _extract_c_edges(tree, rel_path, entities, module_map, support_extends=True)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a C++ header include path map: repo-relative-path → repo-relative-path."""
        return _build_c_module_map(repo_root, files)


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
# C declarator helpers
# ---------------------------------------------------------------------------


def _get_declarator_name(node) -> str | None:
    """Recursively extract the identifier name from a C/C++ declarator node."""
    if node is None:
        return None
    if node.type == "identifier":
        return _node_text(node)
    if node.type == "field_identifier":
        return _node_text(node)
    if node.type == "destructor_name":
        # ~ClassName() → skip
        return None
    if node.type == "qualified_identifier":
        # ::name or Namespace::name → get the last identifier
        name_node = node.child_by_field_name("name")
        if name_node:
            return _get_declarator_name(name_node)
        # fallback: last identifier-like child
        for child in reversed(node.children):
            if child.type in ("identifier", "field_identifier"):
                return _node_text(child)
        return None
    if node.type in ("function_declarator", "abstract_function_declarator"):
        inner = node.child_by_field_name("declarator")
        if inner:
            return _get_declarator_name(inner)
        return None
    if node.type in ("pointer_declarator", "abstract_pointer_declarator"):
        inner = node.child_by_field_name("declarator")
        if inner:
            return _get_declarator_name(inner)
        return None
    if node.type == "reference_declarator":
        inner = node.child_by_field_name("declarator")
        if inner:
            return _get_declarator_name(inner)
        return None
    if node.type == "operator_name":
        return None  # Skip operator overloads
    # Try finding identifier in children
    for child in node.children:
        if child.type in ("identifier", "field_identifier"):
            return _node_text(child)
    return None


def _get_function_name_from_definition(function_def) -> str | None:
    """Get the function name from a function_definition node."""
    declarator = function_def.child_by_field_name("declarator")
    if declarator is None:
        return None
    return _get_declarator_name(declarator)


def _get_function_name_from_declaration(decl) -> str | None:
    """Get a function name from a declaration/field_declaration node, if it's a function."""
    declarator = decl.child_by_field_name("declarator")
    if declarator is None:
        return None

    # It's a function declaration if the declarator is a function_declarator
    # (possibly wrapped in pointer_declarator)
    def has_func_declarator(node) -> bool:
        if node.type == "function_declarator":
            return True
        if node.type in ("pointer_declarator", "reference_declarator"):
            inner = node.child_by_field_name("declarator")
            return has_func_declarator(inner) if inner else False
        return False

    if has_func_declarator(declarator):
        return _get_declarator_name(declarator)
    return None


# ---------------------------------------------------------------------------
# C include helper
# ---------------------------------------------------------------------------


def _get_include_path(preproc_include) -> str | None:
    """Get the include path from a preproc_include node if it is a quoted (local) include.

    Returns None for angle-bracket (system) includes.
    """
    # Try named field 'path'
    path_node = preproc_include.child_by_field_name("path")
    if path_node is None:
        for child in preproc_include.children:
            if child.type in ("string_literal", "system_lib_string"):
                path_node = child
                break

    if path_node is None:
        return None

    if path_node.type == "string_literal":
        raw = path_node.text.decode("utf-8").strip() if path_node.text else ""
        return raw.strip('"')

    # system_lib_string → angle-bracket include → skip (external)
    return None


# ---------------------------------------------------------------------------
# C entity extraction
# ---------------------------------------------------------------------------


def _extract_c_entities(tree, rel_path: str) -> list[Entity]:
    """Extract FILE, CLASS (struct), and FUNCTION entities from a C source tree.

    No MODULE entities (C has no module system).
    No EXTENDS edges (C has no inheritance).
    """
    now = "1970-01-01T00:00:00"
    file_name = Path(rel_path).name
    entities: list[Entity] = []

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
    _extract_c_scope_entities(root.children, rel_path, entities, now, current_class=None)

    return entities


def _extract_c_scope_entities(
    nodes,
    rel_path: str,
    entities: list[Entity],
    now: str,
    current_class: str | None,
) -> None:
    """Extract entities from a list of C AST nodes."""
    for node in nodes:
        node_type = node.type

        if node_type == "function_definition":
            func_name = _get_function_name_from_definition(node)
            if func_name:
                qualified = f"{current_class}.{func_name}" if current_class else func_name
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

        elif node_type == "declaration":
            # Could contain a named struct definition
            type_node = node.child_by_field_name("type")
            if type_node and type_node.type in ("struct_specifier", "union_specifier"):
                struct_name = _field_text(type_node, "name") or _child_text_by_type(type_node, "type_identifier")
                body = type_node.child_by_field_name("body") or _child_by_type(type_node, "field_declaration_list")
                if struct_name and body:
                    entities.append(
                        Entity(
                            id=str(uuid.uuid4()),
                            entity_type=EntityType.CLASS,
                            entity_name=struct_name,
                            entity_path=rel_path,
                            created_at=now,
                            deleted_at=None,
                        )
                    )

        elif node_type in ("struct_specifier", "union_specifier"):
            # Top-level standalone struct specifier
            struct_name = _field_text(node, "name") or _child_text_by_type(node, "type_identifier")
            body = node.child_by_field_name("body") or _child_by_type(node, "field_declaration_list")
            if struct_name and body:
                entities.append(
                    Entity(
                        id=str(uuid.uuid4()),
                        entity_type=EntityType.CLASS,
                        entity_name=struct_name,
                        entity_path=rel_path,
                        created_at=now,
                        deleted_at=None,
                    )
                )

        elif node_type == "type_definition":
            # typedef struct { ... } Name; or typedef struct Name { ... } Alias;
            type_node = _child_by_type(node, "struct_specifier", "union_specifier")
            if type_node:
                struct_name = _field_text(type_node, "name") or _child_text_by_type(type_node, "type_identifier")
                body = type_node.child_by_field_name("body") or _child_by_type(type_node, "field_declaration_list")
                if struct_name and body:
                    entities.append(
                        Entity(
                            id=str(uuid.uuid4()),
                            entity_type=EntityType.CLASS,
                            entity_name=struct_name,
                            entity_path=rel_path,
                            created_at=now,
                            deleted_at=None,
                        )
                    )


# ---------------------------------------------------------------------------
# C++ entity extraction
# ---------------------------------------------------------------------------


def _extract_cpp_entities(tree, rel_path: str) -> list[Entity]:
    """Extract FILE, MODULE (namespace), CLASS (class/struct), and FUNCTION entities."""
    now = "1970-01-01T00:00:00"
    file_name = Path(rel_path).name
    entities: list[Entity] = []

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
    _extract_cpp_scope_entities(root.children, rel_path, entities, now, current_class=None)

    return entities


def _extract_cpp_scope_entities(
    nodes,
    rel_path: str,
    entities: list[Entity],
    now: str,
    current_class: str | None,
) -> None:
    """Extract entities from a list of C++ AST nodes."""
    for node in nodes:
        node_type = node.type

        if node_type == "namespace_definition":
            ns_name = _field_text(node, "name") or _child_text_by_type(node, "namespace_identifier", "identifier")
            if ns_name:
                entities.append(
                    Entity(
                        id=str(uuid.uuid4()),
                        entity_type=EntityType.MODULE,
                        entity_name=ns_name,
                        entity_path=rel_path,
                        created_at=now,
                        deleted_at=None,
                    )
                )
            body = node.child_by_field_name("body") or _child_by_type(node, "declaration_list")
            if body:
                _extract_cpp_scope_entities(body.children, rel_path, entities, now, current_class=None)

        elif node_type in ("class_specifier", "struct_specifier"):
            cls_name = _field_text(node, "name") or _child_text_by_type(node, "type_identifier")
            if not cls_name:
                # Anonymous class/struct — skip
                continue
            entities.append(
                Entity(
                    id=str(uuid.uuid4()),
                    entity_type=EntityType.CLASS,
                    entity_name=cls_name,
                    entity_path=rel_path,
                    created_at=now,
                    deleted_at=None,
                )
            )
            body = node.child_by_field_name("body") or _child_by_type(node, "field_declaration_list")
            if body:
                _extract_cpp_scope_entities(body.children, rel_path, entities, now, current_class=cls_name)

        elif node_type == "function_definition":
            func_name = _get_function_name_from_definition(node)
            if func_name:
                qualified = f"{current_class}.{func_name}" if current_class else func_name
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

        elif node_type in ("declaration", "field_declaration"):
            # Could be a method declaration inside a class
            func_name = _get_function_name_from_declaration(node)
            if func_name and current_class:
                qualified = f"{current_class}.{func_name}"
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

        elif node_type == "access_specifier":
            pass  # public:, private:, protected: — skip

        elif node_type == "type_definition":
            # typedef class/struct
            type_node = _child_by_type(node, "class_specifier", "struct_specifier")
            if type_node:
                cls_name = _field_text(type_node, "name") or _child_text_by_type(type_node, "type_identifier")
                if cls_name:
                    entities.append(
                        Entity(
                            id=str(uuid.uuid4()),
                            entity_type=EntityType.CLASS,
                            entity_name=cls_name,
                            entity_path=rel_path,
                            created_at=now,
                            deleted_at=None,
                        )
                    )
                    body = type_node.child_by_field_name("body") or _child_by_type(type_node, "field_declaration_list")
                    if body:
                        _extract_cpp_scope_entities(body.children, rel_path, entities, now, current_class=cls_name)


# ---------------------------------------------------------------------------
# C/C++ edge extraction
# ---------------------------------------------------------------------------


def _extract_c_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
    *,
    support_extends: bool,
) -> list[EntityEdge]:
    """Extract CONTAINS, IMPORTS, and (for C++) EXTENDS edges from a C/C++ source tree."""
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name

    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}
    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node
    _extract_c_scope_edges(
        root.children,
        rel_path,
        entity_by_name,
        file_entity,
        module_map,
        edges,
        support_extends,
        current_class=None,
    )

    return edges


def _extract_c_scope_edges(
    nodes,
    rel_path: str,
    entity_by_name: dict[str, Entity],
    file_entity: Entity,
    module_map: dict[str, str],
    edges: list[EntityEdge],
    support_extends: bool,
    current_class: str | None,
) -> None:
    """Extract edges from a list of C/C++ AST nodes."""
    for node in nodes:
        node_type = node.type

        if node_type == "preproc_include":
            include_path = _get_include_path(node)
            if include_path:
                target_path = module_map.get(include_path) or module_map.get(Path(include_path).name)
                if target_path:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=f"path:{target_path}",
                            relationship=EdgeType.IMPORTS,
                        )
                    )

        elif node_type == "namespace_definition":
            ns_name = _field_text(node, "name") or _child_text_by_type(node, "namespace_identifier", "identifier")
            if ns_name:
                ns_entity = entity_by_name.get(ns_name)
                if ns_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=ns_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )
            body = node.child_by_field_name("body") or _child_by_type(node, "declaration_list")
            if body:
                _extract_c_scope_edges(
                    body.children,
                    rel_path,
                    entity_by_name,
                    file_entity,
                    module_map,
                    edges,
                    support_extends,
                    current_class=None,
                )

        elif node_type in ("class_specifier", "struct_specifier"):
            cls_name = _field_text(node, "name") or _child_text_by_type(node, "type_identifier")
            if not cls_name:
                continue
            cls_entity = entity_by_name.get(cls_name)
            parent_entity = entity_by_name.get(current_class) if current_class else file_entity

            if cls_entity and parent_entity:
                edges.append(
                    EntityEdge(
                        source_id=parent_entity.id,
                        target_id=cls_entity.id,
                        relationship=EdgeType.CONTAINS,
                    )
                )

            # C++ inheritance via base_class_clause
            if support_extends and cls_entity:
                for child in node.children:
                    if child.type == "base_class_clause":
                        base_name = _get_cpp_base_class_name(child)
                        if base_name:
                            base_entity = entity_by_name.get(base_name)
                            target_id = base_entity.id if base_entity else f"class:{base_name}"
                            edges.append(
                                EntityEdge(
                                    source_id=cls_entity.id,
                                    target_id=target_id,
                                    relationship=EdgeType.EXTENDS,
                                )
                            )

            body = node.child_by_field_name("body") or _child_by_type(node, "field_declaration_list")
            if body:
                _extract_c_scope_edges(
                    body.children,
                    rel_path,
                    entity_by_name,
                    file_entity,
                    module_map,
                    edges,
                    support_extends,
                    current_class=cls_name,
                )

        elif node_type == "function_definition":
            func_name = _get_function_name_from_definition(node)
            if func_name:
                qualified = f"{current_class}.{func_name}" if current_class else func_name
                func_entity = entity_by_name.get(qualified)
                parent_entity = entity_by_name.get(current_class) if current_class else file_entity
                if func_entity and parent_entity:
                    edges.append(
                        EntityEdge(
                            source_id=parent_entity.id,
                            target_id=func_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

        elif node_type in ("declaration", "field_declaration"):
            # Struct definition inside declaration (C)
            type_node = node.child_by_field_name("type")
            if type_node and type_node.type in ("struct_specifier", "union_specifier"):
                struct_name = _field_text(type_node, "name") or _child_text_by_type(type_node, "type_identifier")
                body = type_node.child_by_field_name("body") or _child_by_type(type_node, "field_declaration_list")
                if struct_name and body:
                    struct_entity = entity_by_name.get(struct_name)
                    if struct_entity:
                        edges.append(
                            EntityEdge(
                                source_id=file_entity.id,
                                target_id=struct_entity.id,
                                relationship=EdgeType.CONTAINS,
                            )
                        )
            # Method declaration inside a C++ class
            elif current_class:
                func_name = _get_function_name_from_declaration(node)
                if func_name:
                    qualified = f"{current_class}.{func_name}"
                    func_entity = entity_by_name.get(qualified)
                    cls_entity = entity_by_name.get(current_class)
                    if func_entity and cls_entity:
                        edges.append(
                            EntityEdge(
                                source_id=cls_entity.id,
                                target_id=func_entity.id,
                                relationship=EdgeType.CONTAINS,
                            )
                        )

        elif node_type == "type_definition":
            type_node = _child_by_type(node, "class_specifier", "struct_specifier")
            if type_node:
                cls_name = _field_text(type_node, "name") or _child_text_by_type(type_node, "type_identifier")
                if cls_name:
                    cls_entity = entity_by_name.get(cls_name)
                    if cls_entity:
                        edges.append(
                            EntityEdge(
                                source_id=file_entity.id,
                                target_id=cls_entity.id,
                                relationship=EdgeType.CONTAINS,
                            )
                        )
                    body = type_node.child_by_field_name("body") or _child_by_type(type_node, "field_declaration_list")
                    if body:
                        _extract_c_scope_edges(
                            body.children,
                            rel_path,
                            entity_by_name,
                            file_entity,
                            module_map,
                            edges,
                            support_extends,
                            current_class=cls_name,
                        )


def _get_cpp_base_class_name(base_clause) -> str | None:
    """Extract the first base class type name from a C++ base_class_clause node."""
    for child in base_clause.children:
        if child.type == "type_identifier":
            return _node_text(child)
        if child.type == "qualified_identifier":
            # Namespace::Base → get the last part
            name_node = child.child_by_field_name("name")
            if name_node:
                return _node_text(name_node)
    return None


# ---------------------------------------------------------------------------
# C/C++ module map construction
# ---------------------------------------------------------------------------


def _build_c_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a C/C++ include module map mapping repo-relative paths to themselves.

    Maps each header file's repo-relative path (used in #include "...") to its
    actual repo-relative path, and also maps the filename alone.

    Requirements: 102-REQ-3.2
    """
    module_map: dict[str, str] = {}
    for f in files:
        try:
            rel_path = str(f.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue
        # Map full repo-relative path (e.g., "utils/math.h" → "utils/math.h")
        module_map[rel_path] = rel_path
        # Also map just the filename (e.g., "math.h" → "utils/math.h")
        if f.name not in module_map:
            module_map[f.name] = rel_path

    return module_map
