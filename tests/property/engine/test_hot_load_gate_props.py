"""Property tests for hot-load gate pipeline.

Test Spec: TS-51-P4 (gate pipeline monotonic filtering),
           TS-51-P5 (git-tracked gate correctness),
           TS-51-P6 (completeness gate correctness),
           TS-51-P7 (lint gate correctness),
           TS-51-P8 (stateless re-evaluation)
Requirements: 51-REQ-4.1, 51-REQ-4.E1, 51-REQ-5.1, 51-REQ-5.E1,
              51-REQ-6.1, 51-REQ-6.2, 51-REQ-6.3, 51-REQ-6.E1,
              51-REQ-7.1, 51-REQ-7.2, 51-REQ-7.3
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.engine.hot_load import (
    discover_new_specs_gated,
    is_spec_complete,
    is_spec_tracked_on_develop,
    lint_spec_gate,
)
from agent_fox.spec.validator import EXPECTED_FILES

# Strategy for spec states
spec_state_strategy = st.fixed_dictionaries(
    {
        "tracked": st.booleans(),
        "complete": st.booleans(),
        "lint_clean": st.booleans(),
    }
)


# ---------------------------------------------------------------------------
# TS-51-P4: Gate pipeline is monotonically filtering
# ---------------------------------------------------------------------------


class TestGatePipelineMonotonicFiltering:
    """TS-51-P4: Output is a subset where every element passes all gates.

    Property 4 from design.md.
    Validates: 51-REQ-4.1, 51-REQ-5.1, 51-REQ-6.1, 51-REQ-7.1
    """

    @given(
        spec_states=st.lists(spec_state_strategy, min_size=1, max_size=10),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_output_subset_all_pass(
        self,
        spec_states: list[dict[str, bool]],
    ) -> None:
        """Every spec in output passes all three gates."""
        from agent_fox.spec.discovery import SpecInfo

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            specs_dir = tmp_path / ".specs"
            specs_dir.mkdir(parents=True)

            specs = []
            for i, state in enumerate(spec_states):
                name = f"{i:02d}_spec_{i}"
                spec_path = specs_dir / name
                spec_path.mkdir(parents=True)
                # Create files based on completeness state
                for f in EXPECTED_FILES:
                    (spec_path / f).write_text(f"# {f}\nContent\n")
                if not state["complete"]:
                    # Remove one file to make incomplete
                    (spec_path / "design.md").unlink()

                specs.append(
                    SpecInfo(
                        name=name,
                        prefix=i,
                        path=spec_path,
                        has_tasks=True,
                        has_prd=True,
                    )
                )

            async def mock_is_tracked(
                repo_root: Path, spec_name: str, **kwargs: object
            ) -> bool:
                idx = int(spec_name.split("_")[0])
                return spec_states[idx]["tracked"]

            def mock_lint_gate(
                spec_name: str, spec_path: Path
            ) -> tuple[bool, list[str]]:
                idx = int(spec_name.split("_")[0])
                if spec_states[idx]["lint_clean"]:
                    return (True, [])
                return (False, ["lint error"])

            with (
                patch(
                    "agent_fox.engine.hot_load.discover_new_specs",
                    return_value=specs,
                ),
                patch(
                    "agent_fox.engine.hot_load.is_spec_tracked_on_develop",
                    side_effect=mock_is_tracked,
                ),
                patch(
                    "agent_fox.engine.hot_load.lint_spec_gate",
                    side_effect=mock_lint_gate,
                ),
            ):
                result = await discover_new_specs_gated(
                    specs_dir, known_specs=set(), repo_root=tmp_path
                )

            # Output is a subset
            assert len(result) <= len(spec_states)

            # Every spec in output passes all gates
            for spec in result:
                idx = int(spec.name.split("_")[0])
                assert spec_states[idx]["tracked"]
                assert spec_states[idx]["complete"]
                assert spec_states[idx]["lint_clean"]


# ---------------------------------------------------------------------------
# TS-51-P5: Git-tracked gate correctness
# ---------------------------------------------------------------------------


class TestGitTrackedGateCorrectness:
    """TS-51-P5: Git-tracked gate returns True iff ls-tree has output.

    Property 5 from design.md.
    Validates: 51-REQ-4.1, 51-REQ-4.E1
    """

    @given(
        has_output=st.booleans(),
        command_succeeds=st.booleans(),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_correctness(
        self,
        has_output: bool,
        command_succeeds: bool,
    ) -> None:
        """True when output non-empty OR failure. False only when empty+success."""

        async def mock_run_git(
            args: list[str], cwd: Path, check: bool = True, **kwargs: object
        ) -> tuple[int, str, str]:
            if not command_succeeds:
                raise Exception("git failed")
            output = "100644 blob abc\tprd.md\n" if has_output else ""
            return (0, output, "")

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "agent_fox.engine.hot_load.run_git",
                side_effect=mock_run_git,
            ):
                result = await is_spec_tracked_on_develop(Path(tmp), "test_spec")

        if not command_succeeds:
            assert result is True  # permissive fallback
        elif has_output:
            assert result is True
        else:
            assert result is False


# ---------------------------------------------------------------------------
# TS-51-P6: Completeness gate correctness
# ---------------------------------------------------------------------------


class TestCompletenessGateCorrectness:
    """TS-51-P6: Passes iff all 5 files exist and are non-empty.

    Property 6 from design.md.
    Validates: 51-REQ-5.1, 51-REQ-5.E1
    """

    @given(
        present_files=st.lists(
            st.sampled_from(EXPECTED_FILES),
            min_size=0,
            max_size=5,
            unique=True,
        ),
        empty_files=st.lists(
            st.sampled_from(EXPECTED_FILES),
            min_size=0,
            max_size=5,
            unique=True,
        ),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_correctness(
        self,
        present_files: list[str],
        empty_files: list[str],
    ) -> None:
        """Passes iff all 5 present AND all non-empty."""
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = Path(tmp) / "test_spec"
            spec_path.mkdir()

            for f in present_files:
                fp = spec_path / f
                if f in empty_files:
                    fp.write_text("")
                else:
                    fp.write_text(f"# {f}\nContent\n")

            passed, missing = is_spec_complete(spec_path)

            expected_missing = []
            for f in EXPECTED_FILES:
                if f not in present_files or f in empty_files:
                    expected_missing.append(f)

            assert passed == (len(expected_missing) == 0)
            assert set(missing) == set(expected_missing)


# ---------------------------------------------------------------------------
# TS-51-P7: Lint gate correctness
# ---------------------------------------------------------------------------


class TestLintGateCorrectness:
    """TS-51-P7: Passes iff no error findings. On exception, fails.

    Property 7 from design.md.
    Validates: 51-REQ-6.1, 51-REQ-6.2, 51-REQ-6.3, 51-REQ-6.E1
    """

    @given(
        severities=st.lists(
            st.sampled_from(["error", "warning", "hint"]),
            min_size=0,
            max_size=10,
        ),
        raises=st.booleans(),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_correctness(
        self,
        severities: list[str],
        raises: bool,
    ) -> None:
        """Passes iff no error findings and no exception."""
        from agent_fox.spec.validator import Finding

        findings = [
            Finding(
                spec_name="test_spec",
                file="test.md",
                rule=f"rule_{i}",
                severity=sev,
                message=f"Finding {i}",
                line=i,
            )
            for i, sev in enumerate(severities)
        ]

        with tempfile.TemporaryDirectory() as tmp:
            spec_path = Path(tmp) / "test_spec"
            spec_path.mkdir()

            if raises:
                with patch(
                    "agent_fox.engine.hot_load.validate_specs",
                    side_effect=RuntimeError("boom"),
                ):
                    passed, errors = lint_spec_gate("test_spec", spec_path)
                assert passed is False
            else:
                with patch(
                    "agent_fox.engine.hot_load.validate_specs",
                    return_value=findings,
                ):
                    passed, errors = lint_spec_gate("test_spec", spec_path)

                has_errors = any(s == "error" for s in severities)
                assert passed == (not has_errors)


# ---------------------------------------------------------------------------
# TS-51-P8: Stateless re-evaluation
# ---------------------------------------------------------------------------


class TestStatelessReEvaluation:
    """TS-51-P8: Gate outcome depends only on current state.

    Property 8 from design.md.
    Validates: 51-REQ-7.2, 51-REQ-7.3
    """

    @given(
        state_1=spec_state_strategy,
        state_2=spec_state_strategy,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_result_depends_only_on_current_state(
        self,
        state_1: dict[str, bool],
        state_2: dict[str, bool],
    ) -> None:
        """Second evaluation matches a fresh evaluation of state_2."""
        from agent_fox.spec.discovery import SpecInfo

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            specs_dir = tmp_path / ".specs"
            spec_path = specs_dir / "42_feature"

            def setup_spec(state: dict[str, bool]) -> None:
                # Clean and recreate
                if spec_path.exists():
                    import shutil

                    shutil.rmtree(spec_path)
                spec_path.mkdir(parents=True)
                if state["complete"]:
                    for f in EXPECTED_FILES:
                        (spec_path / f).write_text(f"# {f}\nContent\n")
                else:
                    # Create only some files
                    for f in EXPECTED_FILES[:3]:
                        (spec_path / f).write_text(f"# {f}\nContent\n")

            mock_spec = SpecInfo(
                name="42_feature",
                prefix=42,
                path=spec_path,
                has_tasks=True,
                has_prd=True,
            )

            async def make_is_tracked(state: dict[str, bool]):  # noqa: ANN202
                async def _fn(
                    repo_root: Path, spec_name: str, **kwargs: object
                ) -> bool:
                    return state["tracked"]

                return _fn

            def make_lint_gate(state: dict[str, bool]):  # noqa: ANN202
                def _fn(spec_name: str, spec_path: Path) -> tuple[bool, list[str]]:
                    if state["lint_clean"]:
                        return (True, [])
                    return (False, ["lint error"])

                return _fn

            # Eval 1 with state_1
            setup_spec(state_1)
            with (
                patch(
                    "agent_fox.engine.hot_load.discover_new_specs",
                    return_value=[mock_spec],
                ),
                patch(
                    "agent_fox.engine.hot_load.is_spec_tracked_on_develop",
                    side_effect=await make_is_tracked(state_1),
                ),
                patch(
                    "agent_fox.engine.hot_load.lint_spec_gate",
                    side_effect=make_lint_gate(state_1),
                ),
            ):
                await discover_new_specs_gated(
                    specs_dir, known_specs=set(), repo_root=tmp_path
                )

            # Eval 2 with state_2
            setup_spec(state_2)
            with (
                patch(
                    "agent_fox.engine.hot_load.discover_new_specs",
                    return_value=[mock_spec],
                ),
                patch(
                    "agent_fox.engine.hot_load.is_spec_tracked_on_develop",
                    side_effect=await make_is_tracked(state_2),
                ),
                patch(
                    "agent_fox.engine.hot_load.lint_spec_gate",
                    side_effect=make_lint_gate(state_2),
                ),
            ):
                result_2 = await discover_new_specs_gated(
                    specs_dir, known_specs=set(), repo_root=tmp_path
                )

            # Fresh eval with state_2 (verify same result)
            setup_spec(state_2)
            with (
                patch(
                    "agent_fox.engine.hot_load.discover_new_specs",
                    return_value=[mock_spec],
                ),
                patch(
                    "agent_fox.engine.hot_load.is_spec_tracked_on_develop",
                    side_effect=await make_is_tracked(state_2),
                ),
                patch(
                    "agent_fox.engine.hot_load.lint_spec_gate",
                    side_effect=make_lint_gate(state_2),
                ),
            ):
                result_fresh = await discover_new_specs_gated(
                    specs_dir, known_specs=set(), repo_root=tmp_path
                )

            # Results from eval_2 and fresh must match
            assert len(result_2) == len(result_fresh)
