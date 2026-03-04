"""CLI utilities shared across commands."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import click

from agent_fox.core.errors import AgentFoxError


def handle_agent_fox_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that catches AgentFoxError and exits with code 1.

    Reduces the repeated try/except AgentFoxError pattern across CLI
    commands. The decorated function must receive a Click context as
    its first positional argument (``ctx``).
    """

    @functools.wraps(fn)
    def wrapper(ctx: click.Context, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(ctx, *args, **kwargs)
        except AgentFoxError as exc:
            click.echo(f"Error: {exc}", err=True)
            ctx.exit(1)

    return wrapper
