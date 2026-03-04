"""Property tests for platform integration.

Test Spec: TS-10-P1 (NullPlatform gates always pass),
           TS-10-P2 (NullPlatform create_pr returns empty),
           TS-10-P3 (factory rejects unknown types)
Properties: Property 1, Property 2, Property 3 from design.md
Requirements: 10-REQ-2.2, 10-REQ-2.3, 10-REQ-2.4, 10-REQ-5.E1
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import PlatformConfig
from agent_fox.core.errors import ConfigError
from agent_fox.platform.factory import create_platform
from agent_fox.platform.null import NullPlatform


class TestNullPlatformGatesAlwaysPass:
    """TS-10-P1: NullPlatform gates always pass.

    Property 1: For any call to NullPlatform.wait_for_ci() or
    NullPlatform.wait_for_review(), the return value SHALL be True.
    Validates: 10-REQ-2.3, 10-REQ-2.4
    """

    @given(
        timeout=st.integers(min_value=0, max_value=100_000),
        pr_url=st.text(max_size=200),
    )
    @settings(max_examples=50)
    async def test_wait_for_ci_always_true(
        self,
        timeout: int,
        pr_url: str,
    ) -> None:
        """wait_for_ci returns True for any timeout and pr_url."""
        null = NullPlatform()
        result = await null.wait_for_ci(pr_url, timeout)
        assert result is True

    @given(pr_url=st.text(max_size=200))
    @settings(max_examples=50)
    async def test_wait_for_review_always_true(self, pr_url: str) -> None:
        """wait_for_review returns True for any pr_url."""
        null = NullPlatform()
        result = await null.wait_for_review(pr_url)
        assert result is True


class TestNullPlatformCreatePrReturnsEmpty:
    """TS-10-P2: NullPlatform create_pr returns empty string.

    Property 2: For any call to NullPlatform.create_pr(), the return
    value SHALL be an empty string.
    Validates: 10-REQ-2.2
    """

    @given(
        branch=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_-/.",
            ),
            min_size=1,
            max_size=50,
        ),
        title=st.text(max_size=100),
        body=st.text(max_size=200),
        labels=st.lists(st.text(max_size=20), max_size=5),
    )
    @settings(max_examples=30)
    async def test_create_pr_returns_empty(
        self,
        branch: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> None:
        """create_pr returns empty string for any valid inputs."""
        with patch(
            "agent_fox.platform.null.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
        ):
            null = NullPlatform()
            result = await null.create_pr(branch, title, body, labels)
            assert result == ""


class TestFactoryRejectsUnknownTypes:
    """TS-10-P3: Factory rejects unknown platform types.

    Property 3: Any platform type not in {"none", "github"} raises
    ConfigError from create_platform().
    Validates: 10-REQ-5.E1
    """

    @given(
        type_str=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_-",
            ),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(max_examples=50)
    def test_unknown_type_raises_config_error(self, type_str: str) -> None:
        """create_platform raises ConfigError for any non-valid type."""
        assume(type_str not in ("none", "github"))
        config = PlatformConfig(type=type_str)
        with pytest.raises(ConfigError):
            create_platform(config)
