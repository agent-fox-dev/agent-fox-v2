"""Java language analyzer for the entity graph.

Implements LanguageAnalyzer for Java source files using tree-sitter-java.

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import (
    ENTITY_EPOCH,
    child_by_type,
    child_text_by_type,
    field_text,
    make_entity,
    node_text,
)

# Module-level import so the name can be patched in tests (TS-102-E2).
try:
    from tree_sitter_java import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# JavaAnalyzer
# ---------------------------------------------------------------------------


class JavaAnalyzer:
    """Language analyzer for Java source files (.java).

    Extracts FILE, MODULE (package), CLASS (class/interface/enum), and FUNCTION
    (method) entities. Produces CONTAINS, IMPORTS, and EXTENDS edges.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    @property
    def language_name(self) -> str:
        return "java"

    @property
    def file_extensions(self) -> set[str]:
        return {".java"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Java."""
        if language is None:
            raise ImportError("tree-sitter-java is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, MODULE, CLASS, and FUNCTION entities from a Java tree."""
        return _extract_java_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS, IMPORTS, and EXTENDS edges from a Java tree."""
        return _extract_java_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a Java FQN → repo-relative file path mapping.

        Maps fully qualified class names (e.g., "com.example.Foo") to
        repo-relative file paths.

        Requirements: 102-REQ-3.2
        """
        return _build_java_module_map(repo_root, files)


# ---------------------------------------------------------------------------
# Tree-sitter helpers
# ---------------------------------------------------------------------------

# Aliases for backward compatibility with internal references.
_node_text = node_text
_field_text = field_text
_child_by_type = child_by_type
_child_text_by_type = child_text_by_type


# ---------------------------------------------------------------------------
# Java entity extraction
# ---------------------------------------------------------------------------


def _extract_java_entities(tree, rel_path: str) -> list[Entity]:
    """Extract all entities from a parsed Java source tree."""
    now = ENTITY_EPOCH
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    # FILE entity
    entities.append(make_entity(EntityType.FILE, file_name, rel_path, now=now))

    root = tree.root_node

    for child in root.children:
        # MODULE entity from package_declaration
        if child.type == "package_declaration":
            pkg_name = _extract_java_package_name(child)
            if pkg_name:
                # Convert dotted package to slash-based path for entity_path
                pkg_path = pkg_name.replace(".", "/")
                entities.append(make_entity(EntityType.MODULE, pkg_name, pkg_path, now=now))

        # CLASS entities from class/interface/enum declarations
        elif child.type in (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "annotation_type_declaration",
        ):
            _collect_java_class_entities(child, rel_path, entities, now, parent_class=None)

    return entities


def _collect_java_class_entities(
    node,
    rel_path: str,
    entities: list[Entity],
    now: str,
    parent_class: str | None,
) -> None:
    """Collect CLASS and FUNCTION entities from a Java class/interface/enum node."""
    class_name = _field_text(node, "name") or _child_text_by_type(node, "identifier")
    if class_name is None:
        return

    # Use simple class name (not qualified with parent for top-level)
    entities.append(make_entity(EntityType.CLASS, class_name, rel_path, now=now))

    # Find the class/interface/enum body
    body = None
    for child in node.children:
        if child.type in ("class_body", "interface_body", "enum_body"):
            body = child
            break

    if body is None:
        return

    # Extract methods from the body
    for child in body.children:
        if child.type == "method_declaration":
            method_name = _field_text(child, "name") or _child_text_by_type(child, "identifier")
            if method_name:
                qualified = f"{class_name}.{method_name}"
                entities.append(make_entity(EntityType.FUNCTION, qualified, rel_path, now=now))
        # Nested classes
        elif child.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            _collect_java_class_entities(child, rel_path, entities, now, parent_class=class_name)


def _extract_java_package_name(pkg_decl) -> str | None:
    """Extract the package name text from a package_declaration node."""
    # In tree-sitter-java, package_declaration contains the package name
    # as a scoped_identifier or identifier
    for child in pkg_decl.children:
        if child.type in ("scoped_identifier", "identifier"):
            return _node_text(child)
    return None


# ---------------------------------------------------------------------------
# Java edge extraction
# ---------------------------------------------------------------------------


def _extract_java_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS, IMPORTS, and EXTENDS edges from a parsed Java source tree.

    Requirements: 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name

    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}
    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node

    for child in root.children:
        # IMPORTS edge from import_declaration
        if child.type == "import_declaration":
            import_edges = _extract_java_import_edges(child, file_entity, module_map)
            edges.extend(import_edges)

        # Class-level edges
        elif child.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            class_edges = _extract_java_class_edges(child, rel_path, entities, module_map, file_entity)
            edges.extend(class_edges)

    return edges


def _extract_java_class_edges(
    node,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
    file_entity: Entity,
) -> list[EntityEdge]:
    """Extract CONTAINS, and EXTENDS edges from a Java class/interface/enum node."""
    edges: list[EntityEdge] = []
    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}

    class_name = _field_text(node, "name") or _child_text_by_type(node, "identifier")
    if class_name is None:
        return edges

    class_entity = entity_by_name.get(class_name)

    # CONTAINS: file → class
    if class_entity:
        edges.append(
            EntityEdge(
                source_id=file_entity.id,
                target_id=class_entity.id,
                relationship=EdgeType.CONTAINS,
            )
        )

    # EXTENDS: from superclass
    if node.type == "class_declaration":
        superclass_node = node.child_by_field_name("superclass")
        if superclass_node is None:
            # Look for 'superclass' child by checking for 'extends' keyword then type
            superclass_node = _find_java_superclass(node)

        if superclass_node and class_entity:
            base_name = _extract_java_type_name(superclass_node)
            if base_name:
                base_entity = entity_by_name.get(base_name)
                if base_entity:
                    edges.append(
                        EntityEdge(
                            source_id=class_entity.id,
                            target_id=base_entity.id,
                            relationship=EdgeType.EXTENDS,
                        )
                    )
                else:
                    # Use class sentinel
                    edges.append(
                        EntityEdge(
                            source_id=class_entity.id,
                            target_id=f"class:{base_name}",
                            relationship=EdgeType.EXTENDS,
                        )
                    )

    # Find class body for method CONTAINS edges
    body = None
    for child in node.children:
        if child.type in ("class_body", "interface_body", "enum_body"):
            body = child
            break

    if body and class_entity:
        for child in body.children:
            if child.type == "method_declaration":
                method_name = _field_text(child, "name") or _child_text_by_type(child, "identifier")
                if method_name:
                    qualified = f"{class_name}.{method_name}"
                    method_entity = entity_by_name.get(qualified)
                    if method_entity:
                        # CONTAINS: class → method
                        edges.append(
                            EntityEdge(
                                source_id=class_entity.id,
                                target_id=method_entity.id,
                                relationship=EdgeType.CONTAINS,
                            )
                        )

    return edges


def _find_java_superclass(class_decl) -> object | None:
    """Find the superclass type node in a class_declaration.

    Looks for a child named 'superclass' or the type_identifier after 'extends'.
    """
    # Try named field first
    superclass = class_decl.child_by_field_name("superclass")
    if superclass is not None:
        return superclass

    # Fallback: look for the pattern 'extends <TypeName>'
    found_extends = False
    for child in class_decl.children:
        if child.type == "extends" or (child.text and _node_text(child) == "extends"):
            found_extends = True
            continue
        if found_extends and child.type in ("type_identifier", "generic_type"):
            return child
    return None


def _extract_java_type_name(type_node) -> str | None:
    """Extract a simple class name from a Java type node."""
    if type_node.type == "type_identifier":
        return _node_text(type_node)
    elif type_node.type == "generic_type":
        # e.g., List<String> → List
        return _child_text_by_type(type_node, "type_identifier")
    else:
        # Try getting text and stripping generics
        text = _node_text(type_node)
        if text:
            # Strip anything after '<'
            return text.split("<")[0].strip()
    return None


def _extract_java_import_edges(
    import_decl,
    file_entity: Entity,
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract IMPORTS edges from a Java import_declaration node."""
    edges: list[EntityEdge] = []

    # Get the fully qualified name from the import
    fqn = None
    for child in import_decl.children:
        if child.type in ("scoped_identifier", "identifier"):
            fqn = _node_text(child)
            break

    if fqn is None:
        return edges

    # Strip wildcard imports: "com.example.*" → "com.example"
    fqn = fqn.rstrip(".*")

    # Try exact FQN match in module_map
    target_path = module_map.get(fqn)

    if target_path is None:
        # Unresolvable (external dependency) — skip silently (102-REQ-3.4)
        return edges

    edges.append(
        EntityEdge(
            source_id=file_entity.id,
            target_id=f"path:{target_path}",
            relationship=EdgeType.IMPORTS,
        )
    )
    return edges


# ---------------------------------------------------------------------------
# Java module map construction
# ---------------------------------------------------------------------------


_JAVA_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def _build_java_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a mapping from Java FQNs to repo-relative file paths.

    For each Java file, reads the package declaration and maps
    "package.ClassName" → repo-relative file path.

    Requirements: 102-REQ-3.2
    """
    module_map: dict[str, str] = {}
    for java_file in files:
        package_name = _read_java_package_name(java_file)
        class_name = java_file.stem  # "Foo" from "Foo.java"
        rel_path = str(java_file.relative_to(repo_root)).replace("\\", "/")

        if package_name:
            fqn = f"{package_name}.{class_name}"
        else:
            fqn = class_name

        module_map[fqn] = rel_path
    return module_map


def _read_java_package_name(java_file: Path) -> str | None:
    """Read the package name from a Java source file using regex."""
    try:
        content = java_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _JAVA_PACKAGE_RE.search(content)
    return match.group(1) if match else None
