"""CSS language analyzer for the entity graph.

Implements LanguageAnalyzer for CSS source files using tree-sitter-css.
CSS is a styling language without OOP constructs, so only FILE entities
are produced. IMPORTS edges are generated for @import statements when the
imported file is resolvable within the repo.
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import ENTITY_EPOCH, make_entity, node_text

# Module-level import so the name can be patched in tests.
try:
    from tree_sitter_css import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


class CssAnalyzer:
    """Language analyzer for CSS source files (.css).

    Produces a FILE entity and IMPORTS edges for @import statements that
    resolve to other CSS files in the same repository.
    """

    @property
    def language_name(self) -> str:
        return "css"

    @property
    def file_extensions(self) -> set[str]:
        return {".css"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for CSS."""
        if language is None:
            raise ImportError("tree-sitter-css is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract a FILE entity from a CSS file."""
        file_name = Path(rel_path).name
        return [make_entity(EntityType.FILE, file_name, rel_path, now=ENTITY_EPOCH)]

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract IMPORTS edges from @import statements.

        Only imports that resolve to a file in module_map produce an edge;
        external URLs and unresolvable paths are silently skipped.
        """
        edges: list[EntityEdge] = []
        file_name = Path(rel_path).name
        file_entity = next((e for e in entities if e.entity_name == file_name), None)
        if file_entity is None:
            return edges

        for child in tree.root_node.children:
            if child.type == "import_statement":
                import_path = _extract_css_import_path(child)
                if import_path is None:
                    continue
                target_path = module_map.get(import_path)
                if target_path is not None:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=f"path:{target_path}",
                            relationship=EdgeType.IMPORTS,
                        )
                    )

        return edges

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a mapping from CSS import path strings to repo-relative file paths.

        Maps both the full repo-relative path and the file name alone so that
        both ``@import "base.css"`` and ``@import "styles/base.css"`` can resolve.
        """
        module_map: dict[str, str] = {}
        for css_file in files:
            try:
                rel_path = str(css_file.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                continue
            module_map[rel_path] = rel_path
            module_map[css_file.name] = rel_path
        return module_map


# ---------------------------------------------------------------------------
# CSS import path extraction helpers
# ---------------------------------------------------------------------------


def _extract_css_import_path(import_node) -> str | None:
    """Extract the import path string from an @import statement node.

    Handles both:
    - ``@import "base.css";``  → string_value node
    - ``@import url("base.css");``  → call_expression → arguments → string_value

    Returns None if the path cannot be determined or is a URL.
    """
    for child in import_node.children:
        if child.type == "string_value":
            return _unwrap_string_value(child)
        if child.type == "call_expression":
            # url("...") form
            for sub in child.children:
                if sub.type == "arguments":
                    for arg in sub.children:
                        if arg.type == "string_value":
                            return _unwrap_string_value(arg)
    return None


def _unwrap_string_value(string_value_node) -> str | None:
    """Extract the inner text from a string_value node (strips surrounding quotes)."""
    text = node_text(string_value_node)
    if text is None or len(text) < 2:
        return None
    # Strip surrounding single or double quotes
    inner = text[1:-1]
    # Skip external URLs (http://, https://, //)
    if inner.startswith(("http://", "https://", "//")):
        return None
    return inner if inner else None
