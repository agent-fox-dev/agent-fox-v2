"""Unit tests for WorkStream protocol definition.

Test Spec: TS-85-1
Requirements: 85-REQ-1.1
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-85-1: WorkStream protocol attributes
# Requirement: 85-REQ-1.1
# ---------------------------------------------------------------------------


class TestWorkStreamProtocol:
    """Verify that WorkStream protocol requires name, interval, enabled, run_once, shutdown."""

    def test_complete_implementation_passes_isinstance(self) -> None:
        """A class implementing all WorkStream attributes passes isinstance check."""
        from agent_fox.nightshift.stream import WorkStream

        class CompleteStream:
            @property
            def name(self) -> str:
                return "test"

            @property
            def interval(self) -> int:
                return 60

            @property
            def enabled(self) -> bool:
                return True

            async def run_once(self) -> None:
                pass

            async def shutdown(self) -> None:
                pass

        obj = CompleteStream()
        assert isinstance(obj, WorkStream)

    def test_incomplete_implementation_fails_isinstance(self) -> None:
        """A class missing run_once fails isinstance check."""
        from agent_fox.nightshift.stream import WorkStream

        class IncompleteStream:
            @property
            def name(self) -> str:
                return "test"

            @property
            def interval(self) -> int:
                return 60

            @property
            def enabled(self) -> bool:
                return True

            async def shutdown(self) -> None:
                pass

        obj = IncompleteStream()
        assert not isinstance(obj, WorkStream)

    def test_complete_stream_attributes(self) -> None:
        """Complete stream exposes correct attribute values."""
        from agent_fox.nightshift.stream import WorkStream

        class CompleteStream:
            @property
            def name(self) -> str:
                return "test"

            @property
            def interval(self) -> int:
                return 60

            @property
            def enabled(self) -> bool:
                return True

            async def run_once(self) -> None:
                pass

            async def shutdown(self) -> None:
                pass

        obj = CompleteStream()
        assert isinstance(obj, WorkStream)
        assert obj.name == "test"
        assert obj.interval == 60
        assert obj.enabled is True
