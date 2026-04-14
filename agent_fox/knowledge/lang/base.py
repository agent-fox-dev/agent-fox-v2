"""LanguageAnalyzer protocol definition.

Requirements: 102-REQ-1.1
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from agent_fox.knowledge.entities import Entity, EntityEdge


@runtime_checkable
class LanguageAnalyzer(Protocol):
    """Protocol for language-specific entity and edge extractors.

    Every concrete analyzer must implement this protocol to be registered
    in the language registry and used by analyze_codebase().

    Requirements: 102-REQ-1.1
    """

    @property
    def language_name(self) -> str:
        """Unique human-readable name for this language (e.g. 'python', 'go')."""
        ...

    @property
    def file_extensions(self) -> set[str]:
        """Set of file extensions handled by this analyzer (e.g. {'.py', '.pyi'})."""
        ...

    def make_parser(self):  # type: ignore[return]
        """Create and return a tree-sitter Parser configured for this language.

        Raises ImportError if the grammar package is not installed.
        """
        ...

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract entity objects from a parsed tree-sitter tree.

        Args:
            tree: A tree-sitter Tree object (result of Parser.parse()).
            rel_path: Repo-relative path of the source file (POSIX slashes).

        Returns:
            List of Entity objects extracted from the file.
        """
        ...

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract structural edges from a parsed tree-sitter tree.

        Args:
            tree: A tree-sitter Tree object.
            rel_path: Repo-relative path of the source file.
            entities: Entities extracted from the same file by extract_entities().
            module_map: Language-specific mapping from import identifiers to
                repo-relative file paths (used for import resolution).

        Returns:
            List of EntityEdge objects. source_id and target_id may be
            placeholder or sentinel IDs that the caller resolves to real UUIDs.
        """
        ...

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a language-specific module map for import resolution.

        Args:
            repo_root: Absolute path to the repository root.
            files: All source files of this language found in the repo.

        Returns:
            Dict mapping import identifiers to repo-relative file paths.
        """
        ...
