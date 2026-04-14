"""Rust language analyzer for the entity graph.

Implements LanguageAnalyzer for Rust source files using tree-sitter-rust.

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1
"""

from __future__ import annotations

import uuid
from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType

# Module-level import so the name can be patched in tests (TS-102-E2).
try:
    from tree_sitter_rust import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# RustAnalyzer
# ---------------------------------------------------------------------------


class RustAnalyzer:
    """Language analyzer for Rust source files (.rs).

    Extracts FILE, MODULE (mod items), CLASS (struct/enum/trait), and FUNCTION
    (fn items and impl methods) entities. Produces CONTAINS edges. Rust uses
    traits rather than inheritance, so no EXTENDS edges are produced.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1
    """

    @property
    def language_name(self) -> str:
        return "rust"

    @property
    def file_extensions(self) -> set[str]:
        return {".rs"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Rust."""
        if language is None:
            raise ImportError("tree-sitter-rust is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, MODULE, CLASS, and FUNCTION entities from a Rust tree."""
        return _extract_rust_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS and IMPORTS edges. No EXTENDS (102-REQ-3.E1)."""
        return _extract_rust_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a Rust module map: crate-relative mod path -> repo-relative file path."""
        return _build_rust_module_map(repo_root, files)


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
# Rust entity extraction
# ---------------------------------------------------------------------------


def _extract_rust_entities(tree, rel_path: str) -> list[Entity]:
    """Extract all entities from a parsed Rust source tree."""
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
    _collect_rust_entities(root, rel_path, entities, now, impl_type=None)
    return entities


def _collect_rust_entities(
    node,
    rel_path: str,
    entities: list[Entity],
    now: str,
    impl_type: str | None,
) -> None:
    """Recursively collect Rust entities from a node's children."""
    for child in node.children:
        if child.type == "mod_item":
            # MODULE entity: mod utils; or mod utils { ... }
            mod_name = _field_text(child, "name") or _child_text_by_type(child, "identifier")
            if mod_name:
                entities.append(
                    Entity(
                        id=str(uuid.uuid4()),
                        entity_type=EntityType.MODULE,
                        entity_name=mod_name,
                        entity_path=rel_path,
                        created_at=now,
                        deleted_at=None,
                    )
                )
            # Recurse into inline mod bodies
            body = child.child_by_field_name("body")
            if body:
                _collect_rust_entities(body, rel_path, entities, now, impl_type=None)

        elif child.type in ("struct_item", "enum_item", "trait_item"):
            # CLASS entity
            type_name = (
                _field_text(child, "name")
                or _child_text_by_type(child, "type_identifier")
            )
            if type_name:
                entities.append(
                    Entity(
                        id=str(uuid.uuid4()),
                        entity_type=EntityType.CLASS,
                        entity_name=type_name,
                        entity_path=rel_path,
                        created_at=now,
                        deleted_at=None,
                    )
                )

        elif child.type == "function_item":
            # FUNCTION entity (possibly qualified if inside an impl block)
            func_name = _field_text(child, "name") or _child_text_by_type(child, "identifier")
            if func_name:
                qualified = f"{impl_type}.{func_name}" if impl_type else func_name
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

        elif child.type == "impl_item":
            # impl Type { ... } or impl Trait for Type { ... }
            # Use the 'type' field as the implementation target
            type_node = child.child_by_field_name("type")
            if type_node is None:
                # Fallback: find type_identifier
                type_node = _child_by_type(child, "type_identifier")
            impl_type_name = _node_text(type_node)

            body = child.child_by_field_name("body")
            if body is None:
                body = _child_by_type(child, "declaration_list")
            if body and impl_type_name:
                _collect_rust_entities(body, rel_path, entities, now, impl_type=impl_type_name)

        elif child.type == "declaration_list":
            # Recurse into declaration lists (already handled via impl_item above)
            _collect_rust_entities(child, rel_path, entities, now, impl_type=impl_type)


# ---------------------------------------------------------------------------
# Rust edge extraction
# ---------------------------------------------------------------------------


def _extract_rust_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS and IMPORTS edges from a parsed Rust source tree.

    Rust uses traits rather than inheritance, so no EXTENDS edges are produced.

    Requirements: 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1
    """
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name

    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}
    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node
    _collect_rust_edges(root, rel_path, entities, module_map, edges, file_entity, impl_type=None)
    return edges


def _collect_rust_edges(
    node,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
    edges: list[EntityEdge],
    file_entity: Entity,
    impl_type: str | None,
) -> None:
    """Recursively collect Rust edges from a node's children."""
    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}

    for child in node.children:
        if child.type == "mod_item":
            mod_name = _field_text(child, "name") or _child_text_by_type(child, "identifier")
            if mod_name:
                mod_entity = entity_by_name.get(mod_name)
                if mod_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=mod_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )
            # Recurse into inline mod body
            body = child.child_by_field_name("body")
            if body:
                _collect_rust_edges(
                    body, rel_path, entities, module_map, edges, file_entity, impl_type=None
                )

        elif child.type in ("struct_item", "enum_item", "trait_item"):
            type_name = (
                _field_text(child, "name")
                or _child_text_by_type(child, "type_identifier")
            )
            if type_name:
                class_entity = entity_by_name.get(type_name)
                if class_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=class_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

        elif child.type == "function_item":
            func_name = _field_text(child, "name") or _child_text_by_type(child, "identifier")
            if func_name:
                qualified = f"{impl_type}.{func_name}" if impl_type else func_name
                func_entity = entity_by_name.get(qualified)
                if func_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=func_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

        elif child.type == "impl_item":
            type_node = child.child_by_field_name("type")
            if type_node is None:
                type_node = _child_by_type(child, "type_identifier")
            impl_type_name = _node_text(type_node)

            body = child.child_by_field_name("body")
            if body is None:
                body = _child_by_type(child, "declaration_list")
            if body and impl_type_name:
                _collect_rust_edges(
                    body,
                    rel_path,
                    entities,
                    module_map,
                    edges,
                    file_entity,
                    impl_type=impl_type_name,
                )

        elif child.type == "use_declaration":
            # IMPORTS edge from use_declaration
            use_edges = _extract_rust_use_edges(child, file_entity, module_map)
            edges.extend(use_edges)


def _extract_rust_use_edges(
    use_decl,
    file_entity: Entity,
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract IMPORTS edges from a Rust use_declaration node."""
    edges: list[EntityEdge] = []
    path_text = _get_rust_use_path(use_decl)
    if path_text is None:
        return edges

    # Strip crate:: prefix, convert :: to /
    stripped = path_text.removeprefix("crate::").removeprefix("self::").removeprefix("super::")
    normalized = stripped.replace("::", "/")

    # Try exact match first, then basename
    target_path = module_map.get(normalized) or module_map.get(normalized.split("/")[-1])
    if target_path is None:
        # Unresolvable (external) — skip silently (102-REQ-3.4)
        return edges

    edges.append(
        EntityEdge(
            source_id=file_entity.id,
            target_id=f"path:{target_path}",
            relationship=EdgeType.IMPORTS,
        )
    )
    return edges


def _get_rust_use_path(use_decl) -> str | None:
    """Extract the use path text from a use_declaration node."""
    for child in use_decl.children:
        if child.type not in ("use", ";", "pub"):
            if child.text:
                return child.text.decode("utf-8")
    return None


# ---------------------------------------------------------------------------
# Rust module map construction
# ---------------------------------------------------------------------------


def _build_rust_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a mapping from Rust module paths to repo-relative file paths.

    Maps both:
    - The file stem (e.g., "utils" for "src/utils.rs")
    - A relative path without extension (e.g., "src/utils" for "src/utils.rs")

    Requirements: 102-REQ-3.2
    """
    module_map: dict[str, str] = {}
    for rs_file in files:
        rel_path = str(rs_file.relative_to(repo_root)).replace("\\", "/")
        stem = rs_file.stem  # "utils" from "src/utils.rs"

        # Map by stem (e.g., "utils" → "src/utils.rs")
        if stem not in ("lib", "main", "mod"):
            module_map[stem] = rel_path

        # Map by path without extension (e.g., "src/utils" → "src/utils.rs")
        path_no_ext = rel_path[: -len(rs_file.suffix)]
        module_map[path_no_ext] = rel_path

        # For mod.rs files, map the parent dir name
        if rs_file.name == "mod.rs":
            parent_stem = rs_file.parent.name
            module_map[parent_stem] = rel_path

    return module_map
