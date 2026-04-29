"""Property tests for git stack hardening: error classification, cascade blocking, lifecycle.

Test Spec: TS-118-P3 (non-retryable classification correctness),
           TS-118-P4 (idempotent cascade blocking),
           TS-118-P5 (run lifecycle completeness)
Properties: Property 3, Property 4, Property 5 from design.md
Requirements: 118-REQ-3.1, 118-REQ-3.E1, 118-REQ-7.1,
              118-REQ-6.1, 118-REQ-6.2, 118-REQ-6.3
"""

from __future__ import annotations

import copy
import logging
import logging.handlers

import duckdb
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.state import cleanup_stale_runs

# ---------------------------------------------------------------------------
# TS-118-P3: Non-Retryable Classification Correctness
# Property 3: Divergent-file errors are non-retryable; merge errors retryable
# ---------------------------------------------------------------------------


class TestRetryableClassificationProperty:
    """TS-118-P3: non-retryable classification correctness.

    Property 3 from design.md.
    Requirements: 118-REQ-3.1, 118-REQ-3.E1
    """

    @pytest.mark.property
    def test_integration_error_defaults_retryable(self) -> None:
        """IntegrationError with no retryable kwarg defaults to retryable=True.

        This verifies backward compatibility — all existing raise sites
        produce retryable errors unless explicitly set."""
        from agent_fox.core.errors import IntegrationError

        exc = IntegrationError("merge conflict")
        assert exc.retryable is True

    @pytest.mark.property
    def test_integration_error_explicit_nonretryable(self) -> None:
        """IntegrationError with retryable=False is non-retryable."""
        from agent_fox.core.errors import IntegrationError

        exc = IntegrationError("divergent files", retryable=False)
        assert exc.retryable is False

    @pytest.mark.property
    @given(
        message=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=20, deadline=5000)
    def test_retryable_attribute_preserved(self, message: str) -> None:
        """For any error message, retryable=False is preserved on the
        exception and retryable=True is the default.

        Property 3: divergent-file errors (retryable=False) stay non-retryable;
        merge-conflict errors (default) stay retryable."""
        from agent_fox.core.errors import IntegrationError

        # Non-retryable (divergent-file path)
        exc_nonretry = IntegrationError(message, retryable=False)
        assert exc_nonretry.retryable is False
        assert str(exc_nonretry) == message

        # Retryable (merge-conflict path, default)
        exc_retry = IntegrationError(message)
        assert exc_retry.retryable is True
        assert str(exc_retry) == message

    @pytest.mark.property
    @given(
        n_files=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=10, deadline=5000)
    def test_nonretryable_carries_context(self, n_files: int) -> None:
        """IntegrationError with retryable=False preserves context kwargs.

        Ensures the retryable attribute doesn't interfere with the base
        class's context dict."""
        from agent_fox.core.errors import IntegrationError

        files = [f"file_{i}.py" for i in range(n_files)]
        exc = IntegrationError(
            "divergent untracked files",
            retryable=False,
            conflicting_files=files,
        )
        assert exc.retryable is False
        assert exc.context["conflicting_files"] == files


# ---------------------------------------------------------------------------
# TS-118-P4: Idempotent Cascade Blocking
# Property 4: Blocking an already-blocked node is a no-op
# ---------------------------------------------------------------------------


class TestIdempotentCascadeProperty:
    """TS-118-P4: idempotent cascade blocking.

    Property 4 from design.md.
    Requirements: 118-REQ-7.1
    """

    @pytest.mark.property
    @given(
        reason=st.text(min_size=1, max_size=50),
        new_reason=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=20, deadline=5000)
    def test_idempotent_blocking(self, reason: str, new_reason: str) -> None:
        """Re-blocking an already-blocked node produces identical state
        and no warning log emission."""
        node_states = {"A": "pending"}
        edges: dict[str, list[str]] = {"A": []}
        graph_sync = GraphSync(node_states, edges)

        # Block with first reason
        graph_sync.mark_blocked("A", reason)
        state_after_first = copy.deepcopy(dict(node_states))

        # Capture logs during re-block
        gs_logger = logging.getLogger("agent_fox.engine.graph_sync")
        handler = logging.handlers.MemoryHandler(capacity=100)
        gs_logger.addHandler(handler)
        original_level = gs_logger.level
        gs_logger.setLevel(logging.DEBUG)
        try:
            # Re-block with different reason
            graph_sync.mark_blocked("A", new_reason)
        finally:
            gs_logger.removeHandler(handler)
            gs_logger.setLevel(original_level)

        state_after_second = dict(node_states)

        # State should be identical (blocked remains blocked)
        assert state_after_second == state_after_first

        # No WARNING should have been emitted during re-block
        warnings = [r for r in handler.buffer if r.levelno >= logging.WARNING]
        assert not warnings, f"Expected no WARNING on re-block; got: {[r.message for r in warnings]}"


# ---------------------------------------------------------------------------
# TS-118-P5: Run Lifecycle Completeness
# Property 5: Stale runs are always cleaned up
# ---------------------------------------------------------------------------


class TestRunLifecycleCompleteness:
    """TS-118-P5: run lifecycle completeness.

    Property 5 from design.md.
    Requirements: 118-REQ-6.1, 118-REQ-6.2, 118-REQ-6.3
    """

    @pytest.mark.property
    @given(
        n_stale=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=10, deadline=5000)
    def test_lifecycle_completeness(self, n_stale: int) -> None:
        """After detect_and_clean_stale_runs, all stale runs have terminal status."""
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id                  VARCHAR PRIMARY KEY,
                plan_content_hash   VARCHAR NOT NULL,
                started_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at        TIMESTAMP,
                status              VARCHAR NOT NULL DEFAULT 'running',
                total_input_tokens  BIGINT NOT NULL DEFAULT 0,
                total_output_tokens BIGINT NOT NULL DEFAULT 0,
                total_cost          DOUBLE NOT NULL DEFAULT 0.0,
                total_sessions      INTEGER NOT NULL DEFAULT 0
            )
        """)

        run_ids = [f"stale_{i}" for i in range(n_stale)]
        for rid in run_ids:
            conn.execute(
                "INSERT INTO runs (id, plan_content_hash, status) VALUES (?, ?, ?)",
                [rid, "hash", "running"],
            )

        cleanup_stale_runs(conn, "current_run")

        for rid in run_ids:
            row = conn.execute(
                "SELECT status FROM runs WHERE id = ?", [rid]
            ).fetchone()
            assert row is not None
            # Spec requires status='stalled' for cleanup
            assert row[0] == "stalled"

        conn.close()
