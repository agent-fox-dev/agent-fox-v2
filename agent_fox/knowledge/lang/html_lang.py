"""HTML language analyzer for the entity graph.

Implements LanguageAnalyzer for HTML source files using tree-sitter-html.
HTML is a markup language without OOP constructs, so only FILE entities
and no structural edges are produced.
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.knowledge.entities import Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import ENTITY_EPOCH, make_entity

# Module-level import so the name can be patched in tests.
try:
    from tree_sitter_html import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


class HtmlAnalyzer:
    """Language analyzer for HTML source files (.html, .htm).

    Produces only a FILE entity — HTML has no class or function constructs.
    """

    @property
    def language_name(self) -> str:
        return "html"

    @property
    def file_extensions(self) -> set[str]:
        return {".html", ".htm"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for HTML."""
        if language is None:
            raise ImportError("tree-sitter-html is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract a FILE entity from an HTML file."""
        file_name = Path(rel_path).name
        return [make_entity(EntityType.FILE, file_name, rel_path, now=ENTITY_EPOCH)]

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Return no edges — HTML has no structural edges to extract."""
        return []

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Return an empty module map — HTML imports are not resolved."""
        return {}
