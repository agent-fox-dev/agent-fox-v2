"""C and C++ language analyzers for the entity graph.

Stub implementations — full extraction logic to be completed in task group 4.

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3, 102-REQ-3.E1
"""

from __future__ import annotations

import uuid
from pathlib import Path

from agent_fox.knowledge.entities import Entity, EntityEdge, EntityType


class CAnalyzer:
    """Language analyzer for C source and header files (.c, .h).

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.E1
    """

    @property
    def language_name(self) -> str:
        return "c"

    @property
    def file_extensions(self) -> set[str]:
        return {".c", ".h"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for C."""
        import tree_sitter_c as tsc  # type: ignore[import]
        from tree_sitter import Language, Parser

        return Parser(Language(tsc.language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract entities from a C source file.

        TODO (task group 4): Implement full C entity extraction.
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
        """Extract edges from a C source file.

        TODO (task group 4): Implement full C edge extraction.
        """
        return []

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a C header include path map.

        TODO (task group 4): Implement C module map building.
        """
        return {}


class CppAnalyzer:
    """Language analyzer for C++ source and header files (.cpp, .hpp, .cc, .cxx, .hh).

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    @property
    def language_name(self) -> str:
        return "cpp"

    @property
    def file_extensions(self) -> set[str]:
        return {".cpp", ".hpp", ".cc", ".cxx", ".hh"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for C++."""
        import tree_sitter_cpp as tscpp  # type: ignore[import]
        from tree_sitter import Language, Parser

        return Parser(Language(tscpp.language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract entities from a C++ source file.

        TODO (task group 4): Implement full C++ entity extraction.
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
        """Extract edges from a C++ source file.

        TODO (task group 4): Implement full C++ edge extraction.
        """
        return []

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a C++ header include path map.

        TODO (task group 4): Implement C++ module map building.
        """
        return {}
