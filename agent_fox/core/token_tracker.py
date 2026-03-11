"""Token accumulator for auxiliary LLM calls.

Thread-safe accumulator that records token usage from auxiliary LLM calls
(memory extraction, causal link analysis, spec validation, etc.) so that
reported costs reflect actual consumption.

Requirements: 34-REQ-1.1, 34-REQ-1.2
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """A single auxiliary LLM call's token usage."""

    input_tokens: int
    output_tokens: int
    model: str


class TokenAccumulator:
    """Thread-safe accumulator for auxiliary LLM token usage.

    Module-level singleton. Call sites use the module functions
    directly — no need to pass the accumulator around.
    """

    def __init__(self) -> None:
        self._usages: list[TokenUsage] = []
        self._lock = threading.Lock()

    def record(self, input_tokens: int, output_tokens: int, model: str) -> None:
        """Record token usage from an auxiliary LLM call."""
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
        )
        with self._lock:
            self._usages.append(usage)
        logger.debug(
            "Recorded auxiliary tokens: %d in, %d out, model=%s",
            input_tokens,
            output_tokens,
            model,
        )

    def flush(self) -> list[TokenUsage]:
        """Return all recorded usages and reset the accumulator."""
        with self._lock:
            entries = list(self._usages)
            self._usages.clear()
        if entries:
            total_in = sum(e.input_tokens for e in entries)
            total_out = sum(e.output_tokens for e in entries)
            logger.info(
                "Flushed %d auxiliary token entries: %d in, %d out",
                len(entries),
                total_in,
                total_out,
            )
        return entries

    def total(self) -> tuple[int, int]:
        """Return (total_input_tokens, total_output_tokens) without flushing."""
        with self._lock:
            total_in = sum(e.input_tokens for e in self._usages)
            total_out = sum(e.output_tokens for e in self._usages)
        return total_in, total_out

    def reset(self) -> None:
        """Reset the accumulator, discarding all recorded usages."""
        with self._lock:
            self._usages.clear()


# Module-level singleton
_global_accumulator = TokenAccumulator()


def record_auxiliary_usage(
    input_tokens: int, output_tokens: int, model: str
) -> None:
    """Record auxiliary token usage to the global accumulator."""
    _global_accumulator.record(input_tokens, output_tokens, model)


def flush_auxiliary_usage() -> list[TokenUsage]:
    """Flush and return all accumulated auxiliary usages."""
    return _global_accumulator.flush()


def get_auxiliary_totals() -> tuple[int, int]:
    """Get current auxiliary totals without flushing."""
    return _global_accumulator.total()
