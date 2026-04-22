"""KnowledgeProvider protocol and NoOpKnowledgeProvider implementation.

Defines the clean boundary between the engine and any knowledge implementation.
The engine calls retrieve() pre-session and ingest() post-session through
the protocol --- never importing knowledge internals directly.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class KnowledgeProvider(Protocol):
    """Protocol defining the interface between the engine and a knowledge implementation.

    Any class that implements both ``ingest`` and ``retrieve`` with the
    correct signatures satisfies this protocol at runtime (``isinstance``
    check) thanks to the ``@runtime_checkable`` decorator.
    """

    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict[str, Any],
    ) -> None:
        """Ingest knowledge from a completed session.

        Args:
            session_id: Node ID of the completed session.
            spec_name: Name of the spec the session belongs to.
            context: Dict with at minimum ``touched_files`` (list[str]),
                     ``commit_sha`` (str), ``session_status`` (str).
        """
        ...

    def retrieve(
        self,
        spec_name: str,
        task_description: str,
    ) -> list[str]:
        """Retrieve knowledge context for an upcoming session.

        Args:
            spec_name: Name of the spec being worked on.
            task_description: Human-readable description of the task.

        Returns:
            List of formatted text blocks ready for prompt injection.
            Empty list means no knowledge context.
        """
        ...


class NoOpKnowledgeProvider:
    """Knowledge provider that does nothing.

    Default implementation used when no knowledge system is configured.
    ``ingest()`` is a no-op and ``retrieve()`` always returns an empty list.
    """

    def ingest(
        self,
        session_id: str,
        spec_name: str,
        context: dict[str, Any],
    ) -> None:
        """Accept and discard session knowledge context."""
        return None

    def retrieve(
        self,
        spec_name: str,
        task_description: str,
    ) -> list[str]:
        """Return an empty list --- no knowledge is available."""
        return []
