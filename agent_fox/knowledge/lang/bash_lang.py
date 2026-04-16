"""Bash language analyzer for the entity graph.

Implements LanguageAnalyzer for Bash source files using tree-sitter-bash.

Tree-sitter Bash grammar notes (tree-sitter-bash):
- ``function_definition`` covers both ``function name() { ... }`` and
  ``name() { ... }`` styles. The first ``word`` child is the function name.
- ``command`` nodes whose ``command_name`` child text is ``source`` or ``.``
  (dot) indicate a source/include command. The first non-name ``word``
  argument is the sourced file path.
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import ENTITY_EPOCH, make_entity, node_text

# Module-level import so the name can be patched in tests.
try:
    from tree_sitter_bash import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# BashAnalyzer
# ---------------------------------------------------------------------------


class BashAnalyzer:
    """Language analyzer for Bash source files (.sh, .bash).

    Extracts FILE and FUNCTION entities from function definitions.
    Produces CONTAINS edges (file → function) and IMPORTS edges for
    ``source``/``.`` (dot) commands that resolve to other files in the repo.
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
        """Extract FILE and FUNCTION entities from a Bash script."""
        return _extract_bash_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS and IMPORTS edges from a Bash script."""
        return _extract_bash_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a mapping from source-command paths to repo-relative file paths.

        Maps the repo-relative path and bare filename so both
        ``source utils.sh`` and ``source ./utils.sh`` can be resolved.
        """
        return _build_bash_module_map(repo_root, files)


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------


def _extract_bash_entities(tree, rel_path: str) -> list[Entity]:
    """Extract FILE and FUNCTION entities from a parsed Bash tree."""
    now = ENTITY_EPOCH
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    entities.append(make_entity(EntityType.FILE, file_name, rel_path, now=now))

    for child in tree.root_node.children:
        if child.type == "function_definition":
            func_name = _get_function_name(child)
            if func_name:
                entities.append(make_entity(EntityType.FUNCTION, func_name, rel_path, now=now))

    return entities


def _get_function_name(function_def_node) -> str | None:
    """Extract the function name from a function_definition node.

    Both ``function name() { ... }`` and ``name() { ... }`` styles have the
    function name in the first ``word`` child (the ``function`` keyword is a
    separate child of type "function" when present).
    """
    for child in function_def_node.children:
        if child.type == "word":
            return node_text(child)
    return None


# ---------------------------------------------------------------------------
# Edge extraction
# ---------------------------------------------------------------------------


def _extract_bash_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS and IMPORTS edges from a parsed Bash tree."""
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name
    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}

    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    for child in tree.root_node.children:
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

        elif child.type == "command":
            import_path = _extract_source_path(child)
            if import_path is not None:
                # Try to resolve against module_map; also try stripping leading "./"
                target_path = module_map.get(import_path)
                if target_path is None and import_path.startswith("./"):
                    target_path = module_map.get(import_path[2:])
                if target_path is not None:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=f"path:{target_path}",
                            relationship=EdgeType.IMPORTS,
                        )
                    )

    return edges


def _extract_source_path(command_node) -> str | None:
    """Extract the sourced file path from a ``source`` or ``.`` command node.

    Returns the raw path string, or None if this is not a source command.
    """
    children = command_node.children
    if not children:
        return None

    command_name_node = children[0]
    if command_name_node.type != "command_name":
        return None

    # The command_name child is a word node (or wraps one)
    cmd_text: str | None = None
    if command_name_node.text:
        cmd_text = command_name_node.text.decode("utf-8")
    else:
        for sub in command_name_node.children:
            if sub.type == "word":
                cmd_text = node_text(sub)
                break

    if cmd_text not in ("source", "."):
        return None

    # The first argument after the command name is the sourced path.
    for child in children[1:]:
        if child.type == "word":
            return node_text(child)

    return None


# ---------------------------------------------------------------------------
# Module map construction
# ---------------------------------------------------------------------------


def _build_bash_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a mapping from source-command path strings to repo-relative paths.

    Maps both the full repo-relative path (``scripts/utils.sh``) and the bare
    filename (``utils.sh``), allowing both ``source utils.sh`` and
    ``source scripts/utils.sh`` to resolve.
    """
    module_map: dict[str, str] = {}
    for sh_file in files:
        try:
            rel_path = str(sh_file.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue
        module_map[rel_path] = rel_path
        module_map[sh_file.name] = rel_path
    return module_map
