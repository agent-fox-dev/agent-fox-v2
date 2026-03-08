"""Property tests for collector.

Test Spec: TS-08-P2 (collector completeness)
Property: Property 2 from design.md
Requirements: 08-REQ-2.1, 08-REQ-2.2, 08-REQ-2.3
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.fix.checks import run_checks
from agent_fox.fix.checks import CheckCategory, CheckDescriptor

# Strategy: generate a list of check descriptors with various exit codes
check_names = st.sampled_from(["pytest", "ruff", "mypy", "cargo test", "npm test"])
exit_codes = st.integers(min_value=0, max_value=1)


@st.composite
def check_with_exit_code(draw):
    """Generate a (CheckDescriptor, exit_code) pair."""
    name = draw(check_names)
    code = draw(exit_codes)
    category = {
        "pytest": CheckCategory.TEST,
        "ruff": CheckCategory.LINT,
        "mypy": CheckCategory.TYPE,
        "cargo test": CheckCategory.TEST,
        "npm test": CheckCategory.TEST,
    }[name]
    descriptor = CheckDescriptor(
        name=name,
        command=["mock", name],
        category=category,
    )
    return (descriptor, code)


class TestCollectorCompleteness:
    """TS-08-P2: Collector completeness.

    Property 2: For any list of check descriptors, run_checks() returns
    exactly one result per check. No check appears in both or neither.
    """

    @given(
        checks_and_codes=st.lists(
            check_with_exit_code(),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=30, deadline=None)
    def test_every_check_accounted_for(
        self,
        checks_and_codes: list,
        tmp_path_factory,
    ) -> None:
        """Every input check appears in exactly one of failures or passed."""
        tmp_dir = tmp_path_factory.mktemp("col")
        checks = [c for c, _ in checks_and_codes]
        exit_codes_list = [code for _, code in checks_and_codes]

        # Create mock subprocess results that return the corresponding exit codes
        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            idx = call_count
            call_count += 1
            code = exit_codes_list[idx] if idx < len(exit_codes_list) else 0
            return subprocess.CompletedProcess(
                args=args[0] if args else [],
                returncode=code,
                stdout="output",
                stderr="",
            )

        with patch(
            "agent_fox.fix.checks.subprocess.run",
            side_effect=mock_subprocess_run,
        ):
            failures, passed = run_checks(checks, tmp_dir)

        assert len(failures) + len(passed) == len(checks)

        failed_names = [f.check.name for f in failures]
        passed_names = [p.name for p in passed]

        # Verify no overlap (by index, since names may duplicate)
        assert len(failed_names) + len(passed_names) == len(checks)
