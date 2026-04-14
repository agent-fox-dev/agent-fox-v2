"""Ruby language analyzer for the entity graph.

Stub implementation — full extraction logic to be completed in task group 4.

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
"""

from __future__ import annotations

import uuid
from pathlib import Path

from agent_fox.knowledge.entities import Entity, EntityEdge, EntityType


class RubyAnalyzer:
    """Language analyzer for Ruby source files (.rb).

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    @property
    def language_name(self) -> str:
        return "ruby"

    @property
    def file_extensions(self) -> set[str]:
        return {".rb"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Ruby."""
        import tree_sitter_ruby as tsrb  # type: ignore[import]
        from tree_sitter import Language, Parser

        return Parser(Language(tsrb.language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract entities from a Ruby source file.

        TODO (task group 4): Implement full Ruby entity extraction.
        """
        now = "1970-01-01T00:00:00"
        file_name = Path(rel_path).name
        return [
            Entity(
                id=str(uuid.uuid4()),
                entity_type=EntityType.FILE,
                entity_name=file_name,
                entity_path=rel_path,
                created_at=now,
                deleted_at=None,
            )
        ]

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract edges from a Ruby source file.

        TODO (task group 4): Implement full Ruby edge extraction.
        """
        return []

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a Ruby require path map.

        TODO (task group 4): Implement Ruby module map building.
        """
        return {}
