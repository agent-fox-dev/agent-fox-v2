"""Centralised label constants for agent-fox platform operations.

The nightshift pipeline requires these labels to exist on the target
repository before it can assign them to issues. Use the REQUIRED_LABELS
list with ``platform.create_label`` (called automatically by ``af init``)
to ensure they are present.

Requirements: 358-REQ-1, 358-REQ-2, 358-REQ-3
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Label name constants
# ---------------------------------------------------------------------------

#: Applied to issues managed by the fix pipeline.
LABEL_FIX: str = "af:fix"

#: Applied to issues created by hunt scans (dedup fingerprint label).
LABEL_HUNT: str = "af:hunt"


# ---------------------------------------------------------------------------
# Label metadata for idempotent creation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelSpec:
    """Specification for a platform label to be created on init."""

    name: str
    color: str  # 6-character hex without leading #
    description: str


#: Labels that must exist on the target repository for nightshift to operate.
REQUIRED_LABELS: list[LabelSpec] = [
    LabelSpec(
        name=LABEL_FIX,
        color="12ec39",
        description="Issues ready to be implemented by the fix pipeline",
    ),
    LabelSpec(
        name=LABEL_HUNT,
        color="0075ca",
        description="Issues created by hunt scans",
    ),
]
