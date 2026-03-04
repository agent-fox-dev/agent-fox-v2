"""Error hierarchy tests.

Test Spec: TS-01-11 (hierarchy check)
Requirements: 01-REQ-4.1, 01-REQ-4.2, 01-REQ-4.3
"""

from __future__ import annotations

import pytest

from agent_fox.core.errors import (
    AgentFoxError,
    ConfigError,
    CostLimitError,
    HookError,
    InitError,
    IntegrationError,
    PlanError,
    SecurityError,
    SessionError,
    SessionTimeoutError,
    WorkspaceError,
)

ALL_ERROR_CLASSES = [
    ConfigError,
    InitError,
    PlanError,
    SessionError,
    WorkspaceError,
    IntegrationError,
    HookError,
    SessionTimeoutError,
    CostLimitError,
    SecurityError,
]


class TestErrorHierarchy:
    """TS-01-11: Error hierarchy completeness."""

    @pytest.mark.parametrize("error_class", ALL_ERROR_CLASSES)
    def test_subclass_of_agent_fox_error(
        self, error_class: type[AgentFoxError]
    ) -> None:
        """Each error class is a subclass of AgentFoxError."""
        assert issubclass(error_class, AgentFoxError)

    @pytest.mark.parametrize("error_class", ALL_ERROR_CLASSES)
    def test_instance_caught_by_base(self, error_class: type[AgentFoxError]) -> None:
        """Each error instance can be caught by `except AgentFoxError`."""
        instance = error_class("test error message")
        assert isinstance(instance, AgentFoxError)

    @pytest.mark.parametrize("error_class", ALL_ERROR_CLASSES)
    def test_carries_message(self, error_class: type[AgentFoxError]) -> None:
        """Each error carries a human-readable message."""
        instance = error_class("something went wrong")
        assert str(instance) == "something went wrong"

    def test_base_error_has_context(self) -> None:
        """AgentFoxError carries optional structured context."""
        error = AgentFoxError("test", field="parallel", value=99)
        assert error.context == {"field": "parallel", "value": 99}

    def test_subclass_inherits_context(self) -> None:
        """Subclass errors also carry context kwargs."""
        error = ConfigError("bad value", field="parallel")
        assert error.context["field"] == "parallel"

    def test_base_error_is_exception(self) -> None:
        """AgentFoxError is a subclass of Exception."""
        assert issubclass(AgentFoxError, Exception)
