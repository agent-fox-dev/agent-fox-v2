"""MCP server exposing fox tools over stdio transport.

Wraps the core fox tool functions as MCP tools using the ``mcp`` Python SDK.
The server validates file paths against an optional ``allowed_dirs`` list
before delegating to the core library functions.

Requirements: 29-REQ-7.1, 29-REQ-7.2, 29-REQ-7.4,
              29-REQ-7.E1, 29-REQ-7.E2
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import types as mcp_types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from agent_fox.tools.edit import fox_edit
from agent_fox.tools.outline import fox_outline
from agent_fox.tools.read import fox_read
from agent_fox.tools.search import fox_search
from agent_fox.tools.types import (
    EditOperation,
    EditResult,
    OutlineResult,
    ReadResult,
    SearchResult,
)

_FILE_PATH_PROP: dict[str, str] = {
    "type": "string",
    "description": "Absolute path to the file",
}


def _resolve_path(file_path: str) -> str:
    """Resolve a file path to its absolute, real form."""
    return str(Path(file_path).resolve())


def _check_allowed(
    file_path: str,
    allowed_dirs: list[str] | None,
) -> str | None:
    """Check if file_path is within allowed_dirs.

    Returns an error string if not allowed, None otherwise.
    """
    if allowed_dirs is None:
        return None
    resolved = _resolve_path(file_path)
    for d in allowed_dirs:
        allowed_resolved = str(Path(d).resolve())
        if resolved == allowed_resolved or resolved.startswith(
            allowed_resolved + os.sep
        ):
            return None
    return f"Error: path '{file_path}' is outside allowed directories"


def _result_to_text(result: Any) -> str:
    """Convert a core tool result to a text string for MCP."""
    if isinstance(result, str):
        return result
    if isinstance(result, OutlineResult):
        lines = []
        for sym in result.symbols:
            lines.append(f"{sym.start_line}-{sym.end_line}: {sym.kind} {sym.name}")
        lines.append(
            f"--- {len(result.symbols)} symbols, {result.total_lines} lines ---"
        )
        return "\n".join(lines)
    if isinstance(result, ReadResult):
        lines = []
        for hl in result.lines:
            content = hl.content.rstrip("\n")
            lines.append(f"{hl.line_number}|{hl.hash}|{content}")
        for w in result.warnings:
            lines.append(f"WARNING: {w}")
        return "\n".join(lines)
    if isinstance(result, EditResult):
        if result.success:
            return f"OK: {result.lines_changed} lines changed"
        return "FAILED:\n" + "\n".join(result.errors)
    if isinstance(result, SearchResult):
        lines = []
        for match in result.matches:
            for hl in match.lines:
                content = hl.content.rstrip("\n")
                marker = " *" if hl.line_number in match.match_line_numbers else ""
                lines.append(f"{hl.line_number}|{hl.hash}|{content}{marker}")
            lines.append("---")
        lines.append(f"Total matches: {result.total_matches}")
        return "\n".join(lines)
    return str(result)


# -------------------------------------------------------------------
# Tool metadata (matches registry.py schemas)
# -------------------------------------------------------------------

_TOOLS = [
    mcp_types.Tool(
        name="fox_outline",
        description=(
            "Return a structural outline of a file showing "
            "functions, classes, and other declarations "
            "with line numbers."
        ),
        inputSchema={
            "type": "object",
            "properties": {"file_path": _FILE_PATH_PROP},
            "required": ["file_path"],
        },
    ),
    mcp_types.Tool(
        name="fox_read",
        description=(
            "Read specific line ranges from a file with "
            "content hashes for subsequent edit operations."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": _FILE_PATH_PROP,
                "ranges": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "description": (
                        "List of [start, end] line ranges (1-based, inclusive)"
                    ),
                },
            },
            "required": ["file_path", "ranges"],
        },
    ),
    mcp_types.Tool(
        name="fox_edit",
        description=(
            "Apply hash-verified edits to a file. Verifies "
            "content hashes before writing to prevent "
            "stale-read edits."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": _FILE_PATH_PROP,
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "start_line": {"type": "integer"},
                            "end_line": {"type": "integer"},
                            "hashes": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "new_content": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "start_line",
                            "end_line",
                            "hashes",
                            "new_content",
                        ],
                    },
                },
            },
            "required": ["file_path", "edits"],
        },
    ),
    mcp_types.Tool(
        name="fox_search",
        description=(
            "Search a file by regex pattern and return "
            "matching lines with context and content hashes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": _FILE_PATH_PROP,
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "context": {
                    "type": "integer",
                    "default": 0,
                    "description": ("Context lines before/after each match"),
                },
            },
            "required": ["file_path", "pattern"],
        },
    ),
]


def _dispatch_tool(
    name: str,
    arguments: dict[str, Any],
    allowed_dirs: list[str] | None,
) -> str:
    """Dispatch a tool call to the core function."""
    file_path = arguments.get("file_path", "")

    path_err = _check_allowed(file_path, allowed_dirs)
    if path_err is not None:
        return path_err

    if name == "fox_outline":
        result = fox_outline(file_path=file_path)
    elif name == "fox_read":
        ranges = [tuple(r) for r in arguments["ranges"]]
        result = fox_read(file_path=file_path, ranges=ranges)
    elif name == "fox_edit":
        edits = [
            EditOperation(
                start_line=e["start_line"],
                end_line=e["end_line"],
                hashes=e["hashes"],
                new_content=e["new_content"],
            )
            for e in arguments["edits"]
        ]
        result = fox_edit(file_path=file_path, edits=edits)
    elif name == "fox_search":
        result = fox_search(
            file_path=file_path,
            pattern=arguments["pattern"],
            context=arguments.get("context", 0),
        )
    else:
        return f"Error: unknown tool '{name}'"

    return _result_to_text(result)


# -------------------------------------------------------------------
# FoxMCPServer — MCP protocol + test-friendly synchronous API
# -------------------------------------------------------------------


@dataclass
class ToolInfo:
    """Lightweight tool descriptor for list_tools()."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class FoxMCPServer:
    """Wrapper around the MCP Server that exposes fox tools.

    Provides a test-friendly synchronous API (``list_tools``,
    ``call_tool``) as well as an ``mcp_server`` attribute for
    running over stdio.
    """

    allowed_dirs: list[str] | None = None
    mcp_server: Server = field(init=False)

    def __post_init__(self) -> None:
        self.mcp_server = self._build_server()

    def _build_server(self) -> Server:
        server = Server("agent-fox-tools")
        dirs = self.allowed_dirs

        @server.list_tools()
        async def _list_tools() -> list[mcp_types.Tool]:
            return list(_TOOLS)

        @server.call_tool()
        async def _call_tool(
            name: str,
            arguments: dict[str, Any] | None,
        ) -> list[mcp_types.TextContent]:
            args = arguments or {}
            text = _dispatch_tool(name, args, dirs)
            return [mcp_types.TextContent(type="text", text=text)]

        return server

    # ---- Test-friendly synchronous API ----

    def list_tools(self) -> list[ToolInfo]:
        """Return metadata for all registered tools."""
        return [
            ToolInfo(
                name=t.name,
                description=t.description or "",
                input_schema=t.inputSchema,
            )
            for t in _TOOLS
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Synchronously call a tool and return text."""
        return _dispatch_tool(name, arguments, self.allowed_dirs)

    async def run_stdio(self) -> None:
        """Run the MCP server on stdio transport."""
        async with stdio_server() as streams:
            read_stream, write_stream = streams
            init_options = self.mcp_server.create_initialization_options()
            await self.mcp_server.run(read_stream, write_stream, init_options)


def create_mcp_server(
    allowed_dirs: list[str] | None = None,
) -> FoxMCPServer:
    """Create an MCP server exposing fox tools.

    If ``allowed_dirs`` is set, all file paths are validated
    against the list before any operation.

    Requirements: 29-REQ-7.1, 29-REQ-7.2, 29-REQ-7.4,
                  29-REQ-7.E1
    """
    return FoxMCPServer(allowed_dirs=allowed_dirs)
