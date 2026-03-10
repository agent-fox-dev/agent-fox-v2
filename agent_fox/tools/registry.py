"""Fox tool registry: builds ToolDefinition list for backend registration.

Wraps core fox tool functions as ToolDefinition objects with JSON Schemas
and handler functions that deserialize tool_input dicts into function calls.

Requirements: 29-REQ-8.2
"""

from __future__ import annotations

from typing import Any

from agent_fox.session.backends.protocol import ToolDefinition
from agent_fox.tools.edit import fox_edit
from agent_fox.tools.outline import fox_outline
from agent_fox.tools.read import fox_read
from agent_fox.tools.search import fox_search
from agent_fox.tools.types import EditOperation


def _handle_outline(tool_input: dict[str, Any]) -> Any:
    """Handler for fox_outline tool invocations."""
    return fox_outline(file_path=tool_input["file_path"])


def _handle_read(tool_input: dict[str, Any]) -> Any:
    """Handler for fox_read tool invocations."""
    ranges = [tuple(r) for r in tool_input["ranges"]]
    return fox_read(file_path=tool_input["file_path"], ranges=ranges)


def _handle_edit(tool_input: dict[str, Any]) -> Any:
    """Handler for fox_edit tool invocations."""
    edits = [
        EditOperation(
            start_line=e["start_line"],
            end_line=e["end_line"],
            hashes=e["hashes"],
            new_content=e["new_content"],
        )
        for e in tool_input["edits"]
    ]
    return fox_edit(file_path=tool_input["file_path"], edits=edits)


def _handle_search(tool_input: dict[str, Any]) -> Any:
    """Handler for fox_search tool invocations."""
    return fox_search(
        file_path=tool_input["file_path"],
        pattern=tool_input["pattern"],
        context=tool_input.get("context", 0),
    )


# JSON Schemas for each tool
_OUTLINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Absolute path to the file",
        },
    },
    "required": ["file_path"],
}

_READ_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Absolute path to the file",
        },
        "ranges": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 2,
                "maxItems": 2,
            },
            "description": "List of [start, end] line ranges (1-based, inclusive)",
        },
    },
    "required": ["file_path", "ranges"],
}

_EDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Absolute path to the file",
        },
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "hashes": {"type": "array", "items": {"type": "string"}},
                    "new_content": {"type": "string"},
                },
                "required": ["start_line", "end_line", "hashes", "new_content"],
            },
        },
    },
    "required": ["file_path", "edits"],
}

_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Absolute path to the file",
        },
        "pattern": {
            "type": "string",
            "description": "Regex pattern to search for",
        },
        "context": {
            "type": "integer",
            "default": 0,
            "description": "Number of context lines before and after each match",
        },
    },
    "required": ["file_path", "pattern"],
}


def build_fox_tool_definitions() -> list[ToolDefinition]:
    """Build ToolDefinition list for all four fox tools.

    Each definition wraps a core function with its JSON Schema
    and a handler that deserializes tool_input and calls the function.

    Requirements: 29-REQ-8.2
    """
    return [
        ToolDefinition(
            name="fox_outline",
            description=(
                "Return a structural outline of a file showing functions, "
                "classes, and other declarations with line numbers."
            ),
            input_schema=_OUTLINE_SCHEMA,
            handler=_handle_outline,
        ),
        ToolDefinition(
            name="fox_read",
            description=(
                "Read specific line ranges from a file with content hashes "
                "for use in subsequent edit operations."
            ),
            input_schema=_READ_SCHEMA,
            handler=_handle_read,
        ),
        ToolDefinition(
            name="fox_edit",
            description=(
                "Apply hash-verified edits to a file. Verifies content hashes "
                "before writing to prevent edits against stale reads."
            ),
            input_schema=_EDIT_SCHEMA,
            handler=_handle_edit,
        ),
        ToolDefinition(
            name="fox_search",
            description=(
                "Search a file by regex pattern and return matching lines "
                "with context and content hashes."
            ),
            input_schema=_SEARCH_SCHEMA,
            handler=_handle_search,
        ),
    ]
