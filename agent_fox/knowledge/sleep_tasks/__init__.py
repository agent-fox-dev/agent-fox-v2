"""Sleep task implementations for the sleep-time compute pipeline.

Contains:
- ContextRewriter: clusters facts by directory, synthesizes narrative summaries via LLM.
- BundleBuilder: pre-computes keyword and causal retrieval signals per spec.

Requirements: 112-REQ-3.*, 112-REQ-4.*
"""

from __future__ import annotations

from agent_fox.knowledge.sleep_tasks.bundle_builder import BundleBuilder
from agent_fox.knowledge.sleep_tasks.context_rewriter import ContextRewriter

__all__ = ["BundleBuilder", "ContextRewriter"]
