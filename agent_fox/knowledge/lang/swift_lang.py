"""Swift language analyzer for the entity graph.

Implements LanguageAnalyzer for Swift source files using tree-sitter-swift.

Tree-sitter Swift grammar notes (tree-sitter-swift 0.0.1):
- Root node type: ``source_file``.
- ``class_declaration``: Covers ``class``, ``struct``, and ``enum`` declarations.
  The ``type_identifier`` direct child is the name. A ``class_body`` child
  contains ``function_declaration`` children for methods.
- ``protocol_declaration``: Covers ``protocol`` declarations. The
  ``type_identifier`` direct child is the name. A ``protocol_body`` child
  contains ``protocol_function_declaration`` children.
- ``function_declaration``: Top-level functions at ``source_file`` level.
  The ``simple_identifier`` direct child is the name.
- ``import_declaration``: ``import Module`` statements. The ``identifier``
  child contains a ``simple_identifier`` grandchild with the module name.
- ``inheritance_specifier``: Inheritance clause ``class Foo: Bar``. The
  ``user_type`` child contains a ``type_identifier`` grandchild.
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

    Extracts FILE, CLASS (class/struct/enum/protocol), and FUNCTION
    (top-level functions and methods, qualified as ``ClassName.method``)
    entities. Produces CONTAINS, IMPORTS, and EXTENDS edges.
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
        """Extract FILE, CLASS, and FUNCTION entities from a Swift source tree."""
        return _extract_swift_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS, IMPORTS, and EXTENDS edges from a Swift source tree."""
        return _extract_swift_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Return an empty module map.

        Swift modules are identified by target name (a build-system concept),
        not by file path. Without build system knowledge, imports cannot be
        resolved to specific files.
        """
        return {}


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------


def _extract_swift_entities(tree, rel_path: str) -> list[Entity]:
    """Extract all entities from a parsed Swift source tree."""
    now = ENTITY_EPOCH
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    entities.append(make_entity(EntityType.FILE, file_name, rel_path, now=now))

    for child in tree.root_node.children:
        if child.type == "class_declaration":
            # Covers class, struct, and enum declarations.
            _collect_class_entities(child, rel_path, entities, now)

        elif child.type == "protocol_declaration":
            _collect_protocol_entities(child, rel_path, entities, now)

        elif child.type == "function_declaration":
            # Top-level function.
            func_name = _get_simple_identifier(child)
            if func_name:
                entities.append(make_entity(EntityType.FUNCTION, func_name, rel_path, now=now))

    return entities


def _collect_class_entities(
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

    # Walk class_body for method declarations.
    for child in class_node.children:
        if child.type == "class_body":
            for body_child in child.children:
                if body_child.type == "function_declaration":
                    method_name = _get_simple_identifier(body_child)
                    if method_name:
                        qualified = f"{class_name}.{method_name}"
                        entities.append(make_entity(EntityType.FUNCTION, qualified, rel_path, now=now))


def _collect_protocol_entities(
    protocol_node,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect CLASS entities from a protocol_declaration node."""
    protocol_name = _get_type_identifier(protocol_node)
    if protocol_name is None:
        return

    entities.append(make_entity(EntityType.CLASS, protocol_name, rel_path, now=now))

    # Protocols do not have method bodies, so no FUNCTION entities are extracted.


# ---------------------------------------------------------------------------
# Edge extraction
# ---------------------------------------------------------------------------


def _extract_swift_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS, IMPORTS, and EXTENDS edges from a parsed Swift tree."""
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name
    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}

    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    for child in tree.root_node.children:
        if child.type == "import_declaration":
            module_name = _get_import_module_name(child)
            if module_name is not None:
                target_path = module_map.get(module_name)
                if target_path is not None:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=f"path:{target_path}",
                            relationship=EdgeType.IMPORTS,
                        )
                    )
                # External or unresolvable imports are silently skipped.

        elif child.type == "class_declaration":
            class_edges = _extract_class_edges(child, file_entity, entity_by_name)
            edges.extend(class_edges)

        elif child.type == "protocol_declaration":
            protocol_name = _get_type_identifier(child)
            if protocol_name:
                proto_entity = entity_by_name.get(protocol_name)
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

    return edges


def _extract_class_edges(
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

    # CONTAINS: file → class/struct/enum
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
            # EXTENDS: class → base types
            for base_name in _extract_inheritance_names(child):
                base_entity = entity_by_name.get(base_name)
                edges.append(
                    EntityEdge(
                        source_id=class_entity.id,
                        target_id=base_entity.id if base_entity else f"class:{base_name}",
                        relationship=EdgeType.EXTENDS,
                    )
                )

        elif child.type == "class_body" and class_entity:
            # CONTAINS: class → methods
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
# Tree-sitter node helpers (Swift-specific)
# ---------------------------------------------------------------------------


def _get_type_identifier(node) -> str | None:
    """Get the text of the first ``type_identifier`` direct child of *node*."""
    for child in node.children:
        if child.type == "type_identifier":
            return node_text(child)
    return None


def _get_simple_identifier(node) -> str | None:
    """Get the text of the first ``simple_identifier`` direct child of *node*."""
    for child in node.children:
        if child.type == "simple_identifier":
            return node_text(child)
    return None


def _get_import_module_name(import_node) -> str | None:
    """Extract the module name from an ``import_declaration`` node.

    Navigates: import_declaration → identifier → simple_identifier
    """
    for child in import_node.children:
        if child.type == "identifier":
            return _get_simple_identifier(child)
    return None


def _extract_inheritance_names(inheritance_specifier_node) -> list[str]:
    """Extract all inherited type names from an ``inheritance_specifier`` node.

    Navigates: inheritance_specifier → user_type → type_identifier
    """
    names: list[str] = []
    for child in inheritance_specifier_node.children:
        if child.type == "user_type":
            name = _get_type_identifier(child)
            if name:
                names.append(name)
    return names
