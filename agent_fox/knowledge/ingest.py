"""Knowledge source ingestion for the Fox Ball.

Ingests additional knowledge sources (ADRs, git commits) into the
knowledge store alongside session-extracted facts.

Requirements: 12-REQ-4.1, 12-REQ-4.2, 12-REQ-4.3
"""

from __future__ import annotations

import logging
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import duckdb

from agent_fox.knowledge.embeddings import EmbeddingGenerator

logger = logging.getLogger("agent_fox.knowledge.ingest")


@dataclass(frozen=True)
class IngestResult:
    """Summary of an ingestion run."""

    source_type: str  # "adr" | "git"
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
        target_dir = adr_dir if adr_dir is not None else (
            self._project_root / "docs" / "adr"
        )

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
                category="adr", identifier=filename,
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
                VALUES (?::UUID, ?, 'adr', ?, NULL, NULL, 'high',
                        CURRENT_TIMESTAMP)
                """,
                [fact_id, content, filename],
            )
            facts_added += 1

            # Generate and store embedding (best-effort)
            try:
                embedding = self._embedder.embed_text(content)
                if embedding is not None:
                    self._conn.execute(
                        "INSERT INTO memory_embeddings (id, embedding) "
                        "VALUES (?::UUID, ?::FLOAT[1024])",
                        [fact_id, embedding],
                    )
                else:
                    embedding_failures += 1
                    logger.warning(
                        "Embedding returned None for ADR %s", filename,
                    )
            except Exception:
                embedding_failures += 1
                logger.warning(
                    "Embedding failed for ADR %s", filename, exc_info=True,
                )

        return IngestResult(
            source_type="adr",
            facts_added=facts_added,
            facts_skipped=facts_skipped,
            embedding_failures=embedding_failures,
        )

    def ingest_git_commits(
        self,
        *,
        limit: int = 100,
        since: str | None = None,
    ) -> IngestResult:
        """Ingest git commit messages as facts.

        Each commit is stored as a fact with:
        - content: the commit message (subject + body)
        - category: "git"
        - commit_sha: the commit's SHA
        - created_at: the commit's author date

        Skips commits that have already been ingested (by checking
        for existing facts with the same commit_sha and category).

        Args:
            limit: Maximum number of commits to ingest.
            since: Only ingest commits after this date (ISO 8601).

        Returns:
            An IngestResult summarizing what was ingested.
        """
        # Build git log command
        cmd = [
            "git", "log",
            f"--max-count={limit}",
            "--format=%H%x00%aI%x00%s",
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
                "git log returned non-zero exit code: %d", result.returncode,
            )
            return IngestResult(
                source_type="git",
                facts_added=0,
                facts_skipped=0,
                embedding_failures=0,
            )

        facts_added = 0
        facts_skipped = 0
        embedding_failures = 0

        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue

            parts = line.split("\x00", 2)
            if len(parts) < 3:
                logger.warning("Skipping malformed git log line: %s", line)
                continue

            sha, date, message = parts

            if self._is_already_ingested(
                category="git", identifier=sha,
            ):
                facts_skipped += 1
                continue

            fact_id = str(uuid.uuid4())

            self._conn.execute(
                """
                INSERT INTO memory_facts
                    (id, content, category, spec_name, session_id,
                     commit_sha, confidence, created_at)
                VALUES (?::UUID, ?, 'git', NULL, NULL, ?, 'high', ?::TIMESTAMP)
                """,
                [fact_id, message, sha, date],
            )
            facts_added += 1

            # Generate and store embedding (best-effort)
            try:
                embedding = self._embedder.embed_text(message)
                if embedding is not None:
                    self._conn.execute(
                        "INSERT INTO memory_embeddings (id, embedding) "
                        "VALUES (?::UUID, ?::FLOAT[1024])",
                        [fact_id, embedding],
                    )
                else:
                    embedding_failures += 1
                    logger.warning(
                        "Embedding returned None for commit %s", sha,
                    )
            except Exception:
                embedding_failures += 1
                logger.warning(
                    "Embedding failed for commit %s", sha, exc_info=True,
                )

        return IngestResult(
            source_type="git",
            facts_added=facts_added,
            facts_skipped=facts_skipped,
            embedding_failures=embedding_failures,
        )

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
        """
        if category == "adr":
            row = self._conn.execute(
                "SELECT COUNT(*) FROM memory_facts "
                "WHERE category = 'adr' AND spec_name = ?",
                [identifier],
            ).fetchone()
        elif category == "git":
            row = self._conn.execute(
                "SELECT COUNT(*) FROM memory_facts "
                "WHERE category = 'git' AND commit_sha = ?",
                [identifier],
            ).fetchone()
        else:
            return False

        return row is not None and row[0] > 0
