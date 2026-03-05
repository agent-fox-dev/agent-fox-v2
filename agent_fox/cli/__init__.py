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

    In JSON mode (``ctx.obj["json"]``), the error is emitted as a
    JSON envelope to stdout instead of plain text to stderr.
    """

    @functools.wraps(fn)
    def wrapper(ctx: click.Context, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(ctx, *args, **kwargs)
        except AgentFoxError as exc:
            if ctx.obj and ctx.obj.get("json"):
                from agent_fox.cli.json_io import emit_error

                emit_error(str(exc))
                ctx.exit(1)
                return
            click.echo(f"Error: {exc}", err=True)
            ctx.exit(1)

    return wrapper
