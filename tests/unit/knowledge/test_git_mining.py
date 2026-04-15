"""Tests for agent_fox.knowledge.git_mining — Spec 101.

Tests: TS-101-7, TS-101-8, TS-101-10, TS-101-15, TS-101-16,
       TS-101-17, TS-101-18, TS-101-19
Requirements: 101-REQ-4.1, 101-REQ-4.2, 101-REQ-4.3, 101-REQ-4.4,
              101-REQ-4.5, 101-REQ-4.6, 101-REQ-4.E2, 101-REQ-4.E3
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from agent_fox.knowledge.git_mining import (
    MiningResult,
    _compute_cochange_counts,
    _compute_file_frequencies,
    _is_mining_fact_exists,
    _parse_git_numstat,
    mine_git_patterns,
)
from agent_fox.knowledge.store import load_facts_by_spec


def _make_subprocess_result(stdout: str, returncode: int = 0) -> MagicMock:
    """Create a mock subprocess.CompletedProcess with given stdout."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    return mock


class TestMiningResultFields:
    """TS-101-15: MiningResult has required fields with correct defaults.

    Requirement: 101-REQ-4.6
    """

    def test_all_count_fields_default_to_zero(self) -> None:
        """Verify all count fields default to zero."""
        r = MiningResult()
        assert r.fragile_areas_created == 0
        assert r.cochange_patterns_created == 0
        assert r.commits_analyzed == 0
        assert r.files_analyzed == 0

    def test_is_frozen_dataclass(self) -> None:
        """Verify MiningResult is immutable (frozen=True)."""
        r = MiningResult()
        with pytest.raises((AttributeError, TypeError)):
            r.fragile_areas_created = 1  # type: ignore[misc]


class TestParseGitNumstat:
    """TS-101-17: _parse_git_numstat correctly parses git log --numstat output.

    Requirement: 101-REQ-4.1, 101-REQ-4.3
    """

    def test_parses_two_commits_correctly(self, tmp_path: Path) -> None:
        """Verify correct mapping of commit SHA to file paths."""
        git_output = "sha1\n10\t5\tsrc/a.py\n3\t1\tsrc/b.py\n\nsha2\n1\t1\tsrc/a.py\n\n"
        with patch(
            "agent_fox.knowledge.git_mining.subprocess.run",
            return_value=_make_subprocess_result(git_output),
        ):
            result = _parse_git_numstat(tmp_path, days=365)

        assert result == {
            "sha1": ["src/a.py", "src/b.py"],
            "sha2": ["src/a.py"],
        }

    def test_empty_output_returns_empty_dict(self, tmp_path: Path) -> None:
        """Verify empty git output returns empty dict."""
        with patch(
            "agent_fox.knowledge.git_mining.subprocess.run",
            return_value=_make_subprocess_result(""),
        ):
            result = _parse_git_numstat(tmp_path, days=365)

        assert result == {}

    def test_skips_binary_file_entries(self, tmp_path: Path) -> None:
        """Verify binary file entries (- - filename) are excluded."""
        git_output = "sha1\n-\t-\tbinary.png\n3\t1\tsrc/a.py\n\n"
        with patch(
            "agent_fox.knowledge.git_mining.subprocess.run",
            return_value=_make_subprocess_result(git_output),
        ):
            result = _parse_git_numstat(tmp_path, days=365)

        assert "src/a.py" in result.get("sha1", [])
        assert "binary.png" not in result.get("sha1", [])

    def test_uses_days_parameter_in_git_call(self, tmp_path: Path) -> None:
        """Verify git log is called with the specified days window."""
        with patch(
            "agent_fox.knowledge.git_mining.subprocess.run",
            return_value=_make_subprocess_result(""),
        ) as mock_run:
            _parse_git_numstat(tmp_path, days=30)

        # The subprocess call should include some reference to the days limit
        assert mock_run.called
        call_args = mock_run.call_args
        cmd = call_args.args[0] if call_args.args else call_args[0][0]
        # Either --after or --since or similar date filtering in args
        assert any("30" in str(arg) or "after" in str(arg) or "since" in str(arg) for arg in cmd)


class TestComputeFileFrequencies:
    """TS-101-18: _compute_file_frequencies counts correctly.

    Requirement: 101-REQ-4.1
    """

    def test_basic_frequency_counts(self) -> None:
        """Verify correct per-file commit counts."""
        commit_files = {
            "sha1": ["a.py", "b.py"],
            "sha2": ["a.py"],
            "sha3": ["a.py", "c.py"],
        }
        result = _compute_file_frequencies(commit_files)
        assert result == {"a.py": 3, "b.py": 1, "c.py": 1}

    def test_empty_input_returns_empty(self) -> None:
        """Verify empty input returns empty dict."""
        assert _compute_file_frequencies({}) == {}

    def test_single_file_single_commit(self) -> None:
        """Verify single file in single commit counts as 1."""
        result = _compute_file_frequencies({"sha1": ["only.py"]})
        assert result == {"only.py": 1}

    def test_multiple_files_same_commit(self) -> None:
        """Verify multiple files in one commit each counted once."""
        result = _compute_file_frequencies({"sha1": ["a.py", "b.py", "c.py"]})
        assert result == {"a.py": 1, "b.py": 1, "c.py": 1}


class TestComputeCochangeCounts:
    """TS-101-19: _compute_cochange_counts counts correctly.

    Requirement: 101-REQ-4.2
    """

    def test_basic_cochange_counts(self) -> None:
        """Verify correct per-pair co-occurrence with sorted tuple keys."""
        commit_files = {
            "sha1": ["a.py", "b.py"],
            "sha2": ["a.py", "b.py"],
            "sha3": ["a.py"],
        }
        result = _compute_cochange_counts(commit_files)
        assert result == {("a.py", "b.py"): 2}

    def test_keys_are_sorted_tuples(self) -> None:
        """Verify key is always (smaller_path, larger_path) lexicographically."""
        commit_files = {"sha1": ["z.py", "a.py"]}
        result = _compute_cochange_counts(commit_files)
        assert ("a.py", "z.py") in result
        assert ("z.py", "a.py") not in result

    def test_empty_input_returns_empty(self) -> None:
        """Verify empty input returns empty dict."""
        assert _compute_cochange_counts({}) == {}

    def test_single_file_commits_produce_no_pairs(self) -> None:
        """Verify commits with one file produce no co-change pairs."""
        commit_files = {"sha1": ["a.py"], "sha2": ["b.py"]}
        assert _compute_cochange_counts(commit_files) == {}

    def test_three_file_commit_produces_three_pairs(self) -> None:
        """Verify C(3,2)=3 pairs from a single three-file commit."""
        commit_files = {"sha1": ["a.py", "b.py", "c.py"]}
        result = _compute_cochange_counts(commit_files)
        assert len(result) == 3
        assert ("a.py", "b.py") in result
        assert ("a.py", "c.py") in result
        assert ("b.py", "c.py") in result


class TestFragileAreaDetection:
    """TS-101-7: mine_git_patterns creates fragile_area facts above threshold.

    Requirement: 101-REQ-4.1, 101-REQ-4.4
    """

    def test_creates_one_fragile_area_fact(self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Verify one fragile_area fact created when file meets threshold."""
        mock_data = {f"sha{i}": ["src/hot_file.py"] for i in range(25)}
        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            result = mine_git_patterns(tmp_path, knowledge_conn, fragile_threshold=20)

        assert result.fragile_areas_created == 1
        facts = load_facts_by_spec("onboard", knowledge_conn)
        fragile = [f for f in facts if f.category == "fragile_area"]
        assert len(fragile) == 1
        assert "src/hot_file.py" in fragile[0].content

    def test_file_below_threshold_not_flagged(self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Verify files modified fewer than threshold times are not flagged."""
        mock_data = {f"sha{i}": ["src/stable.py"] for i in range(15)}
        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            result = mine_git_patterns(tmp_path, knowledge_conn, fragile_threshold=20)

        assert result.fragile_areas_created == 0

    def test_fragile_fact_has_correct_spec_name(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Verify fragile_area fact has spec_name='onboard'."""
        mock_data = {f"sha{i}": ["src/hot.py"] for i in range(25)}
        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            mine_git_patterns(tmp_path, knowledge_conn, fragile_threshold=20)

        facts = load_facts_by_spec("onboard", knowledge_conn)
        fragile = [f for f in facts if f.category == "fragile_area"]
        assert len(fragile) == 1
        assert fragile[0].spec_name == "onboard"

    def test_fragile_fact_has_fingerprint_keyword(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Verify fragile_area fact includes fingerprint keyword."""
        mock_data = {f"sha{i}": ["src/hot.py"] for i in range(25)}
        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            mine_git_patterns(tmp_path, knowledge_conn, fragile_threshold=20)

        facts = load_facts_by_spec("onboard", knowledge_conn)
        fragile = [f for f in facts if f.category == "fragile_area"]
        assert len(fragile) == 1
        fingerprints = [kw for kw in fragile[0].keywords if kw.startswith("onboard:fragile:")]
        assert len(fingerprints) >= 1


class TestCochangePatternDetection:
    """TS-101-8: mine_git_patterns creates pattern facts for co-changed files.

    Requirement: 101-REQ-4.2, 101-REQ-4.5
    """

    def test_creates_one_cochange_pattern_fact(self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Verify one pattern fact created for file pair meeting co-change threshold."""
        mock_data = {f"sha{i}": ["a.py", "b.py"] for i in range(6)}
        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            result = mine_git_patterns(tmp_path, knowledge_conn, cochange_threshold=5)

        assert result.cochange_patterns_created == 1
        facts = load_facts_by_spec("onboard", knowledge_conn)
        patterns = [f for f in facts if f.category == "pattern"]
        assert len(patterns) == 1
        assert "a.py" in patterns[0].content
        assert "b.py" in patterns[0].content

    def test_pair_below_threshold_not_flagged(self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Verify pairs co-changed fewer than threshold times are not flagged."""
        mock_data = {f"sha{i}": ["a.py", "b.py"] for i in range(3)}
        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            result = mine_git_patterns(tmp_path, knowledge_conn, cochange_threshold=5)

        assert result.cochange_patterns_created == 0

    def test_cochange_fact_mentions_both_files(self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Verify co-change pattern fact content names both files."""
        mock_data = {f"sha{i}": ["x.py", "y.py"] for i in range(8)}
        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            mine_git_patterns(tmp_path, knowledge_conn, cochange_threshold=5)

        facts = load_facts_by_spec("onboard", knowledge_conn)
        patterns = [f for f in facts if f.category == "pattern"]
        assert len(patterns) == 1
        assert "x.py" in patterns[0].content
        assert "y.py" in patterns[0].content


class TestMinimumCommitThreshold:
    """TS-101-10: Git mining skips when fewer than 10 commits in window.

    Requirement: 101-REQ-4.E2
    """

    def test_fewer_than_10_commits_returns_all_zeros(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Verify mining returns zero created facts with < 10 commits."""
        mock_data = {f"sha{i}": ["file.py"] for i in range(5)}
        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            result = mine_git_patterns(tmp_path, knowledge_conn)

        assert result.fragile_areas_created == 0
        assert result.cochange_patterns_created == 0

    def test_nine_commits_still_skips(self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
        """Verify 9 commits (< 10) still triggers the skip."""
        mock_data = {f"sha{i}": ["file.py"] for i in range(9)}
        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            result = mine_git_patterns(tmp_path, knowledge_conn, fragile_threshold=5)

        assert result.fragile_areas_created == 0
        assert result.cochange_patterns_created == 0


class TestDuplicateMiningFactPrevention:
    """TS-101-16: Mining skips creating duplicate facts.

    Requirement: 101-REQ-4.E3, 101-REQ-8.2
    """

    def test_second_run_does_not_duplicate_fragile_area(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Verify second mine run with same data creates zero new facts."""
        mock_data = {f"sha{i}": ["hot.py"] for i in range(25)}

        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            result1 = mine_git_patterns(tmp_path, knowledge_conn, fragile_threshold=20)

        assert result1.fragile_areas_created == 1

        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            result2 = mine_git_patterns(tmp_path, knowledge_conn, fragile_threshold=20)

        assert result2.fragile_areas_created == 0

    def test_is_mining_fact_exists_returns_false_for_unknown(self, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Verify _is_mining_fact_exists returns False when fingerprint absent."""
        assert not _is_mining_fact_exists(knowledge_conn, "onboard:fragile:nonexistent.py")

    def test_is_mining_fact_exists_returns_true_after_creation(
        self, knowledge_conn: duckdb.DuckDBPyConnection, tmp_path: Path
    ) -> None:
        """Verify _is_mining_fact_exists returns True after fact is created."""
        fingerprint = "onboard:fragile:checked.py"
        assert not _is_mining_fact_exists(knowledge_conn, fingerprint)

        mock_data = {f"sha{i}": ["checked.py"] for i in range(25)}
        with patch(
            "agent_fox.knowledge.git_mining._parse_git_numstat",
            return_value=mock_data,
        ):
            mine_git_patterns(tmp_path, knowledge_conn, fragile_threshold=20)

        assert _is_mining_fact_exists(knowledge_conn, fingerprint)
