"""Property tests for knowledge provider protocol and configuration.

Test Spec: TS-114-P1, TS-114-P2, TS-114-P3, TS-114-P7, TS-114-P8, TS-114-P9
Requirements: 114-REQ-1.1, 114-REQ-1.2, 114-REQ-2.1, 114-REQ-2.2,
              114-REQ-2.3, 114-REQ-2.E1,
              114-REQ-3.E1, 114-REQ-4.E1,
              114-REQ-8.1, 114-REQ-8.2, 114-REQ-8.3, 114-REQ-8.5
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

from agent_fox.knowledge.provider import KnowledgeProvider, NoOpKnowledgeProvider
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# TS-114-P1: Protocol Structural Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Any class with both protocol methods satisfies isinstance.

    Property 1: For any class C that implements both ingest and retrieve
    with correct signatures, isinstance(C(), KnowledgeProvider) is True.

    Requirements: 114-REQ-1.1, 114-REQ-1.2, 114-REQ-2.1
    """

    @given(st.just(True))
    @settings(max_examples=5)
    def test_conforming_class_satisfies_protocol(self, _: bool) -> None:
        class DynProvider:
            def ingest(self, session_id: str, spec_name: str, context: dict[str, Any]) -> None:
                pass

            def retrieve(self, spec_name: str, task_description: str) -> list[str]:
                return []

        assert isinstance(DynProvider(), KnowledgeProvider)


# ---------------------------------------------------------------------------
# TS-114-P2: NoOp Retrieve Idempotency
# ---------------------------------------------------------------------------


class TestNoOpRetrieveIdempotent:
    """NoOp retrieve always returns empty list regardless of inputs.

    Property 2: For any spec_name and task_description,
    NoOpKnowledgeProvider().retrieve(spec_name, task_description) == [].

    Requirements: 114-REQ-2.3, 114-REQ-2.E1
    """

    @given(
        spec_name=st.text(max_size=100),
        task_description=st.text(max_size=200),
    )
    @settings(max_examples=50)
    def test_noop_retrieve_always_empty(self, spec_name: str, task_description: str) -> None:
        noop = NoOpKnowledgeProvider()
        result = noop.retrieve(spec_name, task_description)
        assert result == []
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TS-114-P3: NoOp Ingest Safety
# ---------------------------------------------------------------------------


class TestNoOpIngestSafe:
    """NoOp ingest never raises regardless of inputs.

    Property 3: For any session_id, spec_name, and context dict,
    NoOpKnowledgeProvider().ingest(...) returns None without exception.

    Requirements: 114-REQ-2.2
    """

    @given(
        session_id=st.text(max_size=50),
        spec_name=st.text(max_size=50),
        context=st.dictionaries(
            st.text(max_size=20),
            st.text(max_size=50),
            max_size=10,
        ),
    )
    @settings(max_examples=50)
    def test_noop_ingest_never_raises(
        self, session_id: str, spec_name: str, context: dict[str, str]
    ) -> None:
        noop = NoOpKnowledgeProvider()
        result = noop.ingest(session_id, spec_name, context)
        assert result is None


# ---------------------------------------------------------------------------
# TS-114-P7: Configuration Backward Compatibility
# ---------------------------------------------------------------------------


class TestConfigBackwardCompat:
    """Old config fields are silently ignored.

    Property 7: For any dictionary containing fields from old KnowledgeConfig,
    constructing a new KnowledgeConfig succeeds and has store_path.

    Requirements: 114-REQ-8.1, 114-REQ-8.2, 114-REQ-8.3, 114-REQ-8.5
    """

    @given(
        data=st.fixed_dictionaries(
            {},
            optional={
                "embedding_model": st.text(max_size=30),
                "embedding_dimensions": st.integers(min_value=1, max_value=2048),
                "dedup_similarity_threshold": st.floats(
                    min_value=0.0, max_value=1.0, allow_nan=False
                ),
                "contradiction_model": st.text(max_size=30),
                "decay_half_life_days": st.floats(
                    min_value=0.0, max_value=365.0, allow_nan=False
                ),
                "cleanup_enabled": st.booleans(),
            },
        ),
    )
    @settings(max_examples=30)
    def test_old_fields_ignored_without_error(self, data: dict[str, Any]) -> None:
        from agent_fox.core.config import KnowledgeConfig

        kc = KnowledgeConfig(**data)
        assert hasattr(kc, "store_path")
        # Old fields should not be stored as model fields
        for key in data:
            assert key not in kc.model_fields_set


# ---------------------------------------------------------------------------
# TS-114-P8: Retrieve Failure Resilience
# ---------------------------------------------------------------------------


class TestRetrieveFailureResilience:
    """Engine survives arbitrary retrieve() failures.

    Property 8: For any exception type, _build_prompts catches the
    exception and returns valid prompts.

    Requirements: 114-REQ-3.E1
    """

    @given(
        exc_type=st.sampled_from([RuntimeError, ValueError, TypeError, OSError]),
    )
    @settings(max_examples=4)
    def test_retrieve_failure_caught(self, exc_type: type[Exception]) -> None:
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        class FailProvider:
            def ingest(self, *a: Any, **kw: Any) -> None:
                pass

            def retrieve(self, *a: Any, **kw: Any) -> list[str]:
                raise exc_type("test failure")

        mock_config = MagicMock()
        mock_config.knowledge = MagicMock()
        mock_config.models = MagicMock()
        mock_config.orchestrator = MagicMock()
        mock_config.archetypes.overrides.get.return_value = None
        mock_config.archetypes.models = {}
        mock_config.models.coding = None
        mock_db = MagicMock()

        runner = NodeSessionRunner(
            "spec_01:1",
            mock_config,
            knowledge_db=mock_db,
            knowledge_provider=FailProvider(),
            sink_dispatcher=MagicMock(),
        )

        with (
            patch("agent_fox.engine.session_lifecycle.assemble_context", return_value=MagicMock()),
            patch("agent_fox.engine.session_lifecycle.build_system_prompt", return_value="sys"),
            patch("agent_fox.engine.session_lifecycle.build_task_prompt", return_value="task"),
            patch("agent_fox.core.config.resolve_spec_root", return_value=MagicMock()),
        ):
            sys_prompt, task_prompt = runner._build_prompts("/tmp/repo", 1, None)

        assert isinstance(sys_prompt, str)


# ---------------------------------------------------------------------------
# TS-114-P9: Ingest Failure Resilience
# ---------------------------------------------------------------------------


class TestIngestFailureResilience:
    """Engine survives arbitrary ingest() failures.

    Property 9: For any exception type, _ingest_knowledge catches the
    exception and does not retry.

    Requirements: 114-REQ-4.E1
    """

    @given(
        exc_type=st.sampled_from([RuntimeError, ValueError, TypeError, OSError]),
    )
    @settings(max_examples=4)
    def test_ingest_failure_caught_no_retry(self, exc_type: type[Exception]) -> None:
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        class FailProvider:
            ingest_count = 0

            def ingest(self, *a: Any, **kw: Any) -> None:
                FailProvider.ingest_count += 1
                raise exc_type("test failure")

            def retrieve(self, *a: Any, **kw: Any) -> list[str]:
                return []

        FailProvider.ingest_count = 0
        provider = FailProvider()
        mock_config = MagicMock()
        mock_config.knowledge = MagicMock()
        mock_config.models = MagicMock()
        mock_config.orchestrator = MagicMock()
        mock_config.archetypes.overrides.get.return_value = None
        mock_config.archetypes.models = {}
        mock_config.models.coding = None
        mock_db = MagicMock()

        runner = NodeSessionRunner(
            "spec_01:1",
            mock_config,
            knowledge_db=mock_db,
            knowledge_provider=provider,
            sink_dispatcher=MagicMock(),
        )

        # Should not raise
        runner._ingest_knowledge("node_1", ["f.py"], "sha", "completed")
        assert provider.ingest_count == 1  # called once, no retry
