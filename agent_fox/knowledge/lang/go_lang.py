"""Go language analyzer for the entity graph.

Implements LanguageAnalyzer for Go source files using tree-sitter-go.

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType, normalize_path

# Module-level import so the name can be patched in tests (TS-102-E2).
# The try/except allows the module to be imported even when tree-sitter-go
# is not installed; make_parser() raises ImportError in that case.
try:
    from tree_sitter_go import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# GoAnalyzer
# ---------------------------------------------------------------------------


class GoAnalyzer:
    """Language analyzer for Go source files (.go).

    Extracts FILE, MODULE (package), CLASS (struct/interface), and FUNCTION
    entities, together with CONTAINS and IMPORTS edges. Go has no inheritance
    so no EXTENDS edges are produced.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1
    """

    @property
    def language_name(self) -> str:
        return "go"

    @property
    def file_extensions(self) -> set[str]:
        return {".go"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Go."""
        if language is None:
            raise ImportError("tree-sitter-go is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, MODULE, CLASS, and FUNCTION entities from a Go tree."""
        return _extract_go_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS and IMPORTS edges from a Go tree. No EXTENDS."""
        return _extract_go_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a Go package module map: package_name -> repo-relative directory.

        Requirements: 102-REQ-3.2
        """
        return _build_go_module_map(repo_root, files)


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
# Go entity extraction
# ---------------------------------------------------------------------------


def _extract_go_entities(tree, rel_path: str) -> list[Entity]:
    """Extract all entities from a parsed Go source tree."""
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
        # MODULE entity from package_clause
        if child.type == "package_clause":
            pkg_name = _field_text(child, "name") or _child_text_by_type(child, "package_identifier")
            if pkg_name:
                dir_path = normalize_path(str(Path(rel_path).parent))
                # For root-level files dir_path is "" (empty); fall back to
                # the file's rel_path so entity_path is always non-empty.
                module_path = dir_path if dir_path else rel_path
                entities.append(
                    Entity(
                        id=str(uuid.uuid4()),
                        entity_type=EntityType.MODULE,
                        entity_name=pkg_name,
                        entity_path=module_path,
                        created_at=now,
                        deleted_at=None,
                    )
                )

        # CLASS entities from type_declaration → type_spec
        elif child.type == "type_declaration":
            for type_spec in child.children:
                if type_spec.type != "type_spec":
                    continue
                type_name = _field_text(type_spec, "name") or _child_text_by_type(type_spec, "type_identifier")
                # Only extract struct and interface types as CLASS entities
                has_struct_or_iface = any(c.type in ("struct_type", "interface_type") for c in type_spec.children)
                if type_name and has_struct_or_iface:
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

        # FUNCTION entity from function_declaration
        elif child.type == "function_declaration":
            func_name = _field_text(child, "name") or _child_text_by_type(child, "identifier")
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

        # FUNCTION entity from method_declaration (qualified as Type.Method)
        elif child.type == "method_declaration":
            receiver_type = _get_go_receiver_type(child)
            method_name = _field_text(child, "name") or _child_text_by_type(child, "field_identifier")
            if receiver_type and method_name:
                qualified = f"{receiver_type}.{method_name}"
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

    return entities


def _get_go_receiver_type(method_decl) -> str | None:
    """Extract the receiver type name from a Go method_declaration node."""
    # Try named field 'receiver' first
    receiver = method_decl.child_by_field_name("receiver")
    if receiver is None:
        # Fallback: find the first parameter_list child
        for child in method_decl.children:
            if child.type == "parameter_list":
                receiver = child
                break

    if receiver is None:
        return None

    # Navigate: parameter_list → parameter_declaration → type
    for child in receiver.children:
        if child.type == "parameter_declaration":
            type_node = child.child_by_field_name("type")
            if type_node is None:
                # fallback: find type node by type
                for c in child.children:
                    if c.type in ("type_identifier", "pointer_type"):
                        type_node = c
                        break

            if type_node is not None:
                if type_node.type == "type_identifier":
                    return _node_text(type_node)
                elif type_node.type == "pointer_type":
                    # *Server → find type_identifier inside
                    inner = _child_by_type(type_node, "type_identifier")
                    if inner:
                        return _node_text(inner)

    return None


# ---------------------------------------------------------------------------
# Go edge extraction
# ---------------------------------------------------------------------------


def _extract_go_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS and IMPORTS edges from a parsed Go source tree.

    Go does not support class inheritance, so no EXTENDS edges are produced.

    Requirements: 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1
    """
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name

    # Build name → entity lookup for entities in this file
    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}
    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node

    for child in root.children:
        # CONTAINS: file → struct/interface (CLASS)
        if child.type == "type_declaration":
            for type_spec in child.children:
                if type_spec.type != "type_spec":
                    continue
                type_name = _field_text(type_spec, "name") or _child_text_by_type(type_spec, "type_identifier")
                has_struct_or_iface = any(c.type in ("struct_type", "interface_type") for c in type_spec.children)
                if type_name and has_struct_or_iface:
                    class_entity = entity_by_name.get(type_name)
                    if class_entity:
                        edges.append(
                            EntityEdge(
                                source_id=file_entity.id,
                                target_id=class_entity.id,
                                relationship=EdgeType.CONTAINS,
                            )
                        )

        # CONTAINS: file → function (FUNCTION)
        elif child.type == "function_declaration":
            func_name = _field_text(child, "name") or _child_text_by_type(child, "identifier")
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

        # CONTAINS: file → method (FUNCTION, qualified)
        elif child.type == "method_declaration":
            receiver_type = _get_go_receiver_type(child)
            method_name = _field_text(child, "name") or _child_text_by_type(child, "field_identifier")
            if receiver_type and method_name:
                qualified = f"{receiver_type}.{method_name}"
                method_entity = entity_by_name.get(qualified)
                if method_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=method_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

        # IMPORTS: from import_declaration
        elif child.type == "import_declaration":
            import_edges = _extract_go_import_edges(child, file_entity, module_map)
            edges.extend(import_edges)

    return edges


def _extract_go_import_edges(
    import_decl,
    file_entity: Entity,
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract IMPORTS edges from a Go import_declaration node."""
    edges: list[EntityEdge] = []

    # Collect all import_spec nodes (single or inside import_spec_list)
    specs: list = []
    for child in import_decl.children:
        if child.type == "import_spec":
            specs.append(child)
        elif child.type == "import_spec_list":
            for grandchild in child.children:
                if grandchild.type == "import_spec":
                    specs.append(grandchild)

    for spec in specs:
        import_path = _get_go_import_path(spec)
        if import_path is None:
            continue

        # Resolve: try the last path segment (package name) against module_map
        last_segment = import_path.split("/")[-1]
        target_dir = module_map.get(last_segment)

        if target_dir is None:
            # Also try the full import path (for local relative imports)
            target_dir = module_map.get(import_path)

        if target_dir is None:
            # Unresolvable (external dependency) — skip silently (102-REQ-3.4)
            continue

        sentinel_id = f"path:{target_dir}"
        edges.append(
            EntityEdge(
                source_id=file_entity.id,
                target_id=sentinel_id,
                relationship=EdgeType.IMPORTS,
            )
        )

    return edges


def _get_go_import_path(import_spec) -> str | None:
    """Extract the unquoted import path string from an import_spec node."""
    # Try named field 'path' first
    path_node = import_spec.child_by_field_name("path")
    if path_node is None:
        # Fallback: find interpreted_string_literal
        path_node = _child_by_type(import_spec, "interpreted_string_literal")
    if path_node and path_node.text:
        raw = path_node.text.decode("utf-8").strip()
        # Strip surrounding double quotes: "fmt" → fmt
        return raw.strip('"')
    return None


# ---------------------------------------------------------------------------
# Go module map construction
# ---------------------------------------------------------------------------


def _build_go_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a mapping from Go package names to repo-relative directory paths.

    For each Go file, reads the package declaration and maps
    `package_name → repo-relative directory path`.

    Requirements: 102-REQ-3.2
    """
    module_map: dict[str, str] = {}
    for go_file in files:
        package_name = _read_go_package_name(go_file)
        if package_name:
            dir_path = str(go_file.parent.relative_to(repo_root)).replace("\\", "/")
            # normalize: "." for root-level files
            if dir_path == ".":
                dir_path = ""
            module_map[package_name] = dir_path
    return module_map


_GO_PACKAGE_RE = re.compile(r"^\s*package\s+(\w+)", re.MULTILINE)


def _read_go_package_name(go_file: Path) -> str | None:
    """Read the package name from a Go source file using regex."""
    try:
        content = go_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _GO_PACKAGE_RE.search(content)
    return match.group(1) if match else None
