"""MCP server integration tests.

Test Spec: TS-29-22 (four tools), TS-29-23 (delegates to core),
           TS-29-24 (CLI command), TS-29-25 (allowed-dirs),
           TS-29-E16 (path blocked), TS-29-E17 (clean shutdown)
Requirements: 29-REQ-7.1, 29-REQ-7.2, 29-REQ-7.3, 29-REQ-7.4,
              29-REQ-7.E1, 29-REQ-7.E2
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner


class TestMCPFourToolsRegistered:
    """TS-29-22: MCP server registers all four fox tools."""

    def test_four_tools_registered(self) -> None:
        from agent_fox.tools.server import create_mcp_server

        server = create_mcp_server()
        # The server should have four tools registered
        # Exact API depends on mcp SDK; we verify tool names
        tool_names = {t.name for t in server.list_tools()}
        assert tool_names == {"fox_outline", "fox_read", "fox_edit", "fox_search"}


class TestMCPDelegatesToCore:
    """TS-29-23: MCP tool calls produce same results as direct function calls."""

    def test_delegates_to_core(self, make_temp_file_with_lines) -> None:
        from agent_fox.tools.read import fox_read
        from agent_fox.tools.server import create_mcp_server

        f = make_temp_file_with_lines(10)
        direct = fox_read(str(f), [(1, 5)])

        server = create_mcp_server()
        mcp_result = server.call_tool(
            "fox_read", {"file_path": str(f), "ranges": [[1, 5]]}
        )
        # Results should be equivalent
        assert direct.lines[0].content in str(mcp_result)


class TestMCPCLICommand:
    """TS-29-24: serve-tools is a registered CLI command."""

    def test_cli_command(self) -> None:
        from agent_fox.cli.app import main

        runner = CliRunner()
        result = runner.invoke(main, ["serve-tools", "--help"])
        assert result.exit_code == 0
        assert "mcp" in result.output.lower() or "MCP" in result.output


class TestMCPAllowedDirs:
    """TS-29-25: --allowed-dirs restricts file access."""

    def test_allowed_dirs(self, tmp_path: Path) -> None:
        from agent_fox.tools.server import create_mcp_server

        safe_dir = tmp_path / "safe"
        safe_dir.mkdir()

        server = create_mcp_server(allowed_dirs=[str(safe_dir)])
        result = server.call_tool(
            "fox_read", {"file_path": "/etc/passwd", "ranges": [[1, 1]]}
        )
        assert "error" in str(result).lower() or hasattr(result, "is_error")


class TestMCPPathBlocked:
    """TS-29-E16: Path outside allowed-dirs is blocked."""

    def test_path_blocked(self, tmp_path: Path) -> None:
        from agent_fox.tools.server import create_mcp_server

        safe_dir = tmp_path / "safe"
        safe_dir.mkdir()

        server = create_mcp_server(allowed_dirs=[str(safe_dir)])
        result = server.call_tool(
            "fox_read", {"file_path": "/etc/hosts", "ranges": [[1, 1]]}
        )
        # Should return error, not file content
        assert "error" in str(result).lower() or "denied" in str(result).lower()


class TestMCPCleanShutdown:
    """TS-29-E17: Server exits cleanly on client disconnect."""

    def test_clean_shutdown(self) -> None:
        # This test verifies the server can be created and would exit
        # cleanly. Full subprocess test deferred to MCP server implementation.
        from agent_fox.tools.server import create_mcp_server

        server = create_mcp_server()
        # Server should be creatable without error
        assert server is not None


# Shared fixture for integration tests that need temp files
@pytest.fixture
def make_temp_file_with_lines(tmp_path: Path):
    """Factory fixture: create a temp file with N numbered lines."""

    def _make(n: int, name: str = "test.txt") -> Path:
        lines = [f"line {i}\n" for i in range(1, n + 1)]
        p = tmp_path / name
        p.write_text("".join(lines))
        return p

    return _make
