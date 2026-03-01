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
    raise NotImplementedError


def build_task_prompt(
    task_group: int,
    spec_name: str,
) -> str:
    """Build the task prompt for a coding session.

    The task prompt tells the agent specifically which task group
    to implement, referencing the tasks.md structure.

    Returns the task prompt string.
    """
    raise NotImplementedError
