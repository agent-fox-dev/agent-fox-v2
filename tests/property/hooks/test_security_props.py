"""Property tests for command allowlist security.

Test Spec: TS-06-P1 (allowlist enforcement completeness),
           TS-06-P2 (default allowlist stability)
Properties: Property 1, Property 3 from design.md
Requirements: 06-REQ-8.1, 06-REQ-8.2, 06-REQ-8.3, 06-REQ-9.1, 06-REQ-9.2
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import SecurityConfig
from agent_fox.core.errors import SecurityError
from agent_fox.hooks.security import (
    DEFAULT_ALLOWLIST,
    build_effective_allowlist,
    check_command_allowed,
    check_shell_operators,
    extract_command_name,
)

# Strategy for command-like strings: a first token (no spaces) followed
# by optional arguments
_first_token = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="_-./",
    ),
    min_size=1,
    max_size=30,
)

_allowlist = st.frozensets(
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            whitelist_characters="_-",
        ),
        min_size=1,
        max_size=15,
    ),
    min_size=1,
    max_size=20,
)


class TestAllowlistEnforcementCompleteness:
    """TS-06-P1: Allowlist enforcement completeness.

    Property 1: Every non-empty command string is deterministically
    allowed or blocked based on the allowlist. A command is allowed
    if and only if its extracted name is in the allowlist.
    """

    @given(cmd=_first_token, allowlist=_allowlist)
    @settings(max_examples=100)
    def test_allowed_iff_name_in_allowlist(
        self,
        cmd: str,
        allowlist: frozenset[str],
    ) -> None:
        """check_command_allowed returns True iff extracted name is in allowlist."""
        assume(cmd.strip())  # skip empty/whitespace

        try:
            name = extract_command_name(cmd)
        except SecurityError:
            # Empty/whitespace commands are handled separately
            return

        allowed, _ = check_command_allowed(cmd, allowlist)
        assert allowed == (name in allowlist and check_shell_operators(cmd) is None), (
            f"Expected allowed={name in allowlist and check_shell_operators(cmd) is None} "
            f"for command '{cmd}' "
            f"(extracted name='{name}') with allowlist={allowlist!r}"
        )

    @given(
        cmd=st.sampled_from(sorted(DEFAULT_ALLOWLIST)),
        args=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters=" _-./=%",
            ),
            max_size=30,
        ),
    )
    @settings(max_examples=50)
    def test_default_allowlisted_commands_always_allowed(
        self,
        cmd: str,
        args: str,
    ) -> None:
        """Commands from DEFAULT_ALLOWLIST are allowed with safe args.

        Args are restricted to characters that don't contain shell operators
        (pipes, semicolons, subshells, redirects, etc.).
        """
        command = f"{cmd} {args}".strip()
        allowed, _ = check_command_allowed(command, DEFAULT_ALLOWLIST)
        assert allowed is True, f"Command '{command}' should be allowed but was blocked"


class TestDefaultAllowlistStability:
    """TS-06-P2: Default allowlist stability.

    Property 3: Default configuration always yields the default allowlist.
    """

    def test_default_config_yields_default_allowlist(self) -> None:
        """SecurityConfig() -> build_effective_allowlist == DEFAULT_ALLOWLIST."""
        config = SecurityConfig()
        result = build_effective_allowlist(config)
        assert result == DEFAULT_ALLOWLIST

    @given(
        extend=st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N")),
                min_size=1,
                max_size=10,
            ),
            max_size=10,
        ),
    )
    @settings(max_examples=30)
    def test_extend_is_superset_of_default(
        self,
        extend: list[str],
    ) -> None:
        """bash_allowlist_extend always produces a superset of defaults."""
        config = SecurityConfig(bash_allowlist_extend=extend)
        result = build_effective_allowlist(config)
        assert DEFAULT_ALLOWLIST.issubset(result), (
            f"Expected DEFAULT_ALLOWLIST ⊂ result, but missing: {DEFAULT_ALLOWLIST - result}"
        )

    @given(
        replacement=st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N")),
                min_size=1,
                max_size=10,
            ),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=30)
    def test_replacement_exactly_matches_input(
        self,
        replacement: list[str],
    ) -> None:
        """bash_allowlist replaces defaults exactly."""
        config = SecurityConfig(bash_allowlist=replacement)
        result = build_effective_allowlist(config)
        assert result == frozenset(replacement), f"Expected {frozenset(replacement)}, got {result}"
