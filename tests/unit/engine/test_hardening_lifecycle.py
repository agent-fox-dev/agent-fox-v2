"""Tests for session lifecycle and knowledge harvest DuckDB hardening.

Test Spec: TS-38-3, TS-38-4
Requirements: 38-REQ-2.1, 38-REQ-2.3
"""

from __future__ import annotations

from typing import get_type_hints

from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.db import KnowledgeDB


class TestRequiredParameters:
    """Verify session lifecycle and knowledge harvest require KnowledgeDB.

    Requirements: 38-REQ-2.1, 38-REQ-2.3
    """

    def test_node_session_runner_requires_knowledge_db(self) -> None:
        """TS-38-3: NodeSessionRunner requires knowledge_db parameter."""
        hints = get_type_hints(NodeSessionRunner.__init__)
        assert "knowledge_db" in hints
        kb_type = hints["knowledge_db"]
        # Should be KnowledgeDB, not Optional[KnowledgeDB]
        assert kb_type is KnowledgeDB

    def test_extract_and_store_knowledge_requires_knowledge_db(self) -> None:
        """TS-38-4: extract_and_store_knowledge requires knowledge_db."""
        from agent_fox.engine.knowledge_harvest import extract_and_store_knowledge

        hints = get_type_hints(extract_and_store_knowledge)
        assert "knowledge_db" in hints
        kb_type = hints["knowledge_db"]
        assert kb_type is KnowledgeDB

    def test_sync_facts_requires_knowledge_db(self) -> None:
        """TS-38-4: sync_facts_to_duckdb requires knowledge_db."""
        from agent_fox.engine.knowledge_harvest import sync_facts_to_duckdb

        hints = get_type_hints(sync_facts_to_duckdb)
        assert "knowledge_db" in hints
        kb_type = hints["knowledge_db"]
        assert kb_type is KnowledgeDB

    def test_extract_causal_links_requires_knowledge_db(self) -> None:
        """TS-38-4: _extract_causal_links requires knowledge_db."""
        from agent_fox.engine.knowledge_harvest import _extract_causal_links

        hints = get_type_hints(_extract_causal_links)
        assert "knowledge_db" in hints
        kb_type = hints["knowledge_db"]
        assert kb_type is KnowledgeDB
