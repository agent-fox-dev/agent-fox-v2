"""Construct coder session prompts with stub constraint directives.

Requirements: 87-REQ-1.1, 87-REQ-2.3, 87-REQ-5.1
"""

from __future__ import annotations

from agent_fox.scope_guard.models import (
    Deliverable,
    DeliverableStatus,
    ScopeCheckResult,
    TaskGroup,
)

_STUB_DIRECTIVE = """\
<!-- SCOPE_GUARD:STUB_ONLY -->
CONSTRAINT: For all non-test source code, produce ONLY type signatures and stub \
bodies. Stub bodies must consist solely of a placeholder expression:
- Rust: todo!(), unimplemented!(), or panic!("not implemented")
- Python: raise NotImplementedError or pass (as the sole statement)
- TypeScript/JavaScript: throw new Error("not implemented")
Do NOT implement any business logic in non-test code.
<!-- /SCOPE_GUARD:STUB_ONLY -->"""


def build_prompt(
    task_group: TaskGroup, scope_result: ScopeCheckResult | None = None
) -> str:
    """Build a coder session prompt for the given task group.

    For test-writing archetypes the prompt includes the ``SCOPE_GUARD:STUB_ONLY``
    directive block constraining the agent to stub-only output for non-test code
    (87-REQ-1.1, 87-REQ-5.1).

    When *scope_result* indicates a partially-implemented task group, the prompt
    lists only pending deliverables as work items and already-implemented ones as
    context (87-REQ-2.3).
    """
    sections: list[str] = []

    # Header
    sections.append(
        f"# Coder Session Prompt — Spec {task_group.spec_number}, "
        f"Task Group {task_group.number}"
    )
    sections.append(f"Archetype: {task_group.archetype}")

    # Stub directive for test-writing archetypes
    if task_group.archetype == "test-writing":
        sections.append("")
        sections.append(_STUB_DIRECTIVE)

    # Determine pending vs already-implemented deliverables
    pending, implemented = _split_deliverables(task_group, scope_result)

    # Work section — pending deliverables
    sections.append("")
    sections.append("## Work Items")
    if pending:
        for d in pending:
            sections.append(f"- [ ] `{d.function_id}` in `{d.file_path}`")
    else:
        sections.append("No pending deliverables.")

    # Context section — already-implemented deliverables
    if implemented:
        sections.append("")
        sections.append("## Already Implemented (context only — do not re-implement)")
        for d in implemented:
            sections.append(f"- `{d.function_id}` in `{d.file_path}`")

    return "\n".join(sections)


def _filter_pending_deliverables(
    scope_result: ScopeCheckResult,
) -> list[Deliverable]:
    """Return only deliverables whose status is PENDING."""
    return [
        dr.deliverable
        for dr in scope_result.deliverable_results
        if dr.status == DeliverableStatus.PENDING
    ]


def _split_deliverables(
    task_group: TaskGroup, scope_result: ScopeCheckResult | None
) -> tuple[list[Deliverable], list[Deliverable]]:
    """Split deliverables into (pending, already_implemented) lists.

    When no *scope_result* is provided, all deliverables are treated as pending.
    """
    if scope_result is None:
        return task_group.deliverables, []

    pending: list[Deliverable] = []
    implemented: list[Deliverable] = []
    for dr in scope_result.deliverable_results:
        if dr.status == DeliverableStatus.ALREADY_IMPLEMENTED:
            implemented.append(dr.deliverable)
        else:
            # PENDING and INDETERMINATE both go into the work list
            pending.append(dr.deliverable)

    return pending, implemented
