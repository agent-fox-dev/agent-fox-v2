"""DB-dump module tests for the dump command.

Test Spec: TS-49-7 through TS-49-10, TS-49-E3
Requirements: 49-REQ-3.1, 49-REQ-3.2, 49-REQ-3.3, 49-REQ-3.4, 49-REQ-3.E1
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import duckdb
from agent_fox.knowledge.dump import (
    discover_tables,
    dump_all_tables_json,
    dump_all_tables_md,
    dump_table_md,
)
from click.testing import CliRunner

from agent_fox.cli.app import main
from tests.unit.knowledge.conftest import SCHEMA_DDL

# -- Helpers -----------------------------------------------------------------


def _create_db_file(db_path: Path) -> None:
    """Create a DuckDB file with schema and sample data."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute(SCHEMA_DDL)
    # Insert sample facts
    conn.execute(
        """
        INSERT INTO memory_facts
            (id, content, category, spec_name, confidence, created_at)
        VALUES
            (?, 'Sample fact one', 'gotcha', 'spec_a', 0.9, CURRENT_TIMESTAMP),
            (?, 'Sample fact two', 'pattern', 'spec_b', 0.6, CURRENT_TIMESTAMP)
        """,
        [str(uuid.uuid4()), str(uuid.uuid4())],
    )
    conn.close()


def _in_memory_with_schema() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection with the full schema."""
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL)
    return conn


# -- TS-49-7: DB dump writes Markdown ----------------------------------------


class TestDbDumpMarkdown:
    """TS-49-7: --db produces .agent-fox/knowledge_dump.md with all tables.

    Requirement: 49-REQ-3.1
    """

    def test_db_dump_markdown(self, tmp_path: Path) -> None:
        """dump --db writes markdown with table headings."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            td_path = Path(td)
            _create_db_file(td_path / ".agent-fox" / "knowledge.duckdb")

            result = runner.invoke(main, ["dump", "--db"], catch_exceptions=False)

            assert result.exit_code == 0
            dump_md = td_path / ".agent-fox" / "knowledge_dump.md"
            assert dump_md.exists(), f"Expected {dump_md} to exist"
            content = dump_md.read_text()
            assert "## memory_facts" in content
            assert "## schema_version" in content

    def test_dump_all_tables_md_function(self, tmp_path: Path) -> None:
        """dump_all_tables_md writes all tables to a Markdown file."""
        conn = _in_memory_with_schema()
        conn.execute(
            """
            INSERT INTO memory_facts
                (id, content, category, spec_name, confidence, created_at)
            VALUES (?, 'test fact', 'gotcha', 'test', 0.9, CURRENT_TIMESTAMP)
            """,
            [str(uuid.uuid4())],
        )
        output = tmp_path / "dump.md"
        count = dump_all_tables_md(conn, output)
        assert count > 0
        content = output.read_text()
        assert "## memory_facts" in content
        conn.close()


# -- TS-49-8: DB dump writes JSON -------------------------------------------


class TestDbDumpJson:
    """TS-49-8: --json dump --db produces .agent-fox/knowledge_dump.json.

    Requirement: 49-REQ-3.2
    """

    def test_db_dump_json(self, tmp_path: Path) -> None:
        """dump --db with --json writes JSON with tables dict."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            td_path = Path(td)
            _create_db_file(td_path / ".agent-fox" / "knowledge.duckdb")

            result = runner.invoke(
                main, ["--json", "dump", "--db"], catch_exceptions=False
            )

            assert result.exit_code == 0
            dump_json = td_path / ".agent-fox" / "knowledge_dump.json"
            assert dump_json.exists(), f"Expected {dump_json} to exist"
            data = json.loads(dump_json.read_text())
            assert "tables" in data
            assert "generated" in data
            assert isinstance(data["tables"], dict)
            # Should have multiple tables from the schema
            assert len(data["tables"]) > 0

    def test_dump_all_tables_json_function(self, tmp_path: Path) -> None:
        """dump_all_tables_json writes all tables to a JSON file."""
        conn = _in_memory_with_schema()
        output = tmp_path / "dump.json"
        count = dump_all_tables_json(conn, output)
        assert count > 0
        data = json.loads(output.read_text())
        assert "tables" in data
        assert "generated" in data
        assert isinstance(data["tables"], dict)
        conn.close()


# -- TS-49-9: DB dump prints confirmation ------------------------------------


class TestDbDumpConfirmation:
    """TS-49-9: --db prints confirmation with file path and table count.

    Requirement: 49-REQ-3.3
    """

    def test_db_dump_confirmation(self, tmp_path: Path) -> None:
        """dump --db prints confirmation message."""
        runner = CliRunner(mix_stderr=False)
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            td_path = Path(td)
            _create_db_file(td_path / ".agent-fox" / "knowledge.duckdb")

            result = runner.invoke(main, ["dump", "--db"], catch_exceptions=False)

            assert result.exit_code == 0
            output = (result.output + (result.stderr or "")).lower()
            assert "knowledge_dump" in output


# -- TS-49-10: Cell truncation -----------------------------------------------


class TestCellTruncation:
    """TS-49-10: Cell values > 120 chars are truncated in Markdown output.

    Requirement: 49-REQ-3.4
    """

    def test_cell_truncation(self) -> None:
        """Long cell values are truncated to 117 chars + '...'."""
        conn = duckdb.connect(":memory:")
        conn.execute("CREATE TABLE test_table (id INTEGER, description TEXT)")
        long_value = "x" * 200
        conn.execute("INSERT INTO test_table VALUES (1, ?)", [long_value])

        md = dump_table_md(conn, "test_table")
        assert "..." in md
        assert long_value not in md
        assert long_value[:117] in md
        conn.close()

    def test_pipe_characters_escaped(self) -> None:
        """Pipe characters in cell values are escaped."""
        conn = duckdb.connect(":memory:")
        conn.execute("CREATE TABLE test_table (id INTEGER, value TEXT)")
        conn.execute("INSERT INTO test_table VALUES (1, 'hello|world')")

        md = dump_table_md(conn, "test_table")
        # The pipe inside the cell should be escaped (not raw |)
        assert "hello\\|world" in md or "hello&#124;world" in md
        conn.close()


# -- TS-49-E3: DB dump with no tables ---------------------------------------


class TestNoTablesError:
    """TS-49-E3: --db with a DB containing no tables exits with code 1.

    Requirement: 49-REQ-3.E1
    """

    def test_no_tables_error(self, tmp_path: Path) -> None:
        """dump --db with an empty database exits 1."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            td_path = Path(td)
            af_dir = td_path / ".agent-fox"
            af_dir.mkdir(parents=True, exist_ok=True)
            # Create a DB with no user tables
            conn = duckdb.connect(str(af_dir / "knowledge.duckdb"))
            conn.close()

            result = runner.invoke(main, ["dump", "--db"], catch_exceptions=False)

        assert result.exit_code == 1
        output = result.output.lower()
        assert "no tables" in output


# -- discover_tables unit test -----------------------------------------------


class TestDiscoverTables:
    """Unit tests for discover_tables function."""

    def test_discover_tables_finds_schema_tables(self) -> None:
        """discover_tables returns all user tables from the schema."""
        conn = _in_memory_with_schema()
        tables = discover_tables(conn)
        assert "memory_facts" in tables
        assert "schema_version" in tables
        assert len(tables) > 0
        conn.close()

    def test_discover_tables_empty_db(self) -> None:
        """discover_tables returns empty list for DB with no tables."""
        conn = duckdb.connect(":memory:")
        tables = discover_tables(conn)
        assert tables == []
        conn.close()
