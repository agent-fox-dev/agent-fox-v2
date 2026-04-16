"""Swift language analyzer for the entity graph.

Implements LanguageAnalyzer for Swift source files using tree-sitter-swift
(https://github.com/alex-pinkus/tree-sitter-swift, PyPI: tree-sitter-swift).

Tree-sitter Swift grammar notes (tree-sitter-swift 0.0.1):
- ``class_declaration`` covers both ``class Foo {}`` and ``struct Foo {}``.
  The first keyword child is ``class`` or ``struct``.
- ``protocol_declaration`` covers protocol definitions.
- ``function_declaration`` covers top-level and member functions.
  - First child after ``func`` is ``simple_identifier`` (the name).
- ``class_body`` is the body node for both class and struct declarations.
- ``protocol_body`` is the body node for protocol declarations.
- ``import_declaration`` covers import statements.
  - ``identifier`` child gives the module name.
- ``inheritance_specifier`` (`:` clause) gives the base type name(s).

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import ENTITY_EPOCH, make_entity, node_text

# Module-level import so the name can be patched in tests.
try:
    from tree_sitter_swift import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# SwiftAnalyzer
# ---------------------------------------------------------------------------


class SwiftAnalyzer:
    """Language analyzer for Swift source files (.swift).

    Extracts FILE, CLASS (from class/struct/protocol declarations), and FUNCTION
    (top-level functions and methods, qualified as ClassName.methodName) entities.
    Produces CONTAINS and EXTENDS edges.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2
    """

    @property
    def language_name(self) -> str:
        return "swift"

    @property
    def file_extensions(self) -> set[str]:
        return {".swift"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Swift."""
        if language is None:
            raise ImportError("tree-sitter-swift is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, CLASS, and FUNCTION entities from a parsed Swift tree."""
        return _extract_swift_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS and EXTENDS edges from a parsed Swift tree."""
        return _extract_swift_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a Swift module map: module_name → repo-relative file path.

        Maps the stem of each Swift file (without extension) to its
        repo-relative POSIX path, enabling basic same-repo import resolution.
        """
        return _build_swift_module_map(repo_root, files)


# ---------------------------------------------------------------------------
# Swift entity extraction
# ---------------------------------------------------------------------------


def _extract_swift_entities(tree, rel_path: str) -> list[Entity]:
    """Extract all entities from a parsed Swift source tree."""
    now = ENTITY_EPOCH
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    # FILE entity — always present.
    entities.append(make_entity(EntityType.FILE, file_name, rel_path, now=now))

    root = tree.root_node
    for child in root.children:
        if child.type == "class_declaration":
            # Covers both ``class`` and ``struct`` declarations.
            _collect_swift_class_entities(child, rel_path, entities, now)

        elif child.type == "protocol_declaration":
            proto_name = _get_type_identifier(child)
            if proto_name:
                entities.append(make_entity(EntityType.CLASS, proto_name, rel_path, now=now))

        elif child.type == "function_declaration":
            func_name = _get_simple_identifier(child)
            if func_name:
                entities.append(make_entity(EntityType.FUNCTION, func_name, rel_path, now=now))

    return entities


def _collect_swift_class_entities(
    class_node,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect CLASS and FUNCTION entities from a class_declaration node."""
    class_name = _get_type_identifier(class_node)
    if class_name is None:
        return

    entities.append(make_entity(EntityType.CLASS, class_name, rel_path, now=now))

    # Walk class_body for methods.
    for child in class_node.children:
        if child.type == "class_body":
            for body_child in child.children:
                if body_child.type == "function_declaration":
                    method_name = _get_simple_identifier(body_child)
                    if method_name:
                        qualified = f"{class_name}.{method_name}"
                        entities.append(make_entity(EntityType.FUNCTION, qualified, rel_path, now=now))


# ---------------------------------------------------------------------------
# Swift edge extraction
# ---------------------------------------------------------------------------


def _extract_swift_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS and EXTENDS edges from a parsed Swift source tree."""
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name

    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}
    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node
    for child in root.children:
        if child.type == "class_declaration":
            class_edges = _extract_swift_class_edges(child, file_entity, entity_by_name)
            edges.extend(class_edges)

        elif child.type == "protocol_declaration":
            proto_name = _get_type_identifier(child)
            if proto_name:
                proto_entity = entity_by_name.get(proto_name)
                if proto_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=proto_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

        elif child.type == "function_declaration":
            func_name = _get_simple_identifier(child)
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

        elif child.type == "import_declaration":
            # IMPORTS edges from import statements.
            module_name = _get_import_identifier(child)
            if module_name:
                target_path = module_map.get(module_name)
                if target_path:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=f"path:{target_path}",
                            relationship=EdgeType.IMPORTS,
                        )
                    )

    return edges


def _extract_swift_class_edges(
    class_node,
    file_entity: Entity,
    entity_by_name: dict[str, Entity],
) -> list[EntityEdge]:
    """Extract CONTAINS and EXTENDS edges for a class_declaration."""
    edges: list[EntityEdge] = []

    class_name = _get_type_identifier(class_node)
    if class_name is None:
        return edges

    class_entity = entity_by_name.get(class_name)

    # CONTAINS: file → class.
    if class_entity:
        edges.append(
            EntityEdge(
                source_id=file_entity.id,
                target_id=class_entity.id,
                relationship=EdgeType.CONTAINS,
            )
        )

    for child in class_node.children:
        if child.type == "inheritance_specifier" and class_entity:
            # EXTENDS edges from the inheritance specifier (`: BaseClass`).
            base_name = _get_type_identifier(child) or node_text(child)
            # Trim leading `:` and whitespace if node_text returned it.
            if base_name:
                base_name = base_name.lstrip(": \t")
            if base_name:
                base_entity = entity_by_name.get(base_name)
                edges.append(
                    EntityEdge(
                        source_id=class_entity.id,
                        target_id=base_entity.id if base_entity else f"class:{base_name}",
                        relationship=EdgeType.EXTENDS,
                    )
                )

        elif child.type == "class_body" and class_entity:
            # CONTAINS: class → methods.
            for body_child in child.children:
                if body_child.type == "function_declaration":
                    method_name = _get_simple_identifier(body_child)
                    if method_name:
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

    return edges


# ---------------------------------------------------------------------------
# Swift module map
# ---------------------------------------------------------------------------


def _build_swift_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a mapping from Swift file stems to repo-relative POSIX paths.

    Maps ``filename_without_extension → repo-relative POSIX path`` for each
    Swift file.  This enables basic same-repo import resolution when the
    imported module name matches the source file stem.
    """
    module_map: dict[str, str] = {}
    for swift_file in files:
        try:
            rel_path = str(swift_file.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue
        module_map[swift_file.stem] = rel_path
    return module_map


# ---------------------------------------------------------------------------
# Tree-sitter node helpers (Swift-specific)
# ---------------------------------------------------------------------------


def _get_type_identifier(node) -> str | None:
    """Return the text of the first ``type_identifier`` direct child, or None."""
    for child in node.children:
        if child.type == "type_identifier":
            return node_text(child)
    return None


def _get_simple_identifier(node) -> str | None:
    """Return the text of the first ``simple_identifier`` direct child, or None."""
    for child in node.children:
        if child.type == "simple_identifier":
            return node_text(child)
    return None


def _get_import_identifier(import_decl_node) -> str | None:
    """Extract the imported module name from an import_declaration node."""
    for child in import_decl_node.children:
        if child.type == "identifier":
            return node_text(child)
    return None
