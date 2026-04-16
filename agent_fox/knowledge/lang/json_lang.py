"""JSON language analyzer for the entity graph.

Implements LanguageAnalyzer for JSON files using tree-sitter-json.
JSON is a data serialization format, not a programming language — only FILE
entities are extracted and no edges or module maps are produced.

Requirements: 102-REQ-2.1
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.knowledge.entities import Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import ENTITY_EPOCH, make_entity

# Module-level import so the name can be patched in tests.
try:
    from tree_sitter_json import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# JsonAnalyzer
# ---------------------------------------------------------------------------


class JsonAnalyzer:
    """Language analyzer for JSON files (.json).

    Only FILE entities are extracted.  JSON has no functions, classes, or
    importable modules, so extract_edges and build_module_map return empty
    collections.

    Requirements: 102-REQ-2.1
    """

    @property
    def language_name(self) -> str:
        return "json"

    @property
    def file_extensions(self) -> set[str]:
        return {".json"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for JSON."""
        if language is None:
            raise ImportError("tree-sitter-json is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract a single FILE entity from a parsed JSON tree."""
        now = ENTITY_EPOCH
        file_name = Path(rel_path).name
        return [make_entity(EntityType.FILE, file_name, rel_path, now=now)]

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Return empty list — JSON files have no structural edges to extract."""
        return []

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Return empty dict — JSON has no importable module system."""
        return {}
