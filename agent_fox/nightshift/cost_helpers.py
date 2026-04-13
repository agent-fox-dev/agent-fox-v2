"""Auxiliary AI cost emission helper for night-shift modules.

Emits session.complete audit events for direct Anthropic API calls that
don't go through run_session(). Examples: finding consolidation critic,
batch triage, staleness check, quality gate analysis.

Also provides :func:`nightshift_ai_call`, a high-level async AI call
helper that wraps :func:`~agent_fox.core.client.ai_call` with
cost emission on success and failure.

Requirements: 91-REQ-4.1, 91-REQ-4.2, 91-REQ-4.3, 91-REQ-4.4, 91-REQ-4.E1
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_fox.core.config import PricingConfig
    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger(__name__)


def emit_auxiliary_cost(
    sink: SinkDispatcher | None,
    run_id: str,
    archetype: str,
    response: object,
    model_id: str,
    pricing: PricingConfig,
    *,
    node_id: str = "",
) -> None:
    """Emit a session.complete audit event for an auxiliary AI call.

    Extracts token usage from the Anthropic API response object,
    calculates USD cost, and emits a session.complete event via the
    standard audit helper.

    No-op when sink is None or run_id is empty.

    Requirements: 91-REQ-4.1, 91-REQ-4.2, 91-REQ-4.3, 91-REQ-4.4, 91-REQ-4.E1
    """
    if sink is None or not run_id:
        return

    try:
        from agent_fox.core.models import calculate_cost
        from agent_fox.engine.audit_helpers import emit_audit_event
        from agent_fox.knowledge.audit import AuditEventType

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage is not None else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage is not None else 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) if usage is not None else 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) if usage is not None else 0

        # Use the provided pricing; if model is not found there (cost==0),
        # fall back to PricingConfig() which has the standard default rates.
        cost = calculate_cost(
            input_tokens,
            output_tokens,
            model_id,
            pricing,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        )
        if cost == 0.0 and (input_tokens > 0 or output_tokens > 0):
            from agent_fox.core.config import PricingConfig

            cost = calculate_cost(
                input_tokens,
                output_tokens,
                model_id,
                PricingConfig(),
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=cache_creation,
            )

        emit_audit_event(
            sink,
            run_id,
            AuditEventType.SESSION_COMPLETE,
            node_id=node_id,
            archetype=archetype,
            payload={
                "archetype": archetype,
                "model_id": model_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
                "cost": cost,
            },
        )
    except Exception:
        logger.debug(
            "Failed to emit auxiliary cost for archetype %s",
            archetype,
            exc_info=True,
        )


def emit_auxiliary_cost_fail(
    sink: SinkDispatcher | None,
    run_id: str,
    archetype: str,
    error: Exception,
    model_id: str,
    *,
    node_id: str = "",
) -> None:
    """Emit a session.fail audit event for a failed auxiliary AI call.

    No-op when sink is None or run_id is empty.

    Requirements: 91-REQ-4.5
    """
    if sink is None or not run_id:
        return

    try:
        from agent_fox.engine.audit_helpers import emit_audit_event
        from agent_fox.knowledge.audit import AuditEventType

        emit_audit_event(
            sink,
            run_id,
            AuditEventType.SESSION_FAIL,
            node_id=node_id,
            archetype=archetype,
            payload={
                "archetype": archetype,
                "model_id": model_id,
                "error_message": str(error),
            },
        )
    except Exception:
        logger.debug(
            "Failed to emit auxiliary cost fail for archetype %s",
            archetype,
            exc_info=True,
        )


async def nightshift_ai_call(
    *,
    model_tier: str,
    max_tokens: int,
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]] | None = None,
    context: str,
    cost_label: str,
    config: object,
    sink: SinkDispatcher | None = None,
    run_id: str = "",
) -> tuple[str | None, Any]:
    """Async AI call with nightshift cost tracking.

    Wraps :func:`~agent_fox.core.client.ai_call` and emits
    ``emit_auxiliary_cost`` on success or ``emit_auxiliary_cost_fail``
    on API failure.

    Returns:
        A tuple of (response_text_or_none, raw_response).
    """
    from agent_fox.core.client import ai_call
    from agent_fox.core.config import PricingConfig
    from agent_fox.core.models import resolve_model

    model_entry = resolve_model(model_tier)

    try:
        text, response = await ai_call(
            model_tier=model_tier,
            max_tokens=max_tokens,
            messages=messages,
            system=system,
            context=context,
        )
    except Exception as exc:
        emit_auxiliary_cost_fail(sink, run_id, cost_label, exc, model_entry.model_id)
        raise

    pricing = getattr(config, "pricing", PricingConfig())
    emit_auxiliary_cost(sink, run_id, cost_label, response, model_entry.model_id, pricing)
    return text, response
