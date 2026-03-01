"""Prompt builder: construct system and task prompts for coding sessions.

Requirements: 03-REQ-5.1, 03-REQ-5.2
"""

from __future__ import annotations


def build_system_prompt(
    context: str,
    task_group: int,
    spec_name: str,
) -> str:
    """Build the system prompt for a coding session.

    The system prompt instructs the agent to:
    - Act as an expert developer implementing a spec
    - Follow the acceptance criteria in the provided context
    - Work only on the specified task group
    - Commit changes on the current branch
    - Run tests and linters before committing

    Returns the complete system prompt string.
    """
    return (
        f"You are an expert software developer implementing specification "
        f"`{spec_name}`, task group {task_group}.\n"
        f"\n"
        f"## Instructions\n"
        f"\n"
        f"- Implement ONLY task group {task_group} from the tasks listed below.\n"
        f"- Follow the acceptance criteria in the provided context exactly.\n"
        f"- Commit all changes on the current feature branch.\n"
        f"- Run tests and linters before committing to ensure quality.\n"
        f"- Do NOT implement other task groups or make unrelated changes.\n"
        f"\n"
        f"## Context\n"
        f"\n"
        f"{context}\n"
    )


def build_task_prompt(
    task_group: int,
    spec_name: str,
) -> str:
    """Build the task prompt for a coding session.

    The task prompt tells the agent specifically which task group
    to implement, referencing the tasks.md structure.

    Returns the task prompt string.
    """
    return (
        f"Implement task group {task_group} from specification `{spec_name}`.\n"
        f"\n"
        f"Refer to the tasks.md subtask list in the context above for the "
        f"detailed breakdown of work items. Complete all subtasks in group "
        f"{task_group}, update checkbox states in tasks.md, and commit your "
        f"changes on the current branch.\n"
    )
