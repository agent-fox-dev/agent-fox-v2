"""Elixir language analyzer for the entity graph.

Implements LanguageAnalyzer for Elixir source files using tree-sitter-elixir.

Tree-sitter Elixir grammar notes:
- Keywords like defmodule, def, defp, use, import, alias, require are
  represented as `call` nodes whose first child is an `identifier` with
  the keyword text.
- Module names (e.g. MyApp.Accounts.User) are `alias` nodes.
- The `do_block` is a direct child of the `call` node, separate from the
  `arguments` node.
- `child_by_field_name("target")` works for the first identifier of a call.

Requirements: 107-REQ-2.1, 107-REQ-2.2, 107-REQ-2.3, 107-REQ-2.4,
              107-REQ-2.5, 107-REQ-2.6
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import (
    ENTITY_EPOCH,
    make_entity,
    node_text,
)

# Module-level import so the name can be patched in tests (TS-107-E9).
try:
    from tree_sitter_elixir import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]

# Elixir macro calls that produce IMPORTS edges.
_IMPORT_MACROS = frozenset({"use", "import", "alias", "require"})


# ---------------------------------------------------------------------------
# ElixirAnalyzer
# ---------------------------------------------------------------------------


class ElixirAnalyzer:
    """Language analyzer for Elixir source files (.ex, .exs).

    Extracts FILE, MODULE (defmodule), and FUNCTION (def/defp) entities.
    Never produces CLASS entities or EXTENDS edges.
    Produces CONTAINS and IMPORTS edges.

    Requirements: 107-REQ-2.1 through 107-REQ-2.6
    """

    @property
    def language_name(self) -> str:
        return "elixir"

    @property
    def file_extensions(self) -> set[str]:
        return {".ex", ".exs"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Elixir."""
        if language is None:
            raise ImportError("tree-sitter-elixir is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, MODULE, and FUNCTION entities from an Elixir tree."""
        return _extract_elixir_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS and IMPORTS edges from an Elixir tree.

        Never produces EXTENDS edges (Elixir has no inheritance).

        Requirements: 107-REQ-2.5
        """
        return _extract_elixir_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build an Elixir module name → repo-relative file path mapping.

        Requirements: 107-REQ-2.6
        """
        return _build_elixir_module_map(repo_root, files)


# ---------------------------------------------------------------------------
# Tree navigation helpers
# ---------------------------------------------------------------------------


def _call_target_name(call_node) -> str | None:
    """Get the function name (target) from a call node.

    For Elixir's tree-sitter grammar, `child_by_field_name("target")`
    returns the first identifier child (e.g. "defmodule", "def", "use").
    Falls back to iterating children when the field is not available.
    """
    target = call_node.child_by_field_name("target")
    if target is not None and target.type == "identifier":
        return node_text(target)
    # Fallback: first identifier child.
    for child in call_node.children:
        if child.type == "identifier":
            return node_text(child)
    return None


def _get_arguments(call_node):
    """Get the arguments node from a call node (direct child of type 'arguments')."""
    for child in call_node.children:
        if child.type == "arguments":
            return child
    return None


def _get_do_block(call_node):
    """Get the do_block from a call node (direct child of type 'do_block')."""
    for child in call_node.children:
        if child.type == "do_block":
            return child
    return None


def _defmodule_name(call_node) -> str | None:
    """Extract the module name (alias text) from a defmodule call node."""
    args = _get_arguments(call_node)
    if args is None:
        return None
    for child in args.children:
        if child.type == "alias":
            return node_text(child)
    return None


def _def_name(call_node) -> str | None:
    """Extract the function name from a def/defp call node.

    Two forms:
      - def simple_func, do: expr  → identifier "simple_func" directly in args
      - def func(x) [do:] expr     → inner call node with identifier "func"
    """
    args = _get_arguments(call_node)
    if args is None:
        return None
    for child in args.children:
        if child.type == "identifier":
            # Simple form: def hello, do: :ok
            return node_text(child)
        if child.type == "call":
            # Form with arguments: def hello(x) do ... end
            inner_target = child.child_by_field_name("target")
            if inner_target is not None and inner_target.type == "identifier":
                return node_text(inner_target)
            # Fallback: first identifier child of the inner call.
            for cc in child.children:
                if cc.type == "identifier":
                    return node_text(cc)
    return None


def _get_import_alias(call_node) -> str | None:
    """Extract the module name from a use/import/alias/require call node."""
    args = _get_arguments(call_node)
    if args is None:
        return None
    for child in args.children:
        if child.type == "alias":
            return node_text(child)
    return None


# ---------------------------------------------------------------------------
# Elixir entity extraction
# ---------------------------------------------------------------------------


def _extract_elixir_entities(tree, rel_path: str) -> list[Entity]:
    """Extract all entities from a parsed Elixir source tree.

    Requirements: 107-REQ-2.3, 107-REQ-2.4, 107-REQ-2.E1
    """
    now = ENTITY_EPOCH
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    # FILE entity — always present.
    entities.append(make_entity(EntityType.FILE, file_name, rel_path, now=now))

    # Walk the tree collecting MODULE and FUNCTION entities.
    _walk_entities(tree.root_node, rel_path, entities, now, parent_module=None)

    return entities


def _walk_entities(
    node,
    rel_path: str,
    entities: list[Entity],
    now: str,
    parent_module: str | None,
) -> None:
    """Recursively collect MODULE and FUNCTION entities.

    - For `defmodule` calls: create MODULE entity and recurse into do_block
      with updated parent_module context (handles nested defmodule, REQ-2.E1).
    - For `def`/`defp` calls: create FUNCTION entity with qualified name;
      do NOT recurse into the function body.
    - For all other nodes: recurse into children.

    Never creates CLASS entities (REQ-2.4).
    """
    for child in node.children:
        if child.type == "call":
            target = _call_target_name(child)

            if target == "defmodule":
                mod_name = _defmodule_name(child)
                if mod_name:
                    full_name = f"{parent_module}.{mod_name}" if parent_module else mod_name
                    entities.append(make_entity(EntityType.MODULE, full_name, rel_path, now=now))
                    # Recurse into the do_block body with updated module context.
                    do_block = _get_do_block(child)
                    if do_block:
                        _walk_entities(do_block, rel_path, entities, now, parent_module=full_name)

            elif target in ("def", "defp"):
                fname = _def_name(child)
                if fname and parent_module:
                    qualified = f"{parent_module}.{fname}"
                    entities.append(make_entity(EntityType.FUNCTION, qualified, rel_path, now=now))
                # Do NOT recurse into the def/defp body.

            # Other calls (use, import, alias, require, Enum.map, etc.): skip.

        else:
            # Non-call node (do_block, arguments, source, tokens, …): recurse.
            _walk_entities(child, rel_path, entities, now, parent_module)


# ---------------------------------------------------------------------------
# Elixir edge extraction
# ---------------------------------------------------------------------------


def _extract_elixir_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS and IMPORTS edges from a parsed Elixir source tree.

    - CONTAINS: file→module, module→function, parent_module→nested_module.
    - IMPORTS: use/import/alias/require resolved via module_map; external
      references are silently skipped (REQ-2.E2).
    - Never produces EXTENDS edges (REQ-2.4).

    Requirements: 107-REQ-2.5, 107-REQ-2.E2
    """
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name
    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}

    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    _walk_edges(
        tree.root_node,
        edges,
        entity_by_name,
        file_entity,
        module_map,
        parent_module=None,
    )

    return edges


def _walk_edges(
    node,
    edges: list[EntityEdge],
    entity_by_name: dict[str, Entity],
    file_entity: Entity,
    module_map: dict[str, str],
    parent_module: str | None,
) -> None:
    """Recursively collect edges from an Elixir AST node."""
    for child in node.children:
        if child.type == "call":
            target = _call_target_name(child)

            if target == "defmodule":
                mod_name = _defmodule_name(child)
                if mod_name:
                    full_name = f"{parent_module}.{mod_name}" if parent_module else mod_name
                    mod_entity = entity_by_name.get(full_name)

                    if mod_entity:
                        # CONTAINS: file → top-level module.
                        if parent_module is None:
                            edges.append(
                                EntityEdge(
                                    source_id=file_entity.id,
                                    target_id=mod_entity.id,
                                    relationship=EdgeType.CONTAINS,
                                )
                            )
                        else:
                            # CONTAINS: parent module → nested module.
                            parent_entity = entity_by_name.get(parent_module)
                            if parent_entity:
                                edges.append(
                                    EntityEdge(
                                        source_id=parent_entity.id,
                                        target_id=mod_entity.id,
                                        relationship=EdgeType.CONTAINS,
                                    )
                                )

                    # Recurse into do_block with updated module context.
                    do_block = _get_do_block(child)
                    if do_block:
                        _walk_edges(do_block, edges, entity_by_name, file_entity, module_map, parent_module=full_name)

            elif target in ("def", "defp"):
                fname = _def_name(child)
                if fname and parent_module:
                    qualified = f"{parent_module}.{fname}"
                    func_entity = entity_by_name.get(qualified)
                    parent_entity = entity_by_name.get(parent_module)
                    if func_entity and parent_entity:
                        # CONTAINS: module → function.
                        edges.append(
                            EntityEdge(
                                source_id=parent_entity.id,
                                target_id=func_entity.id,
                                relationship=EdgeType.CONTAINS,
                            )
                        )
                # Do NOT recurse into def/defp body.

            elif target in _IMPORT_MACROS:
                # IMPORTS edges for use/import/alias/require.
                # Only emit if we're inside a module (parent_module is set).
                if parent_module is not None:
                    imported_name = _get_import_alias(child)
                    if imported_name:
                        target_path = module_map.get(imported_name)
                        if target_path is not None:
                            edges.append(
                                EntityEdge(
                                    source_id=file_entity.id,
                                    target_id=f"path:{target_path}",
                                    relationship=EdgeType.IMPORTS,
                                )
                            )
                        # If not in module_map → external dep → skip silently (REQ-2.E2).

            # Other calls: do nothing (don't recurse into function bodies).

        else:
            # Non-call node: recurse (handles do_block, source, body tokens, …).
            _walk_edges(child, edges, entity_by_name, file_entity, module_map, parent_module)


# ---------------------------------------------------------------------------
# Elixir module map construction
# ---------------------------------------------------------------------------

_EX_DEFMODULE_RE = re.compile(r"\bdefmodule\s+([\w.]+)\s+do\b", re.MULTILINE)


def _build_elixir_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a mapping from Elixir module names to repo-relative file paths.

    Maps "MyApp.Accounts.User" → "lib/my_app/accounts/user.ex".
    All values are POSIX-style repo-relative paths (no backslashes, no leading /).

    Requirements: 107-REQ-2.6
    """
    module_map: dict[str, str] = {}
    for ex_file in files:
        try:
            content = ex_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel_path = str(ex_file.relative_to(repo_root)).replace("\\", "/")

        for match in _EX_DEFMODULE_RE.finditer(content):
            module_name = match.group(1)
            module_map[module_name] = rel_path

    return module_map
