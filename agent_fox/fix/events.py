"""Event dataclasses for fix command progress reporting.

FixProgressEvent and CheckEvent are transient in-memory event objects used
to communicate progress from the fix/improve loops to the CLI display layer.
All parameters default to None for full backward compatibility — existing
callers that do not pass callbacks are unaffected.

Requirements: 76-REQ-4.*, 76-REQ-5.*, 76-REQ-6.*
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FixProgressEvent:
    """Progress event from the fix or improve loop.

    Emitted at key lifecycle points (pass start/end, session start/end, etc.)
    and forwarded to the CLI display layer via a progress_callback.
    """

    phase: str  # "repair" (fix loop) or "improve" (improve loop)
    pass_number: int  # current pass, 1-indexed
    max_passes: int  # configured maximum passes
    stage: str  # event stage identifier; one of:
    #   "checks_start"   — pass beginning, about to run quality checks
    #   "all_passed"     — all checks returned exit 0
    #   "clusters_found" — failures clustered; detail contains cluster count
    #   "session_start"  — fix session starting; detail contains cluster label
    #   "session_done"   — fix session completed successfully
    #   "session_error"  — fix session raised an exception
    #   "cost_limit"     — cost budget exhausted; loop terminating
    #   "analyzer_start" — improve analyzer session starting
    #   "analyzer_done"  — improve analyzer session completed
    #   "coder_start"    — improve coder session starting
    #   "coder_done"     — improve coder session completed
    #   "verifier_start" — improve verifier session starting
    #   "verifier_pass"  — improve verifier returned PASS
    #   "verifier_fail"  — improve verifier returned FAIL (rollback triggered)
    #   "converged"      — analyzer detected diminishing returns or zero improvements
    detail: str = ""  # human-readable supplementary info (cluster label, counts, etc.)


# Type alias for the fix/improve loop progress callback.
FixProgressCallback = Callable[[FixProgressEvent], None]


@dataclass(frozen=True, slots=True)
class CheckEvent:
    """Progress event from a single quality check execution.

    Emitted twice per check: once before execution (stage="start") and once
    after execution (stage="done"), even on timeout or failure.
    """

    check_name: str  # e.g. "ruff", "pytest", "cargo test"
    stage: str  # "start" or "done"
    passed: bool = True  # True when exit_code == 0; only meaningful at stage="done"
    exit_code: int = 0  # subprocess exit code; -1 for timeouts; only at stage="done"


# Type alias for the check execution callback.
CheckCallback = Callable[[CheckEvent], None]
