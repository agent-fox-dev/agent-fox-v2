"""TypeScript and JavaScript language analyzers for the entity graph.

Stub implementations — full extraction logic to be completed in task group 4.

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
"""

from __future__ import annotations

import uuid
from pathlib import Path

from agent_fox.knowledge.entities import Entity, EntityEdge, EntityType


class TypeScriptAnalyzer:
    """Language analyzer for TypeScript source files (.ts, .tsx).

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    @property
    def language_name(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> set[str]:
        return {".ts", ".tsx"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for TypeScript."""
        import tree_sitter_typescript as tsts  # type: ignore[import]
        from tree_sitter import Language, Parser

        return Parser(Language(tsts.language_typescript()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract entities from a TypeScript source file.

        TODO (task group 4): Implement full TypeScript entity extraction.
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
        """Extract edges from a TypeScript source file.

        TODO (task group 4): Implement full TypeScript edge extraction.
        """
        return []

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a TypeScript/ES module map.

        TODO (task group 4): Implement TypeScript module map building.
        """
        return {}


class JavaScriptAnalyzer:
    """Language analyzer for JavaScript source files (.js, .jsx).

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    @property
    def language_name(self) -> str:
        return "javascript"

    @property
    def file_extensions(self) -> set[str]:
        return {".js", ".jsx"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for JavaScript."""
        import tree_sitter_javascript as tsj  # type: ignore[import]
        from tree_sitter import Language, Parser

        return Parser(Language(tsj.language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract entities from a JavaScript source file.

        TODO (task group 4): Implement full JavaScript entity extraction.
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
        """Extract edges from a JavaScript source file.

        TODO (task group 4): Implement full JavaScript edge extraction.
        """
        return []

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a JavaScript/ES module map.

        TODO (task group 4): Implement JavaScript module map building.
        """
        return {}
