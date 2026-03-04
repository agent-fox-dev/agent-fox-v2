"""Property tests for detector.

Test Spec: TS-08-P1 (detection determinism)
Property: Property 1 from design.md
Requirements: 08-REQ-1.1, 08-REQ-1.2
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.fix.detector import detect_checks

# Strategy: combination of config files that may be present
config_strategies = st.fixed_dictionaries(
    {},
    optional={
        "has_pyproject_pytest": st.just(True),
        "has_pyproject_ruff": st.just(True),
        "has_pyproject_mypy": st.just(True),
        "has_package_json_test": st.just(True),
        "has_package_json_lint": st.just(True),
        "has_makefile_test": st.just(True),
        "has_cargo_toml": st.just(True),
    },
)


def _create_project(tmp_dir, config_flags: dict) -> None:
    """Create config files in tmp_dir based on flags."""
    # Build pyproject.toml content
    pyproject_sections = []
    if config_flags.get("has_pyproject_pytest"):
        pyproject_sections.append('[tool.pytest.ini_options]\ntestpaths = ["tests"]')
    if config_flags.get("has_pyproject_ruff"):
        pyproject_sections.append("[tool.ruff]")
    if config_flags.get("has_pyproject_mypy"):
        pyproject_sections.append("[tool.mypy]")

    if pyproject_sections:
        (tmp_dir / "pyproject.toml").write_text("\n\n".join(pyproject_sections) + "\n")

    # Build package.json
    scripts = {}
    if config_flags.get("has_package_json_test"):
        scripts["test"] = "jest"
    if config_flags.get("has_package_json_lint"):
        scripts["lint"] = "eslint ."
    if scripts:
        (tmp_dir / "package.json").write_text(json.dumps({"scripts": scripts}))

    # Makefile
    if config_flags.get("has_makefile_test"):
        (tmp_dir / "Makefile").write_text("test:\n\tpytest\n")

    # Cargo.toml
    if config_flags.get("has_cargo_toml"):
        (tmp_dir / "Cargo.toml").write_text('[package]\nname = "myproject"\n')


class TestDetectionDeterminism:
    """TS-08-P1: Detection determinism.

    Property 1: For any project directory with a fixed set of configuration
    files, calling detect_checks() twice returns identical results.
    """

    @given(config_flags=config_strategies)
    @settings(max_examples=30)
    def test_detection_is_deterministic(
        self,
        config_flags: dict,
        tmp_path_factory,
    ) -> None:
        """detect_checks() returns the same result on two consecutive calls."""
        tmp_dir = tmp_path_factory.mktemp("det")
        _create_project(tmp_dir, config_flags)

        result1 = detect_checks(tmp_dir)
        result2 = detect_checks(tmp_dir)

        assert result1 == result2
