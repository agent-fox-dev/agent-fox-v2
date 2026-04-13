"""Tree-sitter static analysis for the entity graph subsystem.

Scans Python source files, extracts entities (files, modules, classes,
functions) and structural edges (contains, imports, extends), then
upserts them into the entity graph via entity_store.

Requirements: 95-REQ-4.*
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import duckdb

from agent_fox.knowledge.entities import (
    AnalysisResult,
    EdgeType,
    Entity,
    EntityEdge,
    EntityType,
    normalize_path,
)
from agent_fox.knowledge.entity_store import (
    soft_delete_missing,
    upsert_edges,
    upsert_entities,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File scanning
# ---------------------------------------------------------------------------


def _load_gitignore_spec(repo_root: Path):  # type: ignore[return]
    """Load gitignore patterns from .gitignore in repo_root (if it exists).

    Returns a pathspec.PathSpec or None if pathspec is unavailable or no
    .gitignore exists.
    """
    gitignore = repo_root / ".gitignore"
    if not gitignore.is_file():
        return None
    try:
        import pathspec  # type: ignore[import]

        return pathspec.PathSpec.from_lines("gitignore", gitignore.read_text().splitlines())
    except ImportError:
        logger.warning("pathspec library not available; .gitignore patterns will not be applied")
        return None


def _scan_python_files(repo_root: Path) -> list[Path]:
    """Return all `.py` files under repo_root, excluding .gitignore-matched paths.

    Requirements: 95-REQ-4.1
    """
    spec = _load_gitignore_spec(repo_root)
    results: list[Path] = []
    for py_file in sorted(repo_root.rglob("*.py")):
        rel = py_file.relative_to(repo_root)
        if spec is not None and spec.match_file(str(rel)):
            continue
        results.append(py_file)
    return results


# ---------------------------------------------------------------------------
# Module map construction
# ---------------------------------------------------------------------------


def _build_module_map(repo_root: Path, py_files: list[Path]) -> dict[str, str]:
    """Build a mapping from dotted Python import paths to repo-relative file paths.

    For each Python file, derives the dotted module path by walking up the
    directory tree and checking for __init__.py at each level.

    Requirements: 95-REQ-4.6
    """
    module_map: dict[str, str] = {}

    for py_file in py_files:
        # Check if all parent directories up to any level contain __init__.py
        # to determine the package depth.  We accept partial packages too.
        dotted = _file_to_dotted_path(repo_root, py_file)
        if dotted:
            repo_rel = str(py_file.relative_to(repo_root)).replace("\\", "/")
            module_map[dotted] = repo_rel

    return module_map


def _file_to_dotted_path(repo_root: Path, py_file: Path) -> str | None:
    """Convert a Python file path to a dotted module import path.

    Returns None if the file is not part of a package (i.e., no __init__.py
    in any ancestor directory up to repo_root).

    For __init__.py files themselves, returns the package dotted path.
    """
    rel = py_file.relative_to(repo_root)
    parts = list(rel.parts)

    if not parts:
        return None

    # Strip the .py extension from the last component
    last = parts[-1]
    if last == "__init__.py":
        # The module is the parent package
        if len(parts) == 1:
            return None  # top-level __init__.py has no meaningful dotted path
        module_parts = parts[:-1]
    elif last.endswith(".py"):
        module_parts = parts[:-1] + [last[:-3]]
    else:
        return None

    # For the file to be importable via dotted path, its parent directories
    # must form a package chain (__init__.py at each level).
    # We allow partial packages -- any depth is fine.
    if not module_parts:
        return None

    # Verify all intermediate directories have __init__.py
    for i in range(1, len(module_parts)):
        pkg_dir = repo_root.joinpath(*module_parts[:i])
        if not (pkg_dir / "__init__.py").is_file():
            # Not part of a proper package hierarchy; skip this file
            return None

    return ".".join(module_parts)


# ---------------------------------------------------------------------------
# Tree-sitter parsing and entity extraction
# ---------------------------------------------------------------------------


def _make_parser():  # type: ignore[return]
    """Create a tree-sitter Parser for Python."""
    from tree_sitter import Language, Parser
    from tree_sitter_python import language as py_language  # type: ignore[import]

    return Parser(Language(py_language()))


def _parse_file(file_path: Path, parser) -> object | None:  # type: ignore[return]
    """Parse a Python file with tree-sitter.

    Returns the parse Tree, or None if the file cannot be read.
    Logs a warning if the resulting tree contains parse errors.

    Requirements: 95-REQ-4.E1
    """
    try:
        source = file_path.read_bytes()
    except OSError as exc:
        logger.warning("Cannot read file %s: %s", file_path, exc)
        return None

    tree = parser.parse(source)

    if tree.root_node.has_error:
        logger.warning("Parse errors in %s; skipping file", file_path)
        return None

    return tree


def _extract_entities(tree, rel_path: str) -> list[Entity]:  # type: ignore[return]
    """Extract file, class, and function entities from a parsed tree.

    - One FILE entity per file (entity_name = basename, entity_path = rel_path).
    - One CLASS entity per class definition.
    - One FUNCTION entity per function/method definition; methods use qualified
      names (ClassName.method_name).

    Requirements: 95-REQ-4.2
    """
    entities: list[Entity] = []
    now = "1970-01-01T00:00:00"  # placeholder; real timestamp set at upsert

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

    # Walk tree for class and function definitions
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
                # Recurse into class body with class context
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
                # Recurse into function body (for nested functions/classes)
                _extract_recursive(child, rel_path, entities, parent_class=parent_class, now=now)

        elif child.type == "decorated_definition":
            # Handle decorated classes and functions
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
            # Recurse into other blocks (e.g., module-level blocks)
            if child.type in ("block", "module"):
                _extract_recursive(child, rel_path, entities, parent_class=parent_class, now=now)


def _get_identifier(node) -> str | None:
    """Get the identifier name from a class_definition or function_definition node."""
    for child in node.children:
        if child.type == "identifier":
            return child.text.decode("utf-8") if child.text else None
    return None


# ---------------------------------------------------------------------------
# Edge extraction
# ---------------------------------------------------------------------------


def _extract_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract contains, imports, and extends edges from a parsed tree.

    - contains: file → class, file → top-level function, class → method
    - imports:  file → imported file (resolved via module_map)
    - extends:  subclass → base class (within the same file)

    Returns a list of EntityEdge objects. Note that source_id and target_id
    fields contain the entity_path of the referenced entities (not real UUIDs),
    so they must be resolved to actual IDs by the caller after upserting.

    Since we don't have the real UUIDs at extraction time, we return "path-keyed"
    edges that use the entity's natural key as a surrogate ID, resolved in
    analyze_codebase() once all entities have been upserted.

    Requirements: 95-REQ-4.3, 95-REQ-4.6
    """
    # Build a lookup: (entity_type_str, entity_name) -> entity for this file
    entity_by_type_name: dict[tuple[str, str], Entity] = {(str(e.entity_type), e.entity_name): e for e in entities}
    file_name = Path(rel_path).name

    edges: list[EntityEdge] = []

    # Collect top-level structure
    file_entity = entity_by_type_name.get((EntityType.FILE, file_name))

    # Walk tree for top-level nodes
    for child in tree.root_node.children:
        if child.type == "class_definition":
            class_name = _get_identifier(child)
            if class_name and file_entity:
                class_entity = entity_by_type_name.get((EntityType.CLASS, class_name))
                if class_entity:
                    # file contains class
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
                                        # class extends base (same file)
                                        edges.append(
                                            EntityEdge(
                                                source_id=class_entity.id,
                                                target_id=base_entity.id,
                                                relationship=EdgeType.EXTENDS,
                                            )
                                        )
                                    else:
                                        # Base class not in this file; use a sentinel ID
                                        # that analyze_codebase will try to resolve globally.
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
                                    method_entity = entity_by_type_name.get((EntityType.FUNCTION, qualified))
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
            # Extract imports
            if file_entity:
                import_edges = _extract_import_edges(child, file_entity, module_map)
                edges.extend(import_edges)

        elif child.type == "decorated_definition":
            # Handle decorated top-level definitions
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
    """Extract import edges from an import statement node.

    Resolves dotted Python import paths via module_map.
    Logs a warning for imports that cannot be resolved.

    Requirements: 95-REQ-4.6
    """
    edges: list[EntityEdge] = []

    if import_node.type == "import_from_statement":
        # "from X import Y" — the module is the dotted_name after "from"
        module_dotted = None
        for child in import_node.children:
            if child.type == "dotted_name":
                module_dotted = child.text.decode("utf-8") if child.text else None
                break  # take only the first dotted_name (the module)

        if module_dotted:
            _add_resolved_import_edge(module_dotted, file_entity, module_map, edges)

    elif import_node.type == "import_statement":
        # "import X" or "import X, Y"
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
    """Try to resolve module_dotted to a repo-relative path and add an import edge.

    Uses a sentinel entity ID based on the target path for later resolution.
    """
    # Try exact match first, then try prefixes (e.g., "pkg.mod" -> "pkg/mod.py")
    target_path = module_map.get(module_dotted)

    if target_path is None:
        # Try prefix matches: "pkg.mod.sub" -> try "pkg.mod" -> "pkg"
        parts = module_dotted.split(".")
        for n in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:n])
            target_path = module_map.get(prefix)
            if target_path:
                break

    if target_path is None:
        logger.warning("Cannot resolve import %r to a known module; skipping", module_dotted)
        return

    # Use a sentinel ID: "path:<target_path>" for later resolution by analyze_codebase
    sentinel_id = f"path:{target_path}"
    edges.append(
        EntityEdge(
            source_id=file_entity.id,
            target_id=sentinel_id,
            relationship=EdgeType.IMPORTS,
        )
    )


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def analyze_codebase(repo_root: Path, conn: duckdb.DuckDBPyConnection) -> AnalysisResult:
    """Scan the Python codebase at repo_root and populate the entity graph.

    1. Validates repo_root.
    2. Scans Python files (respecting .gitignore).
    3. Builds module map.
    4. Extracts module entities from packages (__init__.py directories).
    5. Parses each file with tree-sitter, extracts entities and edges.
    6. Upserts all entities, then resolves and upserts edges.
    7. Soft-deletes entities no longer found.
    8. Returns AnalysisResult with counts.

    Requirements: 95-REQ-4.4, 95-REQ-4.5, 95-REQ-4.E2, 95-REQ-4.E3
    """
    if not repo_root.exists() or not repo_root.is_dir():
        raise ValueError(f"repo_root does not exist or is not a directory: {repo_root!r}")

    py_files = _scan_python_files(repo_root)

    if not py_files:
        logger.info("No Python files found under %s", repo_root)
        # Still call soft_delete_missing so that entities from a prior analysis
        # of this repo_root are correctly soft-deleted (95-REQ-4.5).
        entities_soft_deleted = soft_delete_missing(conn, set())
        return AnalysisResult(
            entities_upserted=0,
            edges_upserted=0,
            entities_soft_deleted=entities_soft_deleted,
        )

    module_map = _build_module_map(repo_root, py_files)
    parser = _make_parser()

    # --- Phase 1: Extract module entities from __init__.py packages ---
    all_entities: list[Entity] = []
    # Track which files have __init__.py packages
    for py_file in py_files:
        rel = py_file.relative_to(repo_root)
        if rel.name == "__init__.py" and len(rel.parts) > 1:
            # This is a package: create a MODULE entity for the directory
            pkg_dir_parts = rel.parts[:-1]  # drop __init__.py
            pkg_name = pkg_dir_parts[-1]  # last directory component
            pkg_path = "/".join(pkg_dir_parts)  # e.g., "pkg" or "pkg/sub"
            all_entities.append(
                Entity(
                    id=str(uuid.uuid4()),
                    entity_type=EntityType.MODULE,
                    entity_name=pkg_name,
                    entity_path=pkg_path,
                    created_at="1970-01-01T00:00:00",
                    deleted_at=None,
                )
            )

    # --- Phase 2: Extract file entities and structural entities ---
    # Map from file rel_path -> list of entities extracted
    file_entity_lists: dict[str, list[Entity]] = {}
    # Collect "sentinel" edges with path-based target IDs
    sentinel_edges: list[EntityEdge] = []

    for py_file in py_files:
        rel_path = normalize_path(str(py_file.relative_to(repo_root)))

        tree = _parse_file(py_file, parser)
        if tree is None:
            # Already logged a warning
            continue

        entities = _extract_entities(tree, rel_path)
        file_entity_lists[rel_path] = entities
        all_entities.extend(entities)

        edges = _extract_edges(tree, rel_path, entities, module_map)
        sentinel_edges.extend(edges)

    # --- Phase 3: Upsert all entities ---
    if not all_entities:
        # No parseable entities found; still soft-delete anything previously stored
        entities_soft_deleted = soft_delete_missing(conn, set())
        return AnalysisResult(
            entities_upserted=0,
            edges_upserted=0,
            entities_soft_deleted=entities_soft_deleted,
        )

    upserted_ids = upsert_entities(conn, all_entities)
    entities_upserted = len(upserted_ids)

    # Build a lookup from entity (placeholder) id -> real DB id
    # and from (entity_type, entity_path, entity_name) natural key -> real DB id
    natural_key_to_db_id: dict[tuple[str, str, str], str] = {}
    placeholder_to_db_id: dict[str, str] = {}
    for entity, db_id in zip(all_entities, upserted_ids):
        key = (str(entity.entity_type), entity.entity_path, entity.entity_name)
        natural_key_to_db_id[key] = db_id
        placeholder_to_db_id[entity.id] = db_id

    # Build path -> real_id lookup for sentinel resolution
    # (file entities: entity_path = rel_path, entity_name = basename)
    path_to_file_entity_id: dict[str, str] = {}
    # Build class name -> real_id lookup for extends sentinel resolution
    class_name_to_db_id: dict[str, str] = {}
    for entity, db_id in zip(all_entities, upserted_ids):
        if entity.entity_type == EntityType.FILE:
            path_to_file_entity_id[entity.entity_path] = db_id
        elif entity.entity_type == EntityType.CLASS:
            class_name_to_db_id[entity.entity_name] = db_id

    # --- Phase 4: Resolve and upsert edges ---
    # Also add module → file contains edges
    real_edges: list[EntityEdge] = []

    # Add module → file contains edges
    for py_file in py_files:
        rel_path = normalize_path(str(py_file.relative_to(repo_root)))
        rel_parts = Path(rel_path).parts
        if len(rel_parts) > 1:
            # This file belongs to a package: find the module entity for its directory
            pkg_dir_parts = rel_parts[:-1]
            pkg_path = "/".join(pkg_dir_parts)
            pkg_name = pkg_dir_parts[-1]
            module_key = (str(EntityType.MODULE), pkg_path, pkg_name)
            module_db_id = natural_key_to_db_id.get(module_key)
            file_db_id = path_to_file_entity_id.get(rel_path)
            if module_db_id and file_db_id:
                real_edges.append(
                    EntityEdge(
                        source_id=module_db_id,
                        target_id=file_db_id,
                        relationship=EdgeType.CONTAINS,
                    )
                )

    # Resolve sentinel edges
    seen_edge_keys: set[tuple[str, str, str]] = set()
    for edge in sentinel_edges:
        source_id = placeholder_to_db_id.get(edge.source_id, edge.source_id)
        target_id = edge.target_id

        # Resolve sentinel target IDs
        if target_id.startswith("path:"):
            # Import sentinel: resolve to file entity by path
            target_path = target_id[5:]
            resolved_id = path_to_file_entity_id.get(target_path)
            if resolved_id is None:
                # Path not found in entity graph; skip this edge
                continue
            target_id = resolved_id
        elif target_id.startswith("class:"):
            # Extends sentinel: resolve to class entity by name
            class_name = target_id[6:]
            resolved_id = class_name_to_db_id.get(class_name)
            if resolved_id is None:
                # Class not found in entity graph; skip this edge
                continue
            target_id = resolved_id
        else:
            # Should be a placeholder ID from entity extraction
            resolved_id = placeholder_to_db_id.get(target_id)
            if resolved_id is None:
                continue
            target_id = resolved_id

        # Skip self-edges
        if source_id == target_id:
            continue

        edge_key = (source_id, target_id, str(edge.relationship))
        if edge_key in seen_edge_keys:
            continue
        seen_edge_keys.add(edge_key)

        real_edges.append(
            EntityEdge(
                source_id=source_id,
                target_id=target_id,
                relationship=edge.relationship,
            )
        )

    edges_upserted = 0
    if real_edges:
        # Deduplicate before upserting
        deduped_edges: dict[tuple[str, str, str], EntityEdge] = {}
        for e in real_edges:
            k = (e.source_id, e.target_id, str(e.relationship))
            deduped_edges[k] = e

        edges_upserted = upsert_edges(conn, list(deduped_edges.values()))

    # --- Phase 5: Soft-delete missing entities ---
    found_keys: set[tuple[str, str, str]] = {(str(e.entity_type), e.entity_path, e.entity_name) for e in all_entities}
    entities_soft_deleted = soft_delete_missing(conn, found_keys)

    logger.info(
        "analyze_codebase: %d entities upserted, %d edges upserted, %d soft-deleted",
        entities_upserted,
        edges_upserted,
        entities_soft_deleted,
    )

    return AnalysisResult(
        entities_upserted=entities_upserted,
        edges_upserted=edges_upserted,
        entities_soft_deleted=entities_soft_deleted,
    )
