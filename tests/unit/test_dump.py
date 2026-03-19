"""CLI-level tests for the dump command.

Test Spec: TS-49-1 through TS-49-6, TS-49-11, TS-49-E1, TS-49-E2
Requirements: 49-REQ-1.1, 49-REQ-1.2, 49-REQ-1.E1, 49-REQ-2.1,
              49-REQ-2.2, 49-REQ-2.3, 49-REQ-2.E1, 49-REQ-4.1
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import duckdb
from click.testing import CliRunner

from agent_fox.cli.app import main
from tests.unit.knowledge.conftest import SCHEMA_DDL

# -- Helpers -----------------------------------------------------------------


def _create_db_with_facts(
    db_path: Path,
    facts: list[dict] | None = None,
) -> None:
    """Create a real DuckDB file with schema and optional facts."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute(SCHEMA_DDL)
    if facts:
        for fact in facts:
            conn.execute(
                """
                INSERT INTO memory_facts
                    (id, content, category, spec_name, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [
                    fact.get("id", str(uuid.uuid4())),
                    fact["content"],
                    fact["category"],
                    fact["spec_name"],
                    fact.get("confidence", 0.9),
                ],
            )
    conn.close()


SAMPLE_FACTS = [
    {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "content": "DuckDB is used for the knowledge store",
        "category": "gotcha",
        "spec_name": "11_duckdb",
        "confidence": 0.9,
    },
    {
        "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "content": "Use render_summary for markdown output",
        "category": "pattern",
        "spec_name": "05_memory",
        "confidence": 0.6,
    },
]


# -- TS-49-1: Command registration ------------------------------------------


class TestCommandRegistered:
    """TS-49-1: dump appears as a subcommand of the main CLI group.

    Requirement: 49-REQ-1.1
    """

    def test_command_registered(self) -> None:
        """'dump' is a key in main.commands."""
        assert "dump" in main.commands


# -- TS-49-2: Error when no flags -------------------------------------------


class TestNoFlagsError:
    """TS-49-2: Bare dump without --memory or --db exits with code 1.

    Requirement: 49-REQ-1.2
    """

    def test_no_flags_error(self, tmp_path: Path) -> None:
        """Invoking dump with no flags exits with code 1."""
        db_path = tmp_path / ".agent-fox" / "knowledge.duckdb"
        _create_db_with_facts(db_path)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            # Create the DB in the isolated filesystem
            af_dir = Path(td) / ".agent-fox"
            af_dir.mkdir(parents=True, exist_ok=True)
            _create_db_with_facts(af_dir / "knowledge.duckdb")

            result = runner.invoke(main, ["dump"], catch_exceptions=False)

        assert result.exit_code == 1
        output = result.output.lower()
        assert "must specify" in output or "required" in output


# -- TS-49-3: Error when both flags -----------------------------------------


class TestBothFlagsError:
    """TS-49-3: dump --memory --db exits with code 1.

    Requirement: 49-REQ-1.E1
    """

    def test_both_flags_error(self, tmp_path: Path) -> None:
        """Invoking dump with both flags exits with code 1."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            af_dir = Path(td) / ".agent-fox"
            af_dir.mkdir(parents=True, exist_ok=True)
            _create_db_with_facts(af_dir / "knowledge.duckdb")

            result = runner.invoke(
                main, ["dump", "--memory", "--db"], catch_exceptions=False
            )

        assert result.exit_code == 1
        output = result.output.lower()
        assert "mutually exclusive" in output


# -- TS-49-4: Memory export writes Markdown ----------------------------------


class TestMemoryMarkdown:
    """TS-49-4: --memory produces docs/memory.md with facts grouped by category.

    Requirement: 49-REQ-2.1
    """

    def test_memory_markdown(self, tmp_path: Path) -> None:
        """dump --memory writes docs/memory.md with category headings."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            td_path = Path(td)
            af_dir = td_path / ".agent-fox"
            af_dir.mkdir(parents=True, exist_ok=True)
            _create_db_with_facts(af_dir / "knowledge.duckdb", SAMPLE_FACTS)

            result = runner.invoke(main, ["dump", "--memory"], catch_exceptions=False)

            assert result.exit_code == 0
            memory_md = td_path / "docs" / "memory.md"
            assert memory_md.exists(), f"Expected {memory_md} to exist"
            content = memory_md.read_text()
            assert "## Gotchas" in content
            assert "DuckDB is used for the knowledge store" in content


# -- TS-49-5: Memory export writes JSON --------------------------------------


class TestMemoryJson:
    """TS-49-5: --json dump --memory produces docs/memory.json.

    Requirement: 49-REQ-2.2
    """

    def test_memory_json(self, tmp_path: Path) -> None:
        """dump --memory with --json writes docs/memory.json."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            td_path = Path(td)
            af_dir = td_path / ".agent-fox"
            af_dir.mkdir(parents=True, exist_ok=True)
            _create_db_with_facts(af_dir / "knowledge.duckdb", SAMPLE_FACTS)

            result = runner.invoke(
                main, ["--json", "dump", "--memory"], catch_exceptions=False
            )

            assert result.exit_code == 0
            memory_json = td_path / "docs" / "memory.json"
            assert memory_json.exists(), f"Expected {memory_json} to exist"
            data = json.loads(memory_json.read_text())
            assert "facts" in data
            assert "generated" in data
            assert len(data["facts"]) == len(SAMPLE_FACTS)
            for fact_obj in data["facts"]:
                assert {"id", "content", "category", "spec_name", "confidence"} <= set(
                    fact_obj.keys()
                )


# -- TS-49-6: Memory export prints confirmation ------------------------------


class TestMemoryConfirmation:
    """TS-49-6: --memory prints a confirmation message with path and fact count.

    Requirement: 49-REQ-2.3
    """

    def test_memory_confirmation(self, tmp_path: Path) -> None:
        """dump --memory prints confirmation to stderr."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            td_path = Path(td)
            af_dir = td_path / ".agent-fox"
            af_dir.mkdir(parents=True, exist_ok=True)
            _create_db_with_facts(af_dir / "knowledge.duckdb", SAMPLE_FACTS)

            result = runner.invoke(main, ["dump", "--memory"], catch_exceptions=False)

            assert result.exit_code == 0
            # Confirmation should mention the output path and fact count
            output = result.output.lower()
            assert "memory" in output
            assert str(len(SAMPLE_FACTS)) in output


# -- TS-49-11: Error when DB missing -----------------------------------------


class TestMissingDbError:
    """TS-49-11: Command exits 1 when knowledge DB file does not exist.

    Requirement: 49-REQ-4.1
    """

    def test_missing_db_error(self, tmp_path: Path) -> None:
        """dump --memory exits 1 when DB is missing."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # No .agent-fox/knowledge.duckdb created
            result = runner.invoke(main, ["dump", "--memory"], catch_exceptions=False)

        assert result.exit_code == 1
        output = result.output.lower()
        assert "not found" in output or "does not exist" in output

    def test_missing_db_error_db_flag(self, tmp_path: Path) -> None:
        """dump --db also exits 1 when DB is missing."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["dump", "--db"], catch_exceptions=False)

        assert result.exit_code == 1
        output = result.output.lower()
        assert "not found" in output or "does not exist" in output


# -- TS-49-E1: Memory export with no facts -----------------------------------


class TestMemoryEmptyMarkdown:
    """TS-49-E1: --memory with empty DB writes an empty-state file.

    Requirement: 49-REQ-2.E1
    """

    def test_memory_empty_markdown(self, tmp_path: Path) -> None:
        """dump --memory with no facts writes empty-state markdown."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            td_path = Path(td)
            af_dir = td_path / ".agent-fox"
            af_dir.mkdir(parents=True, exist_ok=True)
            _create_db_with_facts(af_dir / "knowledge.duckdb", facts=None)

            result = runner.invoke(main, ["dump", "--memory"], catch_exceptions=False)

            assert result.exit_code == 0
            memory_md = td_path / "docs" / "memory.md"
            assert memory_md.exists()
            content = memory_md.read_text().lower()
            assert "no facts" in content or content.strip() == ""

            # Warning should be printed
            output = result.output.lower()
            assert "no facts" in output or "warning" in output or "0" in output


# -- TS-49-E2: Memory JSON export with no facts ------------------------------


class TestMemoryEmptyJson:
    """TS-49-E2: --json --memory with empty DB writes JSON with empty array.

    Requirement: 49-REQ-2.E1
    """

    def test_memory_empty_json(self, tmp_path: Path) -> None:
        """dump --memory --json with no facts writes empty facts array."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            td_path = Path(td)
            af_dir = td_path / ".agent-fox"
            af_dir.mkdir(parents=True, exist_ok=True)
            _create_db_with_facts(af_dir / "knowledge.duckdb", facts=None)

            result = runner.invoke(
                main, ["--json", "dump", "--memory"], catch_exceptions=False
            )

            assert result.exit_code == 0
            memory_json = td_path / "docs" / "memory.json"
            assert memory_json.exists()
            data = json.loads(memory_json.read_text())
            assert data["facts"] == []
            assert "generated" in data
