"""Integration smoke tests for the four new language analyzers.

Test Spec: TS-107-SMOKE-1
Requirements: 107-REQ-5.1, 107-REQ-5.4, 107-REQ-6.2
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest

from agent_fox.knowledge.static_analysis import analyze_codebase
from tests.unit.knowledge.conftest import SCHEMA_DDL_V2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB with base schema and all migrations applied."""
    from agent_fox.knowledge.migrations import apply_pending_migrations

    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_DDL_V2)
    apply_pending_migrations(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Minimal source content for each language
# ---------------------------------------------------------------------------

_CS_SOURCE = """\
namespace App.Models
{
    public class UserService
    {
        public void CreateUser(string name) { }
    }
}
"""

_EX_SOURCE = """\
defmodule App.Accounts.User do
  def changeset(user, attrs) do
    user
  end

  defp validate(user), do: user
end
"""

_KT_SOURCE = """\
package app.models

class User(val name: String) {
    fun validate(): Boolean = name.isNotEmpty()
}

fun topLevel() {}
"""

_DART_SOURCE = """\
class User {
  String name;
  void save() {}
}

void topLevelFunction() {}
"""


# ---------------------------------------------------------------------------
# TS-107-SMOKE-1: Full analysis with new languages
# ---------------------------------------------------------------------------


class TestFullAnalysisNewLanguages:
    """TS-107-SMOKE-1: analyze_codebase() on a repo with all four new language files.

    Requirements: 107-REQ-5.1, 107-REQ-5.4, 107-REQ-6.2
    """

    def test_languages_analyzed_includes_new_languages(
        self,
        tmp_path: Path,
        entity_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """analyze_codebase returns languages_analyzed including all four new languages."""
        # Create source files for all four new languages
        (tmp_path / "UserService.cs").write_text(_CS_SOURCE)
        (tmp_path / "user.ex").write_text(_EX_SOURCE)
        (tmp_path / "User.kt").write_text(_KT_SOURCE)
        (tmp_path / "user.dart").write_text(_DART_SOURCE)

        result = analyze_codebase(tmp_path, entity_conn)

        assert "csharp" in result.languages_analyzed, "csharp must appear in languages_analyzed"
        assert "elixir" in result.languages_analyzed, "elixir must appear in languages_analyzed"
        assert "kotlin" in result.languages_analyzed, "kotlin must appear in languages_analyzed"
        assert "dart" in result.languages_analyzed, "dart must appear in languages_analyzed"

    def test_entities_inserted_for_each_new_language(
        self,
        tmp_path: Path,
        entity_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """After analysis, DuckDB has entities for each new language."""
        (tmp_path / "UserService.cs").write_text(_CS_SOURCE)
        (tmp_path / "user.ex").write_text(_EX_SOURCE)
        (tmp_path / "User.kt").write_text(_KT_SOURCE)
        (tmp_path / "user.dart").write_text(_DART_SOURCE)

        analyze_codebase(tmp_path, entity_conn)

        rows = entity_conn.execute(
            "SELECT language, COUNT(*) FROM entity_graph WHERE deleted_at IS NULL GROUP BY language"
        ).fetchall()
        lang_counts = {r[0]: r[1] for r in rows}

        assert lang_counts.get("csharp", 0) > 0, "csharp entities must be in DB"
        assert lang_counts.get("elixir", 0) > 0, "elixir entities must be in DB"
        assert lang_counts.get("kotlin", 0) > 0, "kotlin entities must be in DB"
        assert lang_counts.get("dart", 0) > 0, "dart entities must be in DB"

    def test_total_entity_count_is_nonzero(
        self,
        tmp_path: Path,
        entity_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Overall entity count is non-zero after analyzing all four languages."""
        (tmp_path / "UserService.cs").write_text(_CS_SOURCE)
        (tmp_path / "user.ex").write_text(_EX_SOURCE)
        (tmp_path / "User.kt").write_text(_KT_SOURCE)
        (tmp_path / "user.dart").write_text(_DART_SOURCE)

        result = analyze_codebase(tmp_path, entity_conn)

        assert result.entities_upserted > 0, "At least one entity must be upserted"
