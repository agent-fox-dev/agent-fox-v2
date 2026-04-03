"""Oracle RAG pipeline for the agent-fox ask command.

Embeds a question, retrieves relevant facts via vector search,
assembles context with provenance, and synthesizes a grounded
answer using the STANDARD model in a single API call.

Requirements: 12-REQ-5.1, 12-REQ-5.2, 12-REQ-5.3, 12-REQ-6.1,
              12-REQ-8.1, 12-REQ-2.E2
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import anthropic

from agent_fox.core.client import cached_messages_create_sync, create_anthropic_client
from agent_fox.core.config import KnowledgeConfig
from agent_fox.core.errors import KnowledgeStoreError
from agent_fox.core.models import resolve_model
from agent_fox.core.prompt_safety import sanitize_prompt_content
from agent_fox.core.retry import retry_api_call
from agent_fox.core.token_tracker import track_response_usage
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.search import SearchResult, VectorSearch

logger = logging.getLogger("agent_fox.knowledge.oracle")


@dataclass(frozen=True)
class OracleAnswer:
    """The result of an oracle query."""

    answer: str
    sources: list[SearchResult]
    contradictions: list[str] | None
    confidence: float  # [0.0, 1.0]


class Oracle:
    """RAG pipeline for the agent-fox ask command.

    Embeds a question, retrieves relevant facts via vector search,
    assembles context with provenance, and synthesizes a grounded
    answer using the STANDARD model in a single API call.
    """

    def __init__(
        self,
        embedder: EmbeddingGenerator,
        search: VectorSearch,
        config: KnowledgeConfig,
    ) -> None:
        self._embedder = embedder
        self._search = search
        self._config = config
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        """Lazy-initialize the Anthropic client for synthesis."""
        if self._client is None:
            self._client = create_anthropic_client()
        return self._client

    def ask(self, question: str) -> OracleAnswer:
        """Run the full RAG pipeline for a question.

        Steps:
        1. Embed the question using the configured embedding model.
        2. Perform vector search to retrieve the top-k most similar
           facts.
        3. Assemble a context prompt with retrieved facts and their
           provenance (spec name, session ID, commit SHA).
        4. Call the synthesis model (STANDARD / Sonnet) with the
           context prompt and question. Single API call, not streaming.
        5. Parse the response for the answer, source citations,
           contradiction flags, and confidence level.

        Returns:
            An OracleAnswer with the synthesized answer, sources,
            any detected contradictions, and a confidence indicator.

        Raises:
            KnowledgeStoreError: If the query embedding fails
                (embedding API unavailable).
        """
        # Step 1: Embed the question
        query_embedding = self._embedder.embed_text(question)
        if query_embedding is None:
            raise KnowledgeStoreError("Failed to embed question. The embedding API may be unavailable. Please retry.")

        # Step 2: Vector search for top-k similar facts
        results = self._search.search(query_embedding)

        # Step 3: Assemble context with provenance
        context = self._assemble_context(results)

        # Step 4: Synthesize answer via single API call (not streaming)
        prompt = self._build_synthesis_prompt(question, context)
        model = resolve_model(self._config.ask_synthesis_model)

        response = retry_api_call(
            lambda: cached_messages_create_sync(
                self.client,
                model=model.model_id,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            ),
            context="oracle synthesis",
        )

        track_response_usage(response, model.model_id, "oracle synthesis")

        response_text = response.content[0].text  # type: ignore[union-attr]

        # Step 5: Parse the response
        return self._parse_synthesis_response(response_text, results)

    def _assemble_context(self, results: list[SearchResult]) -> str:
        """Build a context string from search results with provenance.

        Each fact is formatted with its source metadata so the
        synthesis model can cite sources and detect contradictions.
        """
        if not results:
            return "No relevant facts found."

        parts: list[str] = []
        for i, r in enumerate(results, 1):
            provenance_parts: list[str] = []
            if r.spec_name:
                provenance_parts.append(f"spec: {r.spec_name}")
            if r.session_id:
                provenance_parts.append(f"session: {r.session_id}")
            if r.commit_sha:
                provenance_parts.append(f"commit: {r.commit_sha}")
            provenance = ", ".join(provenance_parts) if provenance_parts else "unknown"

            parts.append(f"[Fact {i}] (id: {r.fact_id}, {provenance}, similarity: {r.similarity:.2f})\n{r.content}")

        return "\n\n".join(parts)

    def _build_synthesis_prompt(
        self,
        question: str,
        context: str,
    ) -> str:
        """Build the prompt for the synthesis model.

        Instructs the model to:
        - Answer the question using only the provided facts.
        - Cite sources by fact ID and provenance.
        - Flag any contradictions between facts.
        - Indicate confidence level (high/medium/low).
        - Not hallucinate beyond the provided context.
        """
        return (
            "You are a knowledge oracle for a software project. Answer the "
            "question below using ONLY the provided facts. Do not hallucinate "
            "or add information beyond what the facts contain.\n\n"
            "Instructions:\n"
            "1. Provide a clear, grounded answer based on the facts.\n"
            "2. Cite which facts support your answer.\n"
            "3. If any facts contradict each other, flag each contradiction "
            "on its own line starting with 'CONTRADICTION:' followed by a "
            "description of the conflicting facts.\n"
            "4. Do not invent information that is not in the facts.\n\n"
            "## Facts\n\n"
            f"{sanitize_prompt_content(context, label='facts')}\n\n"
            "## Question\n\n"
            f"{sanitize_prompt_content(question, label='question')}"
        )

    def _determine_confidence(self, results: list[SearchResult]) -> float:
        """Determine confidence based on result count and similarity.

        Returns a float in [0.0, 1.0]:
        - 0.9: 3+ results with similarity > 0.7
        - 0.6: 1-2 results with similarity > 0.5
        - 0.3: fewer or lower-similarity results

        Requirements: 37-REQ-4.1, 37-REQ-4.2
        """
        high_quality = [r for r in results if r.similarity > 0.7]
        if len(high_quality) >= 3:
            return 0.9

        medium_quality = [r for r in results if r.similarity > 0.5]
        if len(medium_quality) >= 1:
            return 0.6

        return 0.3

    def _parse_synthesis_response(
        self,
        response_text: str,
        results: list[SearchResult],
    ) -> OracleAnswer:
        """Parse the synthesis model's response into an OracleAnswer.

        Extracts the answer text, source citations, contradiction
        flags, and confidence indicator.
        """
        # Extract contradiction markers anywhere in the text.
        # The synthesis model may place "CONTRADICTION:" at the start of a
        # line or inline within a sentence.
        contradictions: list[str] = []
        for match in re.finditer(r"CONTRADICTION:\s*([^\n.]*(?:\.[^\n]*)?)", response_text, re.IGNORECASE):
            desc = match.group(1).strip()
            if desc:
                contradictions.append(desc)
            else:
                contradictions.append(match.group(0).strip())

        # Build the answer text by removing contradiction markers
        answer = re.sub(r"CONTRADICTION:\s*[^\n]*", "", response_text, flags=re.IGNORECASE).strip()
        confidence = self._determine_confidence(results)

        return OracleAnswer(
            answer=answer,
            sources=results,
            contradictions=contradictions if contradictions else None,
            confidence=confidence,
        )
