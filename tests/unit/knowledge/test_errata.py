"""Tests for agent_fox.knowledge.errata — errata generation, storage, retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pytest

from agent_fox.knowledge.errata import (
    Erratum,
    format_errata_for_prompt,
    generate_errata_from_findings,
    persist_erratum_markdown,
    query_errata,
    store_errata,
)


# -- Helpers / stubs -----------------------------------------------------------


@dataclass(frozen=True)
class FakeFinding:
    """Minimal stub matching ReviewFinding's relevant attrs."""

    severity: str
    description: str
    requirement_ref: str | None = None


def _create_errata_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the errata table for tests."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS errata (
            id              VARCHAR PRIMARY KEY,
            spec_name       VARCHAR NOT NULL,
            task_group      VARCHAR NOT NULL,
            finding_summary TEXT NOT NULL,
            requirement_ref VARCHAR,
            fix_summary     TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


@pytest.fixture
def errata_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with the errata table."""
    conn = duckdb.connect(":memory:")
    _create_errata_table(conn)
    yield conn  # type: ignore[misc]
    conn.close()


# -- generate_errata_from_findings ---------------------------------------------


class TestGenerateErrataFromFindings:
    def test_critical_findings_produce_errata(self) -> None:
        findings = [
            FakeFinding("critical", "Auth bypass in login flow", "REQ-1.1"),
            FakeFinding("major", "Missing input validation", "REQ-2.3"),
        ]
        errata = generate_errata_from_findings(findings, "spec_42", "1")

        assert len(errata) == 2
        assert all(isinstance(e, Erratum) for e in errata)
        assert "[critical]" in errata[0].finding_summary
        assert "[major]" in errata[1].finding_summary
        assert errata[0].requirement_ref == "REQ-1.1"
        assert errata[0].spec_name == "spec_42"
        assert errata[0].task_group == "1"

    def test_minor_and_observation_excluded(self) -> None:
        findings = [
            FakeFinding("minor", "Style issue"),
            FakeFinding("observation", "Could be better"),
            FakeFinding("critical", "Real problem"),
        ]
        errata = generate_errata_from_findings(findings, "spec_1", "2")

        assert len(errata) == 1
        assert "[critical]" in errata[0].finding_summary

    def test_empty_findings_produce_empty_errata(self) -> None:
        errata = generate_errata_from_findings([], "spec_1", "1")
        assert errata == []

    def test_all_minor_produce_empty_errata(self) -> None:
        findings = [FakeFinding("minor", "Trivial")]
        errata = generate_errata_from_findings(findings, "spec_1", "1")
        assert errata == []

    def test_errata_have_unique_ids(self) -> None:
        findings = [
            FakeFinding("critical", "First"),
            FakeFinding("critical", "Second"),
        ]
        errata = generate_errata_from_findings(findings, "spec_1", "1")
        ids = [e.id for e in errata]
        assert len(set(ids)) == 2


# -- store_errata --------------------------------------------------------------


class TestStoreErrata:
    def test_stores_errata_and_returns_count(self, errata_conn: duckdb.DuckDBPyConnection) -> None:
        errata = [
            Erratum(id="e1", spec_name="spec_1", task_group="1", finding_summary="[critical] Problem"),
            Erratum(id="e2", spec_name="spec_1", task_group="1", finding_summary="[major] Issue"),
        ]
        count = store_errata(errata_conn, errata)

        assert count == 2
        rows = errata_conn.execute("SELECT COUNT(*) FROM errata").fetchone()
        assert rows is not None and rows[0] == 2

    def test_empty_list_returns_zero(self, errata_conn: duckdb.DuckDBPyConnection) -> None:
        count = store_errata(errata_conn, [])
        assert count == 0

    def test_missing_table_returns_zero(self) -> None:
        conn = duckdb.connect(":memory:")
        errata = [Erratum(id="e1", spec_name="s", task_group="1", finding_summary="x")]
        count = store_errata(conn, errata)
        assert count == 0
        conn.close()


# -- query_errata --------------------------------------------------------------


class TestQueryErrata:
    def test_queries_by_spec_name(self, errata_conn: duckdb.DuckDBPyConnection) -> None:
        errata_conn.execute(
            "INSERT INTO errata (id, spec_name, task_group, finding_summary) "
            "VALUES ('e1', 'spec_A', '1', 'Finding A'), "
            "       ('e2', 'spec_B', '1', 'Finding B'), "
            "       ('e3', 'spec_A', '2', 'Finding A2')"
        )
        results = query_errata(errata_conn, "spec_A")

        assert len(results) == 2
        assert all(e.spec_name == "spec_A" for e in results)

    def test_respects_limit(self, errata_conn: duckdb.DuckDBPyConnection) -> None:
        for i in range(5):
            errata_conn.execute(
                "INSERT INTO errata (id, spec_name, task_group, finding_summary) "
                "VALUES (?, 'spec_X', '1', ?)",
                [f"e{i}", f"Finding {i}"],
            )
        results = query_errata(errata_conn, "spec_X", limit=3)
        assert len(results) == 3

    def test_missing_table_returns_empty(self) -> None:
        conn = duckdb.connect(":memory:")
        results = query_errata(conn, "spec_1")
        assert results == []
        conn.close()

    def test_no_matching_spec_returns_empty(self, errata_conn: duckdb.DuckDBPyConnection) -> None:
        errata_conn.execute(
            "INSERT INTO errata (id, spec_name, task_group, finding_summary) "
            "VALUES ('e1', 'other_spec', '1', 'Finding')"
        )
        results = query_errata(errata_conn, "spec_1")
        assert results == []


# -- format_errata_for_prompt --------------------------------------------------


class TestFormatErrataForPrompt:
    def test_formats_basic_errata(self) -> None:
        errata = [Erratum(id="e1", spec_name="s", task_group="1", finding_summary="[critical] Bad thing")]
        result = format_errata_for_prompt(errata)

        assert len(result) == 1
        assert result[0] == "[ERRATA] [critical] Bad thing"

    def test_includes_requirement_ref(self) -> None:
        errata = [
            Erratum(
                id="e1",
                spec_name="s",
                task_group="1",
                finding_summary="[critical] Bad thing",
                requirement_ref="REQ-1.1",
            )
        ]
        result = format_errata_for_prompt(errata)

        assert "(ref: REQ-1.1)" in result[0]

    def test_includes_fix_summary(self) -> None:
        errata = [
            Erratum(
                id="e1",
                spec_name="s",
                task_group="1",
                finding_summary="[critical] Bad thing",
                fix_summary="Added validation",
            )
        ]
        result = format_errata_for_prompt(errata)

        assert "Fix: Added validation" in result[0]

    def test_empty_errata_returns_empty(self) -> None:
        assert format_errata_for_prompt([]) == []


# -- persist_erratum_markdown --------------------------------------------------


class TestPersistErratumMarkdown:
    def test_writes_markdown_file(self, tmp_path: Path) -> None:
        errata = [
            Erratum(
                id="e1",
                spec_name="42_auth",
                task_group="3",
                finding_summary="[critical] Auth bypass",
                requirement_ref="REQ-1.1",
            ),
        ]
        path = persist_erratum_markdown(errata, tmp_path)

        assert path is not None
        assert path.exists()
        content = path.read_text()
        assert "42_auth" in content
        assert "[critical] Auth bypass" in content
        assert "REQ-1.1" in content

    def test_empty_errata_returns_none(self, tmp_path: Path) -> None:
        result = persist_erratum_markdown([], tmp_path)
        assert result is None

    def test_creates_errata_directory(self, tmp_path: Path) -> None:
        errata = [Erratum(id="e1", spec_name="s", task_group="1", finding_summary="x")]
        path = persist_erratum_markdown(errata, tmp_path)

        assert path is not None
        assert (tmp_path / "docs" / "errata").is_dir()


# -- Migration v19 ------------------------------------------------------------


class TestMigrationV19:
    def test_migration_creates_errata_table(self) -> None:
        from agent_fox.knowledge.migrations import run_migrations

        conn = duckdb.connect(":memory:")
        run_migrations(conn)

        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
        assert "errata" in tables

        # Verify columns
        cols = {
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'errata'"
            ).fetchall()
        }
        assert {"id", "spec_name", "task_group", "finding_summary", "requirement_ref", "fix_summary", "created_at"} == cols

        conn.close()

    def test_migration_is_idempotent(self) -> None:
        from agent_fox.knowledge.migrations import run_migrations

        conn = duckdb.connect(":memory:")
        run_migrations(conn)
        run_migrations(conn)

        rows = conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = 19").fetchone()
        assert rows is not None and rows[0] == 1
        conn.close()
