"""File-only language analyzers.

Provides a base class for languages that produce only a FILE entity
with no structural edges (e.g., HTML, JSON, regex). Concrete analyzers
are defined via class-level configuration — no method overrides needed.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from agent_fox.knowledge.entities import Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import ENTITY_EPOCH, make_entity


class SimpleAnalyzer:
    """Base analyzer for languages with no class/function constructs.

    Subclasses set three class attributes:
    - ``_language_name``: e.g. ``"html"``
    - ``_file_extensions``: e.g. ``{".html", ".htm"}``
    - ``_grammar_module``: e.g. ``"tree_sitter_html"``
    """

    _language_name: str
    _file_extensions: set[str]
    _grammar_module: str

    @property
    def language_name(self) -> str:
        return self._language_name

    @property
    def file_extensions(self) -> set[str]:
        return self._file_extensions

    def make_parser(self):  # type: ignore[return]
        mod = importlib.import_module(self._grammar_module)
        from tree_sitter import Language, Parser

        return Parser(Language(mod.language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        file_name = Path(rel_path).name
        return [make_entity(EntityType.FILE, file_name, rel_path, now=ENTITY_EPOCH)]

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        return []

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        return {}


class HtmlAnalyzer(SimpleAnalyzer):
    _language_name = "html"
    _file_extensions = {".html", ".htm"}
    _grammar_module = "tree_sitter_html"


class JsonAnalyzer(SimpleAnalyzer):
    _language_name = "json"
    _file_extensions = {".json"}
    _grammar_module = "tree_sitter_json"


class RegexAnalyzer(SimpleAnalyzer):
    _language_name = "regex"
    _file_extensions = {".regex"}
    _grammar_module = "tree_sitter_regex"
