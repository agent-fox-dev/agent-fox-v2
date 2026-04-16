"""Regex language analyzer for the entity graph.

Implements LanguageAnalyzer for regex pattern files using tree-sitter-regex.
Regex files contain patterns without class or function constructs, so only
FILE entities are produced.
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.knowledge.entities import Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import ENTITY_EPOCH, make_entity

# Module-level import so the name can be patched in tests.
try:
    from tree_sitter_regex import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


class RegexAnalyzer:
    """Language analyzer for regex pattern files (.regex).

    Produces only a FILE entity — regex patterns have no class or function
    constructs that map to graph entities.
    """

    @property
    def language_name(self) -> str:
        return "regex"

    @property
    def file_extensions(self) -> set[str]:
        return {".regex"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for regex patterns."""
        if language is None:
            raise ImportError("tree-sitter-regex is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract a FILE entity from a regex file."""
        file_name = Path(rel_path).name
        return [make_entity(EntityType.FILE, file_name, rel_path, now=ENTITY_EPOCH)]

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Return no edges — regex files have no structural edges to extract."""
        return []

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Return an empty module map — regex files have no import mechanism."""
        return {}
