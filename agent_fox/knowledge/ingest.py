"""Knowledge source ingestion for the Fox Ball.

Ingests additional knowledge sources (ADRs, git commits, errata) into the
knowledge store alongside session-extracted facts.

Requirements: 12-REQ-4.1, 12-REQ-4.2, 12-REQ-4.3, 40-REQ-11.6
"""

from __future__ import annotations

import logging
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.migrations import _ALLOWED_EMBEDDING_DIMS

if TYPE_CHECKING:
    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger("agent_fox.knowledge.ingest")


@dataclass(frozen=True)
class IngestResult:
    """Summary of an ingestion run."""

    source_type: str  # "adr" | "git" | "errata"
    facts_added: int
    facts_skipped: int  # already ingested
    embedding_failures: int


class KnowledgeIngestor:
    """Ingests additional knowledge sources into the Fox Ball.

    Parses ADRs and git commit messages, creates facts, generates
    embeddings, and stores them in DuckDB alongside session facts.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        embedder: EmbeddingGenerator,
        project_root: Path,
    ) -> None:
        self._conn = conn
        self._embedder = embedder
        self._project_root = project_root

    def _store_embedding(self, fact_id: str, text: str, label: str) -> bool:
        """Generate and store an embedding for *fact_id* (best-effort).

        Returns True on success, False on failure (logged as warning).
        """
        dim = self._embedder.embedding_dimensions
        assert dim in _ALLOWED_EMBEDDING_DIMS, f"Invalid embedding dimension: {dim}"
        try:
            embedding = self._embedder.embed_text(text)
            if embedding is not None:
                self._conn.execute(
                    f"INSERT INTO memory_embeddings (id, embedding) VALUES (?::UUID, ?::FLOAT[{dim}])",
                    [fact_id, embedding],
                )
                return True
            logger.warning("Embedding returned None for %s", label)
        except Exception:
            logger.warning("Embedding failed for %s", label, exc_info=True)
        return False

    def ingest_adrs(self, adr_dir: Path | None = None) -> IngestResult:
        """Ingest ADRs from docs/adr/ as facts.

        Each ADR markdown file is parsed into a single fact with:
        - content: the ADR title and body
        - category: "adr"
        - spec_name: the ADR filename (e.g., "001-use-duckdb.md")
        - commit_sha: None (ADRs are not tied to a specific commit)

        Skips ADRs that have already been ingested (by checking
        for existing facts with the same spec_name and category).

        Returns:
            An IngestResult summarizing what was ingested.
        """
        target_dir = adr_dir if adr_dir is not None else (self._project_root / "docs" / "adr")

        if not target_dir.exists() or not target_dir.is_dir():
            return IngestResult(
                source_type="adr",
                facts_added=0,
                facts_skipped=0,
                embedding_failures=0,
            )

        facts_added = 0
        facts_skipped = 0
        embedding_failures = 0

        for md_file in sorted(target_dir.glob("*.md")):
            filename = md_file.name

            if self._is_already_ingested(
                category="adr",
                identifier=filename,
            ):
                facts_skipped += 1
                continue

            title, body = self._parse_adr(md_file)
            content = f"{title}\n\n{body}" if title else body
            fact_id = str(uuid.uuid4())

            self._conn.execute(
                """
                INSERT INTO memory_facts
                    (id, content, category, spec_name, session_id,
                     commit_sha, confidence, created_at)
                VALUES (?::UUID, ?, 'adr', ?, NULL, NULL, 0.9,
                        CURRENT_TIMESTAMP)
                """,
                [fact_id, content, filename],
            )
            facts_added += 1

            if not self._store_embedding(fact_id, content, f"ADR {filename}"):
                embedding_failures += 1

        return IngestResult(
            source_type="adr",
            facts_added=facts_added,
            facts_skipped=facts_skipped,
            embedding_failures=embedding_failures,
        )

    def ingest_errata(self, errata_dir: Path | None = None) -> IngestResult:
        """Ingest errata from docs/errata/ as facts.

        Each errata markdown file is parsed into a single fact with:
        - content: the erratum title and body
        - category: "errata"
        - spec_name: the erratum filename (e.g., "93_ts93_4_placement.md")
        - commit_sha: None (errata are not tied to a specific commit)

        Skips errata that have already been ingested (by checking
        for existing facts with the same spec_name and category).

        Args:
            errata_dir: Override for the errata directory. Defaults to
                        docs/errata/ under the project root.

        Returns:
            An IngestResult summarizing what was ingested.
        """
        target_dir = errata_dir if errata_dir is not None else (self._project_root / "docs" / "errata")

        if not target_dir.exists() or not target_dir.is_dir():
            return IngestResult(
                source_type="errata",
                facts_added=0,
                facts_skipped=0,
                embedding_failures=0,
            )

        facts_added = 0
        facts_skipped = 0
        embedding_failures = 0

        for md_file in sorted(target_dir.glob("*.md")):
            filename = md_file.name

            if self._is_already_ingested(
                category="errata",
                identifier=filename,
            ):
                facts_skipped += 1
                continue

            title, body = self._parse_adr(md_file)
            content = f"{title}\n\n{body}" if title else body
            fact_id = str(uuid.uuid4())

            self._conn.execute(
                """
                INSERT INTO memory_facts
                    (id, content, category, spec_name, session_id,
                     commit_sha, confidence, created_at)
                VALUES (?::UUID, ?, 'errata', ?, NULL, NULL, 0.9,
                        CURRENT_TIMESTAMP)
                """,
                [fact_id, content, filename],
            )
            facts_added += 1

            if not self._store_embedding(fact_id, content, f"erratum {filename}"):
                embedding_failures += 1

        return IngestResult(
            source_type="errata",
            facts_added=facts_added,
            facts_skipped=facts_skipped,
            embedding_failures=embedding_failures,
        )

    async def ingest_git_commits(
        self,
        *,
        limit: int = 100,
        since: str | None = None,
        model_name: str = "SIMPLE",
    ) -> IngestResult:
        """Ingest git commit messages as facts using LLM extraction.

        Collects commits via ``git log``, batches them into groups of 20,
        and calls an LLM to extract structured knowledge (decisions,
        patterns, gotchas, conventions) from each batch.  Commits shorter
        than 20 characters are excluded from the LLM batch.

        Requirements: 113-REQ-2.1, 113-REQ-2.2, 113-REQ-2.3,
                      113-REQ-2.E1, 113-REQ-2.E2
        """
        # Build git log command
        cmd = [
            "git",
            "log",
            f"--max-count={limit}",
            "--format=%x1e%H%x00%aI%x00%s%x00%b",
        ]
        if since is not None:
            cmd.append(f"--since={since}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self._project_root),
            )
        except Exception:
            logger.warning("git log failed", exc_info=True)
            return IngestResult(
                source_type="git",
                facts_added=0,
                facts_skipped=0,
                embedding_failures=0,
            )

        if result.returncode != 0:
            logger.warning(
                "git log returned non-zero exit code: %d",
                result.returncode,
            )
            return IngestResult(
                source_type="git",
                facts_added=0,
                facts_skipped=0,
                embedding_failures=0,
            )

        # Parse commits and filter
        commits: list[tuple[str, str, str]] = []  # (sha, message, date)
        for record in result.stdout.split("\x1e"):
            record = record.strip()
            if not record:
                continue

            parts = record.split("\x00", 3)
            if len(parts) < 3:
                logger.warning("Skipping malformed git log record: %s", record[:120])
                continue

            sha, date, subject = parts[0], parts[1], parts[2]
            body = parts[3].strip() if len(parts) > 3 else ""
            message = f"{subject}\n\n{body}" if body else subject

            # 113-REQ-2.E2: Skip messages shorter than 20 characters
            if len(message) < 20:
                continue

            commits.append((sha, message, date))

        if not commits:
            return IngestResult(
                source_type="git",
                facts_added=0,
                facts_skipped=0,
                embedding_failures=0,
            )

        # 113-REQ-2.1: Batch commits into groups of 20
        facts_added = 0
        facts_skipped = 0
        embedding_failures = 0
        batch_size = 20

        for batch_start in range(0, len(commits), batch_size):
            batch = commits[batch_start : batch_start + batch_size]

            # 113-REQ-2.E1: On LLM failure, skip batch and log warning
            try:
                extracted_facts = await self._extract_git_facts_llm(batch, model_name)
            except Exception:
                logger.warning(
                    "LLM git extraction failed for batch starting at %d, skipping",
                    batch_start,
                    exc_info=True,
                )
                continue

            # 113-REQ-2.2: If LLM returns zero facts, store nothing
            if not extracted_facts:
                continue

            # Apply minimum content length filter (113-REQ-5.2)
            from agent_fox.engine.knowledge_harvest import _filter_minimum_length

            extracted_facts, _filtered = _filter_minimum_length(extracted_facts)

            # Use the first commit SHA from the batch for traceability
            batch_sha = batch[0][0] if batch else None

            for fact in extracted_facts:
                self._conn.execute(
                    """
                    INSERT INTO memory_facts
                        (id, content, category, spec_name, session_id,
                         commit_sha, confidence, keywords, created_at)
                    VALUES (?::UUID, ?, 'git', NULL, NULL, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    [fact.id, fact.content, batch_sha, fact.confidence, fact.keywords],
                )
                facts_added += 1

                if not self._store_embedding(fact.id, fact.content, f"git-llm:{fact.id[:8]}"):
                    embedding_failures += 1

        return IngestResult(
            source_type="git",
            facts_added=facts_added,
            facts_skipped=facts_skipped,
            embedding_failures=embedding_failures,
        )

    async def _extract_git_facts_llm(
        self,
        batch: list[tuple[str, str, str]],
        model_name: str = "SIMPLE",
    ) -> list:
        """Extract structured facts from a batch of git commit messages using LLM.

        Returns facts with categories from {decision, pattern, gotcha, convention}
        and confidence derived from LLM response (high=0.9, medium=0.6, low=0.3).
        Returns empty list on LLM failure.

        Requirements: 113-REQ-2.1, 113-REQ-2.2, 113-REQ-2.3, 113-REQ-2.E1
        """
        from agent_fox.core.client import ai_call
        from agent_fox.core.json_extraction import extract_json_array
        from agent_fox.knowledge.extraction import GIT_EXTRACTION_PROMPT
        from agent_fox.knowledge.facts import Fact, parse_confidence

        # Format commits for the prompt
        commit_lines = []
        for sha, message, date in batch:
            commit_lines.append(f"[{sha[:8]}] ({date}): {message}")
        commits_text = "\n\n".join(commit_lines)

        prompt = GIT_EXTRACTION_PROMPT.format(commits=commits_text)

        raw_text, _response = await ai_call(
            model_tier=model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            context="git fact extraction",
        )

        if raw_text is None:
            return []

        json_data = extract_json_array(raw_text)
        if json_data is None or not isinstance(json_data, list):
            return []

        # Valid categories for git extraction
        valid_categories = {"decision", "pattern", "gotcha", "convention"}
        now_str = __import__("datetime").datetime.now(
            __import__("datetime").UTC
        ).isoformat()

        facts: list[Fact] = []
        for item in json_data:
            if not isinstance(item, dict):
                continue
            content = item.get("content", "")
            if not content:
                continue

            category = item.get("category", "pattern")
            if category not in valid_categories:
                category = "pattern"

            raw_confidence = item.get("confidence", "medium")
            confidence = parse_confidence(raw_confidence)

            keywords = item.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []

            fact = Fact(
                id=str(uuid.uuid4()),
                content=content,
                category=category,
                spec_name="",
                keywords=keywords,
                confidence=confidence,
                created_at=now_str,
                supersedes=None,
                session_id=None,
            )
            facts.append(fact)

        return facts

    def _parse_adr(self, path: Path) -> tuple[str, str]:
        """Parse an ADR markdown file into (title, body).

        Extracts the first H1 heading as the title. The full file
        content (including heading) is the body.
        """
        content = path.read_text(encoding="utf-8")
        title = ""

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break

        return title, content

    def _is_already_ingested(
        self,
        *,
        category: str,
        identifier: str,
    ) -> bool:
        """Check whether a source has already been ingested.

        For ADRs: checks spec_name == identifier.
        For git commits: checks commit_sha == identifier.
        For errata: checks spec_name == identifier.
        """
        if category == "adr":
            row = self._conn.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE category = 'adr' AND spec_name = ?",
                [identifier],
            ).fetchone()
        elif category == "git":
            row = self._conn.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE category = 'git' AND commit_sha = ?",
                [identifier],
            ).fetchone()
        elif category == "errata":
            row = self._conn.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE category = 'errata' AND spec_name = ?",
                [identifier],
            ).fetchone()
        else:
            return False

        return row is not None and row[0] > 0


def run_background_ingestion(
    conn: duckdb.DuckDBPyConnection,
    config: KnowledgeConfig,
    project_root: Path,
    *,
    sink_dispatcher: SinkDispatcher | None = None,
    run_id: str = "",
) -> None:
    """Run background knowledge ingestion (ADRs + git commits + errata).

    Creates an EmbeddingGenerator and KnowledgeIngestor, then ingests
    ADRs, recent git commits, and errata documents. Best-effort: all
    failures are logged and silently ignored.

    Requirements: 12-REQ-4.1, 12-REQ-4.2, 12-REQ-4.3, 40-REQ-11.6
    """
    import asyncio

    try:
        embedder = EmbeddingGenerator(config)
        ingestor = KnowledgeIngestor(conn, embedder, project_root)

        adr_result = ingestor.ingest_adrs()
        if adr_result.facts_added > 0:
            logger.info(
                "Ingested %d ADR(s) (%d skipped)",
                adr_result.facts_added,
                adr_result.facts_skipped,
            )
            # 40-REQ-11.6: Emit knowledge.ingested audit event for ADRs
            _emit_knowledge_ingested(
                sink_dispatcher,
                run_id,
                source_type="adr",
                source_path=str(project_root / "docs" / "adr"),
                item_count=adr_result.facts_added,
            )

        # 113-REQ-2.1: ingest_git_commits is now async (LLM extraction)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an event loop — create a new task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                git_result = pool.submit(
                    asyncio.run, ingestor.ingest_git_commits()
                ).result()
        else:
            git_result = asyncio.run(ingestor.ingest_git_commits())

        if git_result.facts_added > 0:
            logger.info(
                "Ingested %d git commit(s) (%d skipped)",
                git_result.facts_added,
                git_result.facts_skipped,
            )
            # 40-REQ-11.6: Emit knowledge.ingested audit event for git commits
            _emit_knowledge_ingested(
                sink_dispatcher,
                run_id,
                source_type="git",
                source_path=str(project_root),
                item_count=git_result.facts_added,
            )

        errata_result = ingestor.ingest_errata()
        if errata_result.facts_added > 0:
            logger.info(
                "Ingested %d erratum/errata (%d skipped)",
                errata_result.facts_added,
                errata_result.facts_skipped,
            )
            # 40-REQ-11.6: Emit knowledge.ingested audit event for errata
            _emit_knowledge_ingested(
                sink_dispatcher,
                run_id,
                source_type="errata",
                source_path=str(project_root / "docs" / "errata"),
                item_count=errata_result.facts_added,
            )
    except Exception:
        logger.warning("Background knowledge ingestion failed", exc_info=True)


def _emit_knowledge_ingested(
    sink_dispatcher: SinkDispatcher | None,
    run_id: str,
    *,
    source_type: str,
    source_path: str,
    item_count: int,
) -> None:
    """Emit a knowledge.ingested audit event (best-effort).

    Requirements: 40-REQ-11.6
    """
    if sink_dispatcher is None or not run_id:
        return
    try:
        from agent_fox.knowledge.audit import AuditEvent, AuditEventType

        event = AuditEvent(
            run_id=run_id,
            event_type=AuditEventType.KNOWLEDGE_INGESTED,
            payload={
                "source_type": source_type,
                "source_path": source_path,
                "item_count": item_count,
            },
        )
        sink_dispatcher.emit_audit_event(event)
    except Exception:
        logger.debug("Failed to emit knowledge.ingested audit event", exc_info=True)
