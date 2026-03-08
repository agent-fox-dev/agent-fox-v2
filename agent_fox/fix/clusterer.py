"""Failure clustering.

Groups failures by likely root cause using AI-assisted semantic grouping
(primary) or fallback one-cluster-per-check grouping.

Requirements: 08-REQ-3.1, 08-REQ-3.2, 08-REQ-3.3
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass

from agent_fox.core.client import create_anthropic_client
from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.models import resolve_model
from agent_fox.fix.checks import FailureRecord

logger = logging.getLogger(__name__)

# Maximum characters of failure output to include per failure in the AI prompt
_MAX_OUTPUT_CHARS = 2000


@dataclass
class FailureCluster:
    """A group of failures believed to share a common root cause."""

    label: str  # Descriptive label for the root cause
    failures: list[FailureRecord]  # Failure records in this cluster
    suggested_approach: str  # Suggested fix approach


def cluster_failures(
    failures: list[FailureRecord],
    config: AgentFoxConfig,
) -> list[FailureCluster]:
    """Group failures by likely root cause.

    Primary: Send failure outputs to STANDARD model, ask it to group by
    root cause and suggest fix approaches. Parse structured response.

    Fallback (AI unavailable): One cluster per check command, using the
    check name as the cluster label.
    """
    try:
        return _ai_cluster(failures, config)
    except Exception:
        logger.warning("AI clustering unavailable, falling back to per-check grouping")
        return _fallback_cluster(failures)


def _ai_cluster(
    failures: list[FailureRecord],
    config: AgentFoxConfig,
) -> list[FailureCluster]:
    """Use AI model to semantically cluster failures.

    Builds a numbered prompt with truncated failure outputs, sends it to the
    STANDARD model tier via the Anthropic SDK, and parses the JSON response
    into FailureCluster objects.

    Falls back to _fallback_cluster on any error (API, parse, validation).
    """
    # 08-REQ-3.1: use STANDARD tier for clustering
    model_entry = resolve_model("STANDARD")

    # Build the clustering prompt
    prompt = _build_clustering_prompt(failures)

    # Call the Anthropic API
    client = create_anthropic_client()
    response = client.messages.create(
        model=model_entry.model_id,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract the text response
    content_block = response.content[0]
    if not hasattr(content_block, "text"):
        raise ValueError("AI response did not contain a text block")
    response_text: str = content_block.text  # type: ignore[union-attr]

    # Parse the JSON response
    return _parse_ai_response(response_text, failures)


def _build_clustering_prompt(failures: list[FailureRecord]) -> str:
    """Build the AI clustering prompt with numbered failure outputs."""
    lines = [
        "You are analyzing quality check failures from a software project.",
        "Group the following failures by their likely root cause.",
        "",
        "For each group, provide:",
        "1. A short descriptive label for the root cause",
        "2. Which failure indices belong to the group",
        "3. A suggested approach for fixing the group",
        "",
        "Failures:",
    ]

    for i, failure in enumerate(failures):
        # Truncate output to _MAX_OUTPUT_CHARS
        output = failure.output[:_MAX_OUTPUT_CHARS]
        lines.append(
            f"[{i}] Check: {failure.check.name} | Exit code: {failure.exit_code}"
        )
        lines.append(f"Output: {output}")
        lines.append("")

    lines.extend(
        [
            "Respond in JSON format:",
            "{",
            '  "groups": [',
            "    {",
            '      "label": "Short descriptive label",',
            '      "failure_indices": [0, 1],',
            '      "suggested_approach": "Description of how to fix..."',
            "    }",
            "  ]",
            "}",
        ]
    )

    return "\n".join(lines)


def _parse_ai_response(
    response_text: str,
    failures: list[FailureRecord],
) -> list[FailureCluster]:
    """Parse the AI model's JSON response into FailureCluster objects.

    Validates that:
    - The response is valid JSON
    - It contains a 'groups' key with a list
    - Each group has label, failure_indices, and suggested_approach
    - All failure indices are valid and cover all failures
    - No failure index is duplicated

    Raises ValueError if validation fails (caller should fall back).
    """
    data = json.loads(response_text)

    if "groups" not in data or not isinstance(data["groups"], list):
        raise ValueError("Response missing 'groups' list")

    clusters: list[FailureCluster] = []
    seen_indices: set[int] = set()

    for group in data["groups"]:
        label = group.get("label", "")
        indices = group.get("failure_indices", [])
        approach = group.get("suggested_approach", "")

        if not label or not isinstance(indices, list) or not approach:
            raise ValueError(f"Invalid group structure: {group}")

        # Validate indices
        for idx in indices:
            if not isinstance(idx, int) or idx < 0 or idx >= len(failures):
                raise ValueError(f"Invalid failure index: {idx}")
            if idx in seen_indices:
                raise ValueError(f"Duplicate failure index: {idx}")
            seen_indices.add(idx)

        cluster_failures_list = [failures[idx] for idx in indices]
        clusters.append(
            FailureCluster(
                label=label,
                failures=cluster_failures_list,
                suggested_approach=approach,
            )
        )

    # Verify all failures are accounted for
    if seen_indices != set(range(len(failures))):
        raise ValueError(
            f"Not all failures covered: expected {set(range(len(failures)))}, "
            f"got {seen_indices}"
        )

    return clusters


# -- Generic category descriptions for fallback clustering --------------------

_CATEGORY_APPROACHES: dict[str, str] = {
    "test": (
        "Investigate test failures, fix the failing test cases or the code under test."
    ),
    "lint": "Fix linting violations reported by the checker.",
    "type": ("Add or fix type annotations to resolve type-checking errors."),
    "build": ("Resolve build errors by fixing compilation or packaging issues."),
}

_DEFAULT_APPROACH = "Investigate and fix the reported issues."


def _fallback_cluster(failures: list[FailureRecord]) -> list[FailureCluster]:
    """Group failures by check command (one cluster per check).

    Groups failures by check name, using the check name as the cluster label
    and a generic message per check category as the suggested approach.
    """
    groups: dict[str, list[FailureRecord]] = defaultdict(list)

    for failure in failures:
        groups[failure.check.name].append(failure)

    clusters: list[FailureCluster] = []
    for check_name, group_failures in groups.items():
        # Use the category of the first failure in the group for the approach
        category = group_failures[0].check.category.value
        approach = _CATEGORY_APPROACHES.get(category, _DEFAULT_APPROACH)

        clusters.append(
            FailureCluster(
                label=check_name,
                failures=group_failures,
                suggested_approach=approach,
            )
        )

    return clusters
