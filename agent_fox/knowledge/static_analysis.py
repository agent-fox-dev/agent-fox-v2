"""Tree-sitter static analysis for the entity graph subsystem.

Scans source files, extracts entities (files, modules, classes, functions)
and structural edges (contains, imports, extends), then upserts them into
the entity graph via entity_store.

As of Spec 102, this module dispatches to per-language analyzers registered
in the language registry. The Python analyzer is always available; other
language analyzers are included when their tree-sitter grammar packages are
installed.

Requirements: 95-REQ-4.*, 102-REQ-4.*
"""

from __future__ import annotations

import logging
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
from agent_fox.knowledge.lang.registry import _scan_files, detect_languages

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File parsing helper (kept public for tests that import it directly)
# ---------------------------------------------------------------------------


def _parse_file(file_path: Path, parser) -> object | None:  # type: ignore[return]
    """Parse a source file with tree-sitter.

    Returns the parse Tree, or None if the file cannot be read or contains
    parse errors.

    Requirements: 95-REQ-4.E1, 102-REQ-2.E1
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


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def analyze_codebase(repo_root: Path, conn: duckdb.DuckDBPyConnection) -> AnalysisResult:
    """Scan the codebase at repo_root and populate the entity graph.

    Detects all languages present (via the language registry), parses each
    file with the appropriate tree-sitter analyzer, extracts entities and
    edges, upserts them, and soft-deletes stale entities.

    Returns AnalysisResult with counts and the tuple of analyzed languages.

    Requirements: 95-REQ-4.4, 95-REQ-4.5, 102-REQ-4.1, 102-REQ-4.2,
                  102-REQ-4.3, 102-REQ-4.4, 102-REQ-4.5,
                  102-REQ-4.E1, 102-REQ-4.E2
    """
    if not repo_root.exists() or not repo_root.is_dir():
        raise ValueError(f"repo_root does not exist or is not a directory: {repo_root!r}")

    # --- Detect languages ---
    analyzers = detect_languages(repo_root)

    if not analyzers:
        logger.info("No recognized source files found under %s", repo_root)
        entities_soft_deleted = soft_delete_missing(conn, set())
        return AnalysisResult(
            entities_upserted=0,
            edges_upserted=0,
            entities_soft_deleted=entities_soft_deleted,
            languages_analyzed=(),
        )

    # Collect per-language entity batches and sentinel edges separately so that
    # upsert_entities() can be called with the correct language tag for each batch.
    lang_entity_batches: list[tuple[str, list[Entity]]] = []
    all_sentinel_edges: list[EntityEdge] = []
    analyzed_languages: list[str] = []

    for analyzer in analyzers:
        try:
            lang_entities: list[Entity] = []
            lang_edges: list[EntityEdge] = []
            _analyze_language(
                repo_root=repo_root,
                analyzer=analyzer,
                all_entities=lang_entities,
                sentinel_edges=lang_edges,
            )
            lang_entity_batches.append((analyzer.language_name, lang_entities))
            all_sentinel_edges.extend(lang_edges)
            analyzed_languages.append(analyzer.language_name)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error analyzing %s files: %s; continuing with remaining languages",
                analyzer.language_name,
                exc,
                exc_info=True,
            )

    languages_analyzed = tuple(sorted(analyzed_languages))

    # Flatten entity list (preserving per-language order) for lookup-map construction
    all_entities: list[Entity] = [e for _, batch in lang_entity_batches for e in batch]

    if not all_entities:
        entities_soft_deleted = soft_delete_missing(conn, set())
        return AnalysisResult(
            entities_upserted=0,
            edges_upserted=0,
            entities_soft_deleted=entities_soft_deleted,
            languages_analyzed=languages_analyzed,
        )

    # --- Upsert entities per language (tags each entity with its source language) ---
    all_upserted_ids: list[str] = []
    for lang_name, lang_entities in lang_entity_batches:
        lang_ids = upsert_entities(conn, lang_entities, language=lang_name)
        all_upserted_ids.extend(lang_ids)

    entities_upserted = len(all_upserted_ids)

    # Build lookup maps for sentinel resolution
    natural_key_to_db_id: dict[tuple[str, str, str], str] = {}
    placeholder_to_db_id: dict[str, str] = {}
    path_to_file_entity_id: dict[str, str] = {}
    class_name_to_db_id: dict[str, str] = {}

    for entity, db_id in zip(all_entities, all_upserted_ids):
        key = (str(entity.entity_type), entity.entity_path, entity.entity_name)
        natural_key_to_db_id[key] = db_id
        placeholder_to_db_id[entity.id] = db_id
        if entity.entity_type == EntityType.FILE:
            path_to_file_entity_id[entity.entity_path] = db_id
        elif entity.entity_type == EntityType.CLASS:
            class_name_to_db_id[entity.entity_name] = db_id

    # --- Resolve and collect real edges ---
    real_edges: list[EntityEdge] = []

    # Add module → file contains edges (for Python packages)
    for entity in all_entities:
        if entity.entity_type != EntityType.FILE:
            continue
        rel_parts = Path(entity.entity_path).parts
        if len(rel_parts) > 1:
            pkg_dir_parts = rel_parts[:-1]
            pkg_path = normalize_path("/".join(pkg_dir_parts))
            pkg_name = pkg_dir_parts[-1]
            module_key = (str(EntityType.MODULE), pkg_path, pkg_name)
            module_db_id = natural_key_to_db_id.get(module_key)
            file_db_id = path_to_file_entity_id.get(entity.entity_path)
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
    for edge in all_sentinel_edges:
        source_id = placeholder_to_db_id.get(edge.source_id, edge.source_id)
        target_id = edge.target_id

        if target_id.startswith("path:"):
            target_path = target_id[5:]
            resolved_id = path_to_file_entity_id.get(target_path)
            if resolved_id is None:
                continue
            target_id = resolved_id
        elif target_id.startswith("class:"):
            class_name = target_id[6:]
            resolved_id = class_name_to_db_id.get(class_name)
            if resolved_id is None:
                continue
            target_id = resolved_id
        else:
            resolved_id = placeholder_to_db_id.get(target_id)
            if resolved_id is None:
                continue
            target_id = resolved_id

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

    # --- Upsert edges ---
    edges_upserted = 0
    if real_edges:
        deduped_edges: dict[tuple[str, str, str], EntityEdge] = {}
        for e in real_edges:
            k = (e.source_id, e.target_id, str(e.relationship))
            deduped_edges[k] = e
        edges_upserted = upsert_edges(conn, list(deduped_edges.values()))

    # --- Soft-delete missing entities ---
    found_keys: set[tuple[str, str, str]] = {
        (str(e.entity_type), e.entity_path, e.entity_name) for e in all_entities
    }
    entities_soft_deleted = soft_delete_missing(conn, found_keys)

    logger.info(
        "analyze_codebase: %d entities upserted, %d edges upserted, %d soft-deleted, languages=%s",
        entities_upserted,
        edges_upserted,
        entities_soft_deleted,
        languages_analyzed,
    )

    return AnalysisResult(
        entities_upserted=entities_upserted,
        edges_upserted=edges_upserted,
        entities_soft_deleted=entities_soft_deleted,
        languages_analyzed=languages_analyzed,
    )


# ---------------------------------------------------------------------------
# Per-language analysis helper
# ---------------------------------------------------------------------------


def _analyze_language(
    repo_root: Path,
    analyzer,
    all_entities: list[Entity],
    sentinel_edges: list[EntityEdge],
) -> None:
    """Run entity and edge extraction for a single language analyzer.

    Appends extracted entities and sentinel edges to the provided lists.
    Handles Python module entities specially (from __init__.py packages).

    Requirements: 102-REQ-4.1, 102-REQ-4.2
    """
    files = _scan_files(repo_root, analyzer.file_extensions)
    if not files:
        return

    module_map = analyzer.build_module_map(repo_root, files)
    parser = analyzer.make_parser()

    # For Python: also extract MODULE entities from __init__.py packages
    if analyzer.language_name == "python":
        from agent_fox.knowledge.lang.python_lang import extract_module_entities

        module_entities = extract_module_entities(repo_root, files)
        all_entities.extend(module_entities)

    for source_file in files:
        rel_path = normalize_path(str(source_file.relative_to(repo_root)))
        tree = _parse_file(source_file, parser)
        if tree is None:
            continue

        entities = analyzer.extract_entities(tree, rel_path)
        all_entities.extend(entities)

        edges = analyzer.extract_edges(tree, rel_path, entities, module_map)
        sentinel_edges.extend(edges)


# ---------------------------------------------------------------------------
# Backward-compatible scan helper (kept for any external callers)
# ---------------------------------------------------------------------------


def _scan_python_files(repo_root: Path) -> list[Path]:
    """Return all .py files under repo_root, respecting .gitignore.

    Delegates to the registry's _scan_files. Kept for backward compatibility.

    Requirements: 95-REQ-4.1
    """
    return _scan_files(repo_root, {".py"})


# ---------------------------------------------------------------------------
# Legacy module-level helpers (kept so existing importers don't break)
# ---------------------------------------------------------------------------


def _load_gitignore_spec(repo_root: Path):  # type: ignore[return]
    """Load gitignore patterns (delegates to lang.registry)."""
    from agent_fox.knowledge.lang.registry import _load_gitignore_spec as _impl

    return _impl(repo_root)


def _build_module_map(repo_root: Path, py_files: list[Path]) -> dict[str, str]:
    """Build Python module map (delegates to python_lang)."""
    from agent_fox.knowledge.lang.python_lang import _build_module_map as _impl

    return _impl(repo_root, py_files)


def _file_to_dotted_path(repo_root: Path, py_file: Path) -> str | None:
    """Convert Python file path to dotted import path (delegates to python_lang)."""
    from agent_fox.knowledge.lang.python_lang import _file_to_dotted_path as _impl

    return _impl(repo_root, py_file)


def _make_parser():  # type: ignore[return]
    """Create a tree-sitter Python parser (delegates to PythonAnalyzer)."""
    from agent_fox.knowledge.lang.python_lang import PythonAnalyzer

    return PythonAnalyzer().make_parser()


def _extract_entities(tree, rel_path: str) -> list[Entity]:
    """Extract entities (delegates to python_lang)."""
    from agent_fox.knowledge.lang.python_lang import _extract_entities as _impl

    return _impl(tree, rel_path)


def _extract_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract edges (delegates to python_lang)."""
    from agent_fox.knowledge.lang.python_lang import _extract_edges as _impl

    return _impl(tree, rel_path, entities, module_map)
