"""Unit tests for the KnowledgeProvider protocol and NoOpKnowledgeProvider.

Test Spec: TS-114-1 through TS-114-7, TS-114-E1, TS-114-E2
Requirements: 114-REQ-1.1, 114-REQ-1.2, 114-REQ-1.3, 114-REQ-1.4,
              114-REQ-1.E1, 114-REQ-2.1, 114-REQ-2.2, 114-REQ-2.3,
              114-REQ-2.E1
"""

from __future__ import annotations

import inspect
from typing import Any

from agent_fox.knowledge.fox_provider import KnowledgeProvider, NoOpKnowledgeProvider

# ---------------------------------------------------------------------------
# TS-114-1: KnowledgeProvider Protocol Definition
# ---------------------------------------------------------------------------


class TestProtocolDefinition:
    """Verify KnowledgeProvider protocol has correct method signatures.

    Requirements: 114-REQ-1.1
    """

    def test_ingest_method_exists(self) -> None:
        """KnowledgeProvider has an ingest method."""
        assert hasattr(KnowledgeProvider, "ingest")

    def test_ingest_parameter_names(self) -> None:
        """ingest() has (self, session_id, spec_name, context) parameters."""
        sig = inspect.signature(KnowledgeProvider.ingest)
        assert list(sig.parameters.keys()) == ["self", "session_id", "spec_name", "context"]

    def test_ingest_return_annotation(self) -> None:
        """ingest() return annotation is None."""
        sig = inspect.signature(KnowledgeProvider.ingest)
        assert sig.return_annotation is None or sig.return_annotation == "None"

    def test_retrieve_method_exists(self) -> None:
        """KnowledgeProvider has a retrieve method."""
        assert hasattr(KnowledgeProvider, "retrieve")

    def test_retrieve_parameter_names(self) -> None:
        """retrieve() has (self, spec_name, task_description, task_group, session_id) parameters."""
        sig = inspect.signature(KnowledgeProvider.retrieve)
        assert list(sig.parameters.keys()) == [
            "self",
            "spec_name",
            "task_description",
            "task_group",
            "session_id",
        ]

    def test_retrieve_return_annotation(self) -> None:
        """retrieve() return annotation is list[str]."""
        sig = inspect.signature(KnowledgeProvider.retrieve)
        assert sig.return_annotation == list[str] or sig.return_annotation == "list[str]"


# ---------------------------------------------------------------------------
# TS-114-2: KnowledgeProvider Is runtime_checkable
# ---------------------------------------------------------------------------


class TestRuntimeCheckable:
    """Verify KnowledgeProvider is decorated with @runtime_checkable.

    Requirements: 114-REQ-1.2
    """

    def test_isinstance_works_on_conforming_class(self) -> None:
        """isinstance() check works against a conforming class."""

        class Dummy:
            def ingest(self, session_id: str, spec_name: str, context: dict[str, Any]) -> None:
                pass

            def retrieve(self, spec_name: str, task_description: str) -> list[str]:
                return []

        assert isinstance(Dummy(), KnowledgeProvider)


# ---------------------------------------------------------------------------
# TS-114-3: Retrieve Returns list[str]
# ---------------------------------------------------------------------------


class TestRetrieveReturnType:
    """Verify retrieve() return type annotation is list[str].

    Requirements: 114-REQ-1.3
    """

    def test_return_type_is_list_str(self) -> None:
        sig = inspect.signature(KnowledgeProvider.retrieve)
        assert sig.return_annotation == list[str] or sig.return_annotation == "list[str]"


# ---------------------------------------------------------------------------
# TS-114-4: Ingest Accepts Context Dict and Returns None
# ---------------------------------------------------------------------------


class TestIngestSignature:
    """Verify ingest() accepts a context dict and returns None.

    Requirements: 114-REQ-1.4
    """

    def test_context_annotation(self) -> None:
        """context parameter is annotated as dict[str, Any]."""
        sig = inspect.signature(KnowledgeProvider.ingest)
        ann = sig.parameters["context"].annotation
        assert ann == dict[str, Any] or ann == "dict[str, Any]"

    def test_return_is_none(self) -> None:
        """Return annotation is None."""
        sig = inspect.signature(KnowledgeProvider.ingest)
        assert sig.return_annotation is None or sig.return_annotation == "None"


# ---------------------------------------------------------------------------
# TS-114-5: NoOpKnowledgeProvider Satisfies Protocol
# ---------------------------------------------------------------------------


class TestNoOpSatisfiesProtocol:
    """Verify NoOpKnowledgeProvider passes isinstance check against KnowledgeProvider.

    Requirements: 114-REQ-2.1
    """

    def test_isinstance_check(self) -> None:
        noop = NoOpKnowledgeProvider()
        assert isinstance(noop, KnowledgeProvider)


# ---------------------------------------------------------------------------
# TS-114-6: NoOp Ingest Is a No-Op
# ---------------------------------------------------------------------------


class TestNoOpIngest:
    """Verify NoOpKnowledgeProvider.ingest() returns None without side effects.

    Requirements: 114-REQ-2.2
    """

    def test_ingest_returns_none(self) -> None:
        noop = NoOpKnowledgeProvider()
        result = noop.ingest(
            "session-1",
            "spec_01",
            {"touched_files": [], "commit_sha": "", "session_status": "completed"},
        )
        assert result is None


# ---------------------------------------------------------------------------
# TS-114-7: NoOp Retrieve Returns Empty List
# ---------------------------------------------------------------------------


class TestNoOpRetrieve:
    """Verify NoOpKnowledgeProvider.retrieve() returns [].

    Requirements: 114-REQ-2.3
    """

    def test_retrieve_returns_empty_list(self) -> None:
        noop = NoOpKnowledgeProvider()
        result = noop.retrieve("spec_01", "implement feature X")
        assert result == []
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TS-114-E1: Partial Protocol Implementation Fails isinstance
# ---------------------------------------------------------------------------


class TestPartialProtocol:
    """Verify a class with only one protocol method fails isinstance.

    Requirements: 114-REQ-1.E1

    Note: Python's @runtime_checkable Protocol returns False (not TypeError)
    when a required method is missing. This follows the correct behavior
    documented in the test spec (TS-114-E1), addressing the critical finding
    that REQ-1.E1 incorrectly claims TypeError is raised.
    """

    def test_ingest_only_fails(self) -> None:
        """A class with only ingest() does not satisfy KnowledgeProvider."""

        class IngestOnly:
            def ingest(self, session_id: str, spec_name: str, context: dict[str, Any]) -> None:
                pass

        assert not isinstance(IngestOnly(), KnowledgeProvider)

    def test_retrieve_only_fails(self) -> None:
        """A class with only retrieve() does not satisfy KnowledgeProvider."""

        class RetrieveOnly:
            def retrieve(self, spec_name: str, task_description: str) -> list[str]:
                return []

        assert not isinstance(RetrieveOnly(), KnowledgeProvider)


# ---------------------------------------------------------------------------
# TS-114-E2: NoOp Retrieve Accepts Any Arguments
# ---------------------------------------------------------------------------


class TestNoOpAnyArgs:
    """Verify NoOpKnowledgeProvider.retrieve() returns [] for any arguments.

    Requirements: 114-REQ-2.E1
    """

    def test_empty_strings(self) -> None:
        noop = NoOpKnowledgeProvider()
        assert noop.retrieve("", "") == []

    def test_long_strings(self) -> None:
        noop = NoOpKnowledgeProvider()
        assert noop.retrieve("spec_with_unicode_ñ", "very " * 1000) == []

    def test_normal_args(self) -> None:
        noop = NoOpKnowledgeProvider()
        assert noop.retrieve("spec_01", "normal task") == []


# ---------------------------------------------------------------------------
# AC-3 (issue #556): task_group parameter is optional; backward-compat
# ---------------------------------------------------------------------------


class TestTaskGroupOptionalParameter:
    """AC-3: KnowledgeProvider and NoOpKnowledgeProvider accept optional task_group.

    Issue #556: filter findings by task group to avoid injecting noise into
    sessions working on different groups.  The parameter must default to None
    so existing callers that omit it continue to work.
    """

    def test_protocol_has_task_group_parameter(self) -> None:
        """KnowledgeProvider.retrieve() declares task_group parameter."""
        sig = inspect.signature(KnowledgeProvider.retrieve)
        assert "task_group" in sig.parameters

    def test_task_group_defaults_to_none_in_protocol(self) -> None:
        """task_group defaults to None in KnowledgeProvider protocol."""
        sig = inspect.signature(KnowledgeProvider.retrieve)
        param = sig.parameters["task_group"]
        assert param.default is None

    def test_noop_retrieve_without_task_group(self) -> None:
        """NoOpKnowledgeProvider.retrieve() works without task_group."""
        noop = NoOpKnowledgeProvider()
        assert noop.retrieve("s", "d") == []

    def test_noop_retrieve_with_task_group(self) -> None:
        """NoOpKnowledgeProvider.retrieve() works with task_group='1'."""
        noop = NoOpKnowledgeProvider()
        assert noop.retrieve("s", "d", task_group="1") == []

    def test_noop_retrieve_with_none_task_group(self) -> None:
        """NoOpKnowledgeProvider.retrieve() works with task_group=None."""
        noop = NoOpKnowledgeProvider()
        assert noop.retrieve("s", "d", task_group=None) == []

    def test_isinstance_still_satisfied(self) -> None:
        """NoOpKnowledgeProvider still satisfies KnowledgeProvider after the change."""
        noop = NoOpKnowledgeProvider()
        assert isinstance(noop, KnowledgeProvider)
