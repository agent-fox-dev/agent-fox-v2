"""C# language analyzer for the entity graph.

Implements LanguageAnalyzer for C# source files using tree-sitter-c-sharp.

Requirements: 107-REQ-1.1, 107-REQ-1.2, 107-REQ-1.3, 107-REQ-1.4, 107-REQ-1.5
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import (
    ENTITY_EPOCH,
    child_text_by_type,
    make_entity,
    node_text,
)

# Module-level import so the name can be patched in tests (TS-107-E9).
try:
    from tree_sitter_c_sharp import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# CSharpAnalyzer
# ---------------------------------------------------------------------------


class CSharpAnalyzer:
    """Language analyzer for C# source files (.cs).

    Extracts FILE, MODULE (namespace), CLASS (class/struct/interface/enum/record),
    and FUNCTION (method) entities. Produces CONTAINS, IMPORTS, and EXTENDS edges.

    Requirements: 107-REQ-1.1, 107-REQ-1.2, 107-REQ-1.3, 107-REQ-1.4, 107-REQ-1.5
    """

    @property
    def language_name(self) -> str:
        return "csharp"

    @property
    def file_extensions(self) -> set[str]:
        return {".cs"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for C#."""
        if language is None:
            raise ImportError("tree-sitter-c-sharp is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, MODULE, CLASS, and FUNCTION entities from a C# tree."""
        return _extract_csharp_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS, IMPORTS, and EXTENDS edges from a C# tree."""
        return _extract_csharp_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a C# namespace.ClassName → repo-relative file path mapping.

        Requirements: 107-REQ-1.5
        """
        return _build_csharp_module_map(repo_root, files)


# ---------------------------------------------------------------------------
# Node type constants
# ---------------------------------------------------------------------------

_CLASS_NODE_TYPES = frozenset(
    {
        "class_declaration",
        "struct_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
    }
)


# ---------------------------------------------------------------------------
# C# entity extraction
# ---------------------------------------------------------------------------


def _extract_csharp_entities(tree, rel_path: str) -> list[Entity]:
    """Extract all entities from a parsed C# source tree."""
    now = ENTITY_EPOCH
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    # FILE entity
    entities.append(make_entity(EntityType.FILE, file_name, rel_path, now=now))

    root = tree.root_node
    for child in root.children:
        if child.type == "namespace_declaration":
            _collect_csharp_namespace_entities(child, rel_path, entities, now)
        elif child.type in _CLASS_NODE_TYPES:
            # Top-level class (no namespace)
            _collect_csharp_class_entities(child, rel_path, entities, now)

    return entities


def _collect_csharp_namespace_entities(
    ns_node,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect MODULE and nested CLASS/FUNCTION entities from a namespace_declaration."""
    ns_name = _get_csharp_namespace_name(ns_node)
    if ns_name is None:
        return

    # MODULE entity — use dotted name converted to slash path
    ns_path = ns_name.replace(".", "/")
    entities.append(make_entity(EntityType.MODULE, ns_name, ns_path, now=now))

    # Walk the declaration_list body
    for child in ns_node.children:
        if child.type == "declaration_list":
            for decl in child.children:
                if decl.type in _CLASS_NODE_TYPES:
                    _collect_csharp_class_entities(decl, rel_path, entities, now)


def _collect_csharp_class_entities(
    class_node,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect CLASS and FUNCTION entities from a class/struct/interface/enum/record node."""
    class_name = child_text_by_type(class_node, "identifier")
    if class_name is None:
        return

    entities.append(make_entity(EntityType.CLASS, class_name, rel_path, now=now))

    # Walk the declaration_list for methods
    for child in class_node.children:
        if child.type == "declaration_list":
            for decl in child.children:
                if decl.type == "method_declaration":
                    method_name = child_text_by_type(decl, "identifier")
                    if method_name:
                        qualified = f"{class_name}.{method_name}"
                        entities.append(make_entity(EntityType.FUNCTION, qualified, rel_path, now=now))


def _get_csharp_namespace_name(ns_node) -> str | None:
    """Extract the namespace name from a namespace_declaration node."""
    for child in ns_node.children:
        if child.type in ("qualified_name", "identifier"):
            return node_text(child)
    return None


# ---------------------------------------------------------------------------
# C# edge extraction
# ---------------------------------------------------------------------------


def _extract_csharp_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS, IMPORTS, and EXTENDS edges from a parsed C# source tree.

    Requirements: 107-REQ-1.4, 107-REQ-1.E1
    """
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name
    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}

    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node
    for child in root.children:
        if child.type == "using_directive":
            # IMPORTS edges from using directives
            import_name = _get_using_directive_name(child)
            if import_name:
                target_path = module_map.get(import_name)
                if target_path is not None:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=f"path:{target_path}",
                            relationship=EdgeType.IMPORTS,
                        )
                    )
                # If not in module_map → external dep → skip silently (107-REQ-1.E1)

        elif child.type == "namespace_declaration":
            ns_name = _get_csharp_namespace_name(child)
            ns_entity = entity_by_name.get(ns_name) if ns_name else None

            # CONTAINS: file -> namespace
            if ns_entity:
                edges.append(
                    EntityEdge(
                        source_id=file_entity.id,
                        target_id=ns_entity.id,
                        relationship=EdgeType.CONTAINS,
                    )
                )

            # Collect class-level edges within namespace
            for ns_child in child.children:
                if ns_child.type == "declaration_list":
                    for decl in ns_child.children:
                        if decl.type in _CLASS_NODE_TYPES:
                            class_edges = _extract_csharp_class_edges(decl, ns_entity, entity_by_name)
                            edges.extend(class_edges)

        elif child.type in _CLASS_NODE_TYPES:
            # Top-level class (no namespace)
            class_edges = _extract_csharp_class_edges(child, None, entity_by_name)
            edges.extend(class_edges)

    return edges


def _extract_csharp_class_edges(
    class_node,
    ns_entity: Entity | None,
    entity_by_name: dict[str, Entity],
) -> list[EntityEdge]:
    """Extract CONTAINS and EXTENDS edges for a class/struct/interface/enum/record."""
    edges: list[EntityEdge] = []

    class_name = child_text_by_type(class_node, "identifier")
    if class_name is None:
        return edges

    class_entity = entity_by_name.get(class_name)

    # CONTAINS: namespace -> class
    if ns_entity and class_entity:
        edges.append(
            EntityEdge(
                source_id=ns_entity.id,
                target_id=class_entity.id,
                relationship=EdgeType.CONTAINS,
            )
        )

    for child in class_node.children:
        if child.type == "base_list":
            # EXTENDS edges from inheritance / interface implementation
            if class_entity:
                for base_child in child.children:
                    if base_child.type in ("identifier", "qualified_name"):
                        base_name = node_text(base_child)
                        if base_name:
                            base_entity = entity_by_name.get(base_name)
                            edges.append(
                                EntityEdge(
                                    source_id=class_entity.id,
                                    target_id=base_entity.id if base_entity else f"class:{base_name}",
                                    relationship=EdgeType.EXTENDS,
                                )
                            )

        elif child.type == "declaration_list":
            # CONTAINS: class -> methods
            if class_entity:
                for decl in child.children:
                    if decl.type == "method_declaration":
                        method_name = child_text_by_type(decl, "identifier")
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


def _get_using_directive_name(node) -> str | None:
    """Extract the imported namespace name from a using_directive node."""
    for child in node.children:
        if child.type in ("qualified_name", "identifier"):
            return node_text(child)
    return None


# ---------------------------------------------------------------------------
# C# module map construction
# ---------------------------------------------------------------------------

_CS_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([\w.]+)", re.MULTILINE)
_CS_CLASS_RE = re.compile(
    r"(?:^|\s)(?:public\s+|private\s+|protected\s+|internal\s+|sealed\s+|abstract\s+|static\s+|partial\s+)*"
    r"(?:class|interface|struct|enum|record)\s+(\w+)",
    re.MULTILINE,
)


def _build_csharp_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a mapping from C# namespace-qualified class names to repo-relative file paths.

    Maps "Namespace.ClassName" → repo-relative POSIX path.

    Requirements: 107-REQ-1.5
    """
    module_map: dict[str, str] = {}
    for cs_file in files:
        try:
            content = cs_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        namespaces = _CS_NAMESPACE_RE.findall(content)
        class_names = _CS_CLASS_RE.findall(content)
        rel_path = str(cs_file.relative_to(repo_root)).replace("\\", "/")

        for ns in namespaces:
            for cls in class_names:
                fqn = f"{ns}.{cls}"
                module_map[fqn] = rel_path

        # Also map without namespace for top-level types
        if not namespaces:
            for cls in class_names:
                module_map[cls] = rel_path

    return module_map
