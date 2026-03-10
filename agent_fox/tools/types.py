"""Core data types for fox tools."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HashedLine:
    """A single line with its number and content hash."""

    line_number: int  # 1-based
    content: str
    hash: str  # 16-char hex


@dataclass(frozen=True)
class Symbol:
    """A structural declaration found by the heuristic parser."""

    kind: str  # "function" | "class" | "method" | "constant" | "import_block"
    name: str  # declaration name, or "(N imports)" for import blocks
    start_line: int  # 1-based inclusive
    end_line: int  # 1-based inclusive


@dataclass(frozen=True)
class OutlineResult:
    """Result of fox_outline."""

    symbols: list[Symbol]
    total_lines: int


@dataclass(frozen=True)
class ReadResult:
    """Result of fox_read."""

    lines: list[HashedLine]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EditOperation:
    """A single edit within a batch."""

    start_line: int  # 1-based inclusive
    end_line: int  # 1-based inclusive
    hashes: list[str]  # one hash per line in [start, end]
    new_content: str  # replacement text (empty = delete)


@dataclass(frozen=True)
class EditResult:
    """Result of fox_edit."""

    success: bool
    lines_changed: int
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchMatch:
    """A search match with surrounding context."""

    lines: list[HashedLine]
    match_line_numbers: list[int]  # which lines in `lines` matched


@dataclass(frozen=True)
class SearchResult:
    """Result of fox_search."""

    matches: list[SearchMatch]
    total_matches: int
