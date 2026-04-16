"""Bash language analyzer for the entity graph.

Implements LanguageAnalyzer for Bash source files using tree-sitter-bash.
Extracts FILE and FUNCTION entities; no class hierarchy or import resolution
applies to shell scripts.

Requirements: 102-REQ-2.1, 102-REQ-3.1
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import ENTITY_EPOCH, make_entity

# Module-level import so the name can be patched in tests.
# The try/except allows the module to be imported even when tree-sitter-bash
# is not installed; make_parser() raises ImportError in that case.
try:
    from tree_sitter_bash import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# BashAnalyzer
# ---------------------------------------------------------------------------


class BashAnalyzer:
    """Language analyzer for Bash source files (.sh, .bash).

    Extracts FILE and FUNCTION entities.  Shell scripts do not have classes,
    modules, or resolvable imports, so extract_edges produces only
    file→function CONTAINS edges and build_module_map returns an empty dict.

    Requirements: 102-REQ-2.1, 102-REQ-3.1
    """

    @property
    def language_name(self) -> str:
        return "bash"

    @property
    def file_extensions(self) -> set[str]:
        return {".sh", ".bash"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Bash."""
        if language is None:
            raise ImportError("tree-sitter-bash is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE and FUNCTION entities from a parsed Bash tree."""
        return _extract_bash_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS edges (file → function) from a parsed Bash tree."""
        return _extract_bash_edges(tree, rel_path, entities)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Return empty dict — Bash has no importable module system."""
        return {}


# ---------------------------------------------------------------------------
# Bash entity extraction
# ---------------------------------------------------------------------------


def _extract_bash_entities(tree, rel_path: str) -> list[Entity]:
    """Extract FILE and FUNCTION entities from a parsed Bash source tree."""
    now = ENTITY_EPOCH
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    # FILE entity — always present.
    entities.append(make_entity(EntityType.FILE, file_name, rel_path, now=now))

    root = tree.root_node
    for child in root.children:
        if child.type == "function_definition":
            func_name = _get_function_name(child)
            if func_name:
                entities.append(make_entity(EntityType.FUNCTION, func_name, rel_path, now=now))

    return entities


def _get_function_name(function_def_node) -> str | None:
    """Extract the function name from a Bash function_definition node.

    Bash function definitions have two forms:
    - ``function greet() { ... }`` → children: [function, word, (, ), compound_statement]
    - ``greet() { ... }``          → children: [word, (, ), compound_statement]

    In both cases the function name is the first ``word`` child.
    """
    for child in function_def_node.children:
        if child.type == "word":
            return child.text.decode("utf-8") if child.text else None
    return None


# ---------------------------------------------------------------------------
# Bash edge extraction
# ---------------------------------------------------------------------------


def _extract_bash_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
) -> list[EntityEdge]:
    """Extract CONTAINS edges (file → function) from a parsed Bash source tree."""
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name

    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}
    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node
    for child in root.children:
        if child.type == "function_definition":
            func_name = _get_function_name(child)
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
