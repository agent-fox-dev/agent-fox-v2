"""Backward-compatible re-export of archetype registry.

The canonical definitions now live in ``agent_fox.archetypes`` to avoid
cross-module coupling between ``graph`` and ``session``.
"""

from agent_fox.archetypes import (  # noqa: F401
    ARCHETYPE_REGISTRY,
    ArchetypeEntry,
    get_archetype,
)

__all__ = ["ARCHETYPE_REGISTRY", "ArchetypeEntry", "get_archetype"]
