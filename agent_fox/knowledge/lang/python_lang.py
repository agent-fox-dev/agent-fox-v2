"""Python language analyzer for the entity graph.

Implements LanguageAnalyzer for Python source files using tree-sitter-python.
The extraction logic is refactored from the original static_analysis.py
(Spec 95) and must produce identical entity natural keys and edge triples.

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3,
              102-REQ-6.1, 102-REQ-6.2
"""

from __future__ import annotations

import uuid
from pathlib import Path

from agent_fox.knowledge.entities import (
    EdgeType,
    Entity,
    EntityEdge,
    EntityType,
    normalize_path,
)

# ---------------------------------------------------------------------------
# PythonAnalyzer
# ---------------------------------------------------------------------------


class PythonAnalyzer:
    """Language analyzer for Python source files.

    Extracts FILE, MODULE (from __init__.py packages), CLASS, and FUNCTION
    entities, together with CONTAINS, IMPORTS, and EXTENDS edges — producing
    output identical to the original Spec-95 static_analysis.py.

    Requirements: 102-REQ-6.1, 102-REQ-6.2
    """

    @property
    def language_name(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> set[str]:
        return {".py"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Python."""
        from tree_sitter import Language, Parser
        from tree_sitter_python import language as py_language  # type: ignore[import]

        return Parser(Language(py_language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, CLASS, and FUNCTION entities from a parsed tree."""
        return _extract_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS, IMPORTS, and EXTENDS edges from a parsed tree."""
        return _extract_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a dotted-path module map for Python import resolution."""
        return _build_module_map(repo_root, files)


# ---------------------------------------------------------------------------
# Module map construction (refactored from static_analysis.py)
# ---------------------------------------------------------------------------


def _build_module_map(repo_root: Path, py_files: list[Path]) -> dict[str, str]:
    """Build a mapping from dotted Python import paths to repo-relative file paths.

    Requirements: 95-REQ-4.6, 102-REQ-3.2
    """
    module_map: dict[str, str] = {}
    for py_file in py_files:
        dotted = _file_to_dotted_path(repo_root, py_file)
        if dotted:
            repo_rel = str(py_file.relative_to(repo_root)).replace("\\", "/")
            module_map[dotted] = repo_rel
    return module_map


def _file_to_dotted_path(repo_root: Path, py_file: Path) -> str | None:
    """Convert a Python file path to a dotted module import path.

    Returns None if the file is not part of a package.
    """
    rel = py_file.relative_to(repo_root)
    parts = list(rel.parts)

    if not parts:
        return None

    last = parts[-1]
    if last == "__init__.py":
        if len(parts) == 1:
            return None
        module_parts = parts[:-1]
    elif last.endswith(".py"):
        module_parts = parts[:-1] + [last[:-3]]
    else:
        return None

    if not module_parts:
        return None

    # Verify all intermediate directories have __init__.py
    for i in range(1, len(module_parts)):
        pkg_dir = repo_root.joinpath(*module_parts[:i])
        if not (pkg_dir / "__init__.py").is_file():
            return None

    return ".".join(module_parts)


# ---------------------------------------------------------------------------
# Entity extraction (refactored from static_analysis.py)
# ---------------------------------------------------------------------------


def _extract_entities(tree, rel_path: str) -> list[Entity]:
    """Extract file, class, and function entities from a parsed tree.

    Requirements: 95-REQ-4.2, 102-REQ-2.1
    """
    entities: list[Entity] = []
    now = "1970-01-01T00:00:00"

    # File entity
    file_name = Path(rel_path).name
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

    _extract_recursive(tree.root_node, rel_path, entities, parent_class=None, now=now)
    return entities


def _extract_recursive(
    node,
    rel_path: str,
    entities: list[Entity],
    parent_class: str | None,
    now: str,
) -> None:
    """Recursively extract class and function entities from a tree-sitter node."""
    for child in node.children:
        if child.type == "class_definition":
            class_name = _get_identifier(child)
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
                _extract_recursive(child, rel_path, entities, parent_class=class_name, now=now)

        elif child.type == "function_definition":
            func_name = _get_identifier(child)
            if func_name:
                qualified_name = f"{parent_class}.{func_name}" if parent_class else func_name
                entities.append(
                    Entity(
                        id=str(uuid.uuid4()),
                        entity_type=EntityType.FUNCTION,
                        entity_name=qualified_name,
                        entity_path=rel_path,
                        created_at=now,
                        deleted_at=None,
                    )
                )
                _extract_recursive(child, rel_path, entities, parent_class=parent_class, now=now)

        elif child.type == "decorated_definition":
            for grandchild in child.children:
                if grandchild.type in ("class_definition", "function_definition"):
                    _extract_recursive(
                        type("_FakeNode", (), {"children": [grandchild]})(),
                        rel_path,
                        entities,
                        parent_class=parent_class,
                        now=now,
                    )

        else:
            if child.type in ("block", "module"):
                _extract_recursive(child, rel_path, entities, parent_class=parent_class, now=now)


def _get_identifier(node) -> str | None:
    """Get the identifier name from a class_definition or function_definition node."""
    for child in node.children:
        if child.type == "identifier":
            return child.text.decode("utf-8") if child.text else None
    return None


# ---------------------------------------------------------------------------
# Edge extraction (refactored from static_analysis.py)
# ---------------------------------------------------------------------------


def _extract_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS, IMPORTS, and EXTENDS edges from a parsed tree.

    Requirements: 95-REQ-4.3, 95-REQ-4.6, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """
    entity_by_type_name: dict[tuple[str, str], Entity] = {
        (str(e.entity_type), e.entity_name): e for e in entities
    }
    file_name = Path(rel_path).name
    edges: list[EntityEdge] = []

    file_entity = entity_by_type_name.get((EntityType.FILE, file_name))

    for child in tree.root_node.children:
        if child.type == "class_definition":
            class_name = _get_identifier(child)
            if class_name and file_entity:
                class_entity = entity_by_type_name.get((EntityType.CLASS, class_name))
                if class_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=class_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

                # Extract base classes (extends edges)
                for grandchild in child.children:
                    if grandchild.type == "argument_list":
                        for base_node in grandchild.children:
                            if base_node.type == "identifier":
                                base_name = base_node.text.decode("utf-8") if base_node.text else None
                                if base_name and class_entity:
                                    base_entity = entity_by_type_name.get((EntityType.CLASS, base_name))
                                    if base_entity:
                                        edges.append(
                                            EntityEdge(
                                                source_id=class_entity.id,
                                                target_id=base_entity.id,
                                                relationship=EdgeType.EXTENDS,
                                            )
                                        )
                                    else:
                                        sentinel_id = f"class:{base_name}"
                                        edges.append(
                                            EntityEdge(
                                                source_id=class_entity.id,
                                                target_id=sentinel_id,
                                                relationship=EdgeType.EXTENDS,
                                            )
                                        )

                # Extract method contains edges
                for grandchild in child.children:
                    if grandchild.type == "block":
                        for method_node in grandchild.children:
                            if method_node.type == "function_definition":
                                method_name = _get_identifier(method_node)
                                if method_name and class_entity:
                                    qualified = f"{class_name}.{method_name}"
                                    method_entity = entity_by_type_name.get(
                                        (EntityType.FUNCTION, qualified)
                                    )
                                    if method_entity:
                                        edges.append(
                                            EntityEdge(
                                                source_id=class_entity.id,
                                                target_id=method_entity.id,
                                                relationship=EdgeType.CONTAINS,
                                            )
                                        )

        elif child.type == "function_definition":
            func_name = _get_identifier(child)
            if func_name and file_entity:
                func_entity = entity_by_type_name.get((EntityType.FUNCTION, func_name))
                if func_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=func_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

        elif child.type in ("import_statement", "import_from_statement"):
            if file_entity:
                import_edges = _extract_import_edges(child, file_entity, module_map)
                edges.extend(import_edges)

        elif child.type == "decorated_definition":
            for grandchild in child.children:
                if grandchild.type == "class_definition" and file_entity:
                    class_name = _get_identifier(grandchild)
                    if class_name:
                        class_entity = entity_by_type_name.get((EntityType.CLASS, class_name))
                        if class_entity:
                            edges.append(
                                EntityEdge(
                                    source_id=file_entity.id,
                                    target_id=class_entity.id,
                                    relationship=EdgeType.CONTAINS,
                                )
                            )
                elif grandchild.type == "function_definition" and file_entity:
                    func_name = _get_identifier(grandchild)
                    if func_name:
                        func_entity = entity_by_type_name.get((EntityType.FUNCTION, func_name))
                        if func_entity:
                            edges.append(
                                EntityEdge(
                                    source_id=file_entity.id,
                                    target_id=func_entity.id,
                                    relationship=EdgeType.CONTAINS,
                                )
                            )

    return edges


def _extract_import_edges(
    import_node,
    file_entity: Entity,
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract import edges from an import statement node."""
    edges: list[EntityEdge] = []

    if import_node.type == "import_from_statement":
        module_dotted = None
        for child in import_node.children:
            if child.type == "dotted_name":
                module_dotted = child.text.decode("utf-8") if child.text else None
                break
        if module_dotted:
            _add_resolved_import_edge(module_dotted, file_entity, module_map, edges)

    elif import_node.type == "import_statement":
        for child in import_node.children:
            if child.type == "dotted_name":
                module_dotted = child.text.decode("utf-8") if child.text else None
                if module_dotted:
                    _add_resolved_import_edge(module_dotted, file_entity, module_map, edges)

    return edges


def _add_resolved_import_edge(
    module_dotted: str,
    file_entity: Entity,
    module_map: dict[str, str],
    edges: list[EntityEdge],
) -> None:
    """Try to resolve module_dotted to a repo-relative path and add an import edge."""
    target_path = module_map.get(module_dotted)

    if target_path is None:
        parts = module_dotted.split(".")
        for n in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:n])
            target_path = module_map.get(prefix)
            if target_path:
                break

    if target_path is None:
        # Cannot resolve — silently skip per 102-REQ-3.4
        return

    sentinel_id = f"path:{target_path}"
    edges.append(
        EntityEdge(
            source_id=file_entity.id,
            target_id=sentinel_id,
            relationship=EdgeType.IMPORTS,
        )
    )


# ---------------------------------------------------------------------------
# Module entity extraction helper
# ---------------------------------------------------------------------------


def extract_module_entities(repo_root: Path, py_files: list[Path]) -> list[Entity]:
    """Create MODULE entities for __init__.py packages.

    Called by the orchestrator (static_analysis.py) to create module entities
    before per-file extraction begins.
    """
    now = "1970-01-01T00:00:00"
    entities: list[Entity] = []
    for py_file in py_files:
        rel = py_file.relative_to(repo_root)
        if rel.name == "__init__.py" and len(rel.parts) > 1:
            pkg_dir_parts = rel.parts[:-1]
            pkg_name = pkg_dir_parts[-1]
            pkg_path = normalize_path("/".join(pkg_dir_parts))
            entities.append(
                Entity(
                    id=str(uuid.uuid4()),
                    entity_type=EntityType.MODULE,
                    entity_name=pkg_name,
                    entity_path=pkg_path,
                    created_at=now,
                    deleted_at=None,
                )
            )
    return entities
