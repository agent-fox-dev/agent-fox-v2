"""LLM-powered contradiction classification for fact pairs.

Requirements: 90-REQ-2.2, 90-REQ-2.5, 90-REQ-2.E1, 90-REQ-2.E3
"""

from __future__ import annotations

from agent_fox.knowledge.lifecycle import ContradictionVerdict

CONTRADICTION_PROMPT = """You are a knowledge base curator. For each pair of facts below, determine
whether the NEW fact contradicts the OLD fact. A contradiction means the
new fact makes the old fact incorrect, outdated, or misleading.

Respond with ONLY a JSON array. For each pair, return:
{{"pair_index": <N>, "contradicts": true/false, "reason": "..."}}

Pairs:
{pairs}"""


async def classify_contradiction_batch(
    pairs: list[tuple],
    model: str = "SIMPLE",
) -> list[ContradictionVerdict]:
    """Classify a batch of fact pairs for contradiction via LLM.

    Requirements: 90-REQ-2.2, 90-REQ-2.5
    """
    raise NotImplementedError("classify_contradiction_batch not yet implemented")
