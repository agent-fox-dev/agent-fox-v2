"""Property tests for allowlist enforcement.

Test Spec: TS-03-P3 (allowlist hook blocks all non-allowlisted commands)
Property: Property 5 from design.md
Requirements: 03-REQ-8.1, 03-REQ-8.2
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.security import DEFAULT_ALLOWLIST, make_pre_tool_use_hook

# Strategy for command-like strings: a first token (no spaces) followed
# by optional arguments
first_token_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="_-./",
    ),
    min_size=1,
    max_size=20,
)


class TestAllowlistBlocksNonAllowlisted:
    """TS-03-P3: Allowlist hook blocks all non-allowlisted commands.

    Property 5: For any command string whose first token is not in the
    allowlist, the hook blocks it.
    """

    @given(first_token=first_token_strategy)
    @settings(max_examples=50)
    def test_non_allowlisted_command_blocked(
        self,
        first_token: str,
    ) -> None:
        """Commands with a first token not in the allowlist are blocked."""
        # Only test tokens that are NOT in the default allowlist
        assume(first_token not in DEFAULT_ALLOWLIST)
        assume(first_token.strip())  # skip empty/whitespace

        config = AgentFoxConfig()
        hook = make_pre_tool_use_hook(config.security)

        command = f"{first_token} --some-arg value"
        result = hook(tool_name="Bash", tool_input={"command": command})
        assert result.get("decision") == "block", f"Command '{command}' should be blocked but was not"

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
    def test_allowlisted_command_not_blocked(
        self,
        cmd: str,
        args: str,
    ) -> None:
        """Commands with a first token in the allowlist are not blocked.

        Args are restricted to safe characters (no shell operators like
        pipes, semicolons, subshells, or redirects).
        """
        config = AgentFoxConfig()
        hook = make_pre_tool_use_hook(config.security)

        command = f"{cmd} {args}".strip()
        result = hook(tool_name="Bash", tool_input={"command": command})
        assert result.get("decision") != "block", f"Command '{command}' should be allowed but was blocked"
