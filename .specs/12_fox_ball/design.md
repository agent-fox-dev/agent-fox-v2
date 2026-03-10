# Design Document: Fox Ball -- Semantic Knowledge Oracle

## Overview

This spec transforms the flat JSONL fact store into a queryable semantic
knowledge oracle. It adds embedding generation, vector similarity search,
additional source ingestion, the `agent-fox ask` RAG pipeline, contradiction
detection, and fact supersession tracking. All vector data lives in DuckDB
alongside the existing schema established by spec 11.

## Architecture

```mermaid
flowchart TB
    User[Developer] -->|agent-fox ask "question"| CLI[CLI: ask command]
    CLI --> Oracle[Oracle<br/>RAG Pipeline]

    subgraph RAG Pipeline
        Oracle --> EmbedQ[Embed Query<br/>sentence-transformers]
        EmbedQ --> Search[Vector Search<br/>cosine similarity]
        Search --> Assemble[Assemble Context<br/>facts + provenance]
        Assemble --> Synthesize[Synthesize Answer<br/>STANDARD model]
    end

    Synthesize --> Answer[OracleAnswer<br/>answer + sources + contradictions]

    subgraph Fact Write Path
        Session[Session Runner] --> Extract[Memory Extraction<br/>spec 05]
        Extract --> DualWrite[Dual-Write<br/>store.py]
        DualWrite --> JSONL[JSONL Store<br/>source of truth]
        DualWrite --> DuckFact[DuckDB memory_facts]
        DualWrite --> Embed[Embed Fact<br/>embeddings.py]
        Embed --> DuckEmbed[DuckDB memory_embeddings]
    end

    subgraph Ingestion
        ADR[docs/adr/*.md] --> Ingest[Ingest<br/>ingest.py]
        Git[git log] --> Ingest
        Ingest --> DualWrite
    end

    Search --> DuckEmbed
    Search --> DuckFact
    DuckFact --> DB[(knowledge.duckdb<br/>spec 11)]
    DuckEmbed --> DB
```

### Module Responsibilities

1. `agent_fox/knowledge/embeddings.py` -- Generate embeddings using the
   Anthropic sentence-transformers. Batch embedding for efficiency. Handle API
   failures gracefully (return None, let caller proceed without embedding).
2. `agent_fox/knowledge/search.py` -- Vector similarity search over the
   `memory_embeddings` table. Cosine similarity ranking. Return top-k facts
   with scores and provenance.
3. `agent_fox/knowledge/oracle.py` -- RAG pipeline for `agent-fox ask`:
   embed query, vector search, assemble context with provenance, synthesize
   answer via STANDARD model (single API call), detect and flag contradictions.
4. `agent_fox/knowledge/ingest.py` -- Ingest additional knowledge sources:
   ADRs from `docs/adr/`, git commit messages. Parse, embed, and store as
   facts alongside session-extracted facts.
5. `agent_fox/cli/ask.py` -- `agent-fox ask "question"` CLI command.
   Wires up the oracle pipeline and renders the answer.
6. `agent_fox/memory/store.py` (extended) -- Dual-write: append to JSONL
   and insert into DuckDB `memory_facts` + `memory_embeddings` on every
   fact write.

## Components and Interfaces

### Embedding Generator

```python
# agent_fox/knowledge/embeddings.py
import logging
from sentence_transformers import SentenceTransformer
from agent_fox.core.config import KnowledgeConfig

logger = logging.getLogger("agent_fox.knowledge.embeddings")


class EmbeddingGenerator:
    """Generates vector embeddings using a local sentence-transformers model.

    The model is lazy-loaded on first use. Failures are handled
    gracefully: returns None for individual texts that fail to embed,
    allowing the caller to proceed without an embedding.
    """

    def __init__(self, config: KnowledgeConfig) -> None:
        self._config = config
        self._model: SentenceTransformer | None = None

    @property
    def embedding_dimensions(self) -> int:
        """Return the configured embedding dimensions."""
        return self._config.embedding_dimensions

    def embed_text(self, text: str) -> list[float] | None:
        """Generate an embedding for a single text string.

        Returns a list of floats (384 dimensions for all-MiniLM-L6-v2)
        on success, or None if embedding fails. Failures are logged
        as warnings, never raised.
        """
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Generate embeddings for multiple texts in a single API call.

        Returns a list parallel to the input: each element is either
        a list of floats or None if that text failed to embed.
        API failures are logged as warnings.
        """
        ...
```

### Vector Search

```python
# agent_fox/knowledge/search.py
import logging
from dataclasses import dataclass
import duckdb
from agent_fox.core.config import KnowledgeConfig

logger = logging.getLogger("agent_fox.knowledge.search")


@dataclass(frozen=True)
class SearchResult:
    """A single result from vector similarity search."""
    fact_id: str
    content: str
    category: str
    spec_name: str
    session_id: str | None
    commit_sha: str | None
    similarity: float


class VectorSearch:
    """Vector similarity search over the memory_embeddings table.

    Uses DuckDB's VSS extension for cosine similarity search over
    the HNSW index on memory_embeddings.embedding.
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        config: KnowledgeConfig,
    ) -> None:
        self._conn = conn
        self._config = config

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int | None = None,
        exclude_superseded: bool = True,
    ) -> list[SearchResult]:
        """Find the top-k facts most similar to the query embedding.

        Args:
            query_embedding: The embedding vector of the query text.
            top_k: Number of results to return. Defaults to
                config.ask_top_k (20).
            exclude_superseded: If True, exclude facts that have been
                superseded by newer facts.

        Returns:
            A list of SearchResult, sorted by descending similarity.
        """
        ...

    def has_embeddings(self) -> bool:
        """Check whether the knowledge store contains any embedded facts."""
        ...
```

### DuckDB Queries for Vector Search

The core search query joins `memory_embeddings` with `memory_facts` using
DuckDB's VSS cosine distance operator:

```sql
-- Core vector search query
SELECT
    f.id AS fact_id,
    f.content,
    f.category,
    f.spec_name,
    f.session_id,
    f.commit_sha,
    1 - array_cosine_distance(e.embedding, ?::FLOAT[384]) AS similarity
FROM memory_embeddings e
JOIN memory_facts f ON e.id = f.id
WHERE f.superseded_by IS NULL  -- exclude superseded facts
ORDER BY similarity DESC
LIMIT ?;
```

When `exclude_superseded=False`, the `WHERE` clause is omitted.

The query parameter `?::FLOAT[384]` receives the query embedding as a
list of floats. The `1 - array_cosine_distance(...)` converts distance
to similarity (higher = more similar).

### Oracle (RAG Pipeline)

```python
# agent_fox/knowledge/oracle.py
import logging
from dataclasses import dataclass, field
from anthropic import Anthropic
from agent_fox.core.config import KnowledgeConfig
from agent_fox.core.models import resolve_model
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.search import VectorSearch, SearchResult

logger = logging.getLogger("agent_fox.knowledge.oracle")


@dataclass(frozen=True)
class OracleAnswer:
    """The result of an oracle query."""
    answer: str
    sources: list[SearchResult]
    contradictions: list[str] | None
    confidence: str  # "high" | "medium" | "low"


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
        self._client: Anthropic | None = None

    @property
    def client(self) -> Anthropic:
        """Lazy-initialize the Anthropic client for synthesis."""
        if self._client is None:
            self._client = Anthropic()
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
        ...

    def _assemble_context(self, results: list[SearchResult]) -> str:
        """Build a context string from search results with provenance.

        Each fact is formatted with its source metadata so the
        synthesis model can cite sources and detect contradictions.
        """
        ...

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
        ...

    def _determine_confidence(self, results: list[SearchResult]) -> str:
        """Determine confidence based on result count and similarity.

        - "high": 3+ results with similarity > 0.7
        - "medium": 1-2 results with similarity > 0.5
        - "low": fewer or lower-similarity results
        """
        ...

    def _parse_synthesis_response(
        self,
        response_text: str,
        results: list[SearchResult],
    ) -> OracleAnswer:
        """Parse the synthesis model's response into an OracleAnswer.

        Extracts the answer text, source citations, contradiction
        flags, and confidence indicator.
        """
        ...
```

### Knowledge Source Ingestor

```python
# agent_fox/knowledge/ingest.py
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass
import duckdb
from agent_fox.knowledge.embeddings import EmbeddingGenerator

logger = logging.getLogger("agent_fox.knowledge.ingest")


@dataclass(frozen=True)
class IngestResult:
    """Summary of an ingestion run."""
    source_type: str       # "adr" | "git"
    facts_added: int
    facts_skipped: int     # already ingested
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
        ...

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
        ...

    def _parse_adr(self, path: Path) -> tuple[str, str]:
        """Parse an ADR markdown file into (title, body).

        Extracts the first H1 heading as the title. The full file
        content (including heading) is the body.
        """
        ...

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
        ...
```

### Dual-Write Store Extension

```python
# agent_fox/memory/store.py (extended interface)
#
# The existing MemoryStore from spec 05 is extended to support
# dual-write. The following methods are added or modified:

class MemoryStore:
    """Extended to support dual-write to JSONL + DuckDB."""

    def __init__(
        self,
        jsonl_path: Path,
        db_conn: duckdb.DuckDBPyConnection | None = None,
        embedder: EmbeddingGenerator | None = None,
    ) -> None:
        """Initialize with JSONL path and optional DuckDB connection.

        If db_conn is None, facts are written to JSONL only (graceful
        degradation). If embedder is None, facts are written without
        embeddings.
        """
        ...

    def write_fact(self, fact: MemoryFact) -> None:
        """Dual-write a fact to JSONL and DuckDB.

        1. Append the fact to JSONL (always succeeds or raises).
        2. Insert the fact into DuckDB memory_facts (best-effort).
        3. Generate an embedding and insert into memory_embeddings
           (best-effort, non-fatal on failure).

        If step 2 fails, log a warning and continue.
        If step 3 fails, log a warning and continue -- the fact
        exists in DuckDB without an embedding.
        """
        ...

    def _write_to_jsonl(self, fact: MemoryFact) -> None:
        """Append a fact to the JSONL store."""
        ...

    def _write_to_duckdb(self, fact: MemoryFact) -> None:
        """Insert a fact into the DuckDB memory_facts table."""
        ...

    def _write_embedding(self, fact_id: str, embedding: list[float]) -> None:
        """Insert an embedding into the DuckDB memory_embeddings table."""
        ...

    def mark_superseded(self, old_fact_id: str, new_fact_id: str) -> None:
        """Mark an old fact as superseded by a new one.

        Updates the superseded_by column in memory_facts.
        """
        ...
```

### CLI Ask Command

```python
# agent_fox/cli/ask.py
import click
from agent_fox.core.config import KnowledgeConfig
from agent_fox.knowledge.db import open_knowledge_store
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.search import VectorSearch
from agent_fox.knowledge.oracle import Oracle

@click.command("ask")
@click.argument("question")
@click.option("--top-k", type=int, default=None,
              help="Number of facts to retrieve (default: from config)")
@click.pass_context
def ask_command(ctx: click.Context, question: str, top_k: int | None) -> None:
    """Ask a question about your project's accumulated knowledge.

    Embeds the question, retrieves relevant facts from the knowledge
    store, and synthesizes a grounded answer with source citations.

    Example:
        agent-fox ask "why did we choose DuckDB over SQLite?"
    """
    ...
```

## Data Models

### EmbeddedFact

```python
@dataclass
class EmbeddedFact:
    """A fact with its vector embedding."""
    fact_id: str
    content: str
    category: str
    spec_name: str
    embedding: list[float]  # 384-dim vector for all-MiniLM-L6-v2
```

### SearchResult

```python
@dataclass(frozen=True)
class SearchResult:
    """A single result from vector similarity search."""
    fact_id: str
    content: str
    category: str
    spec_name: str
    session_id: str | None
    commit_sha: str | None
    similarity: float
```

### OracleAnswer

```python
@dataclass(frozen=True)
class OracleAnswer:
    """The result of an oracle query."""
    answer: str
    sources: list[SearchResult]
    contradictions: list[str] | None
    confidence: str  # "high" | "medium" | "low"
```

### IngestResult

```python
@dataclass(frozen=True)
class IngestResult:
    """Summary of an ingestion run."""
    source_type: str       # "adr" | "git"
    facts_added: int
    facts_skipped: int
    embedding_failures: int
```

### DuckDB Tables Used

The following tables are created by spec 11 and populated by this spec:

```sql
-- Knowledge facts with provenance
CREATE TABLE memory_facts (
    id            UUID PRIMARY KEY,
    content       TEXT NOT NULL,
    category      TEXT,
    spec_name     TEXT,
    session_id    TEXT,
    commit_sha    TEXT,
    confidence    TEXT DEFAULT 'high',
    created_at    TIMESTAMP,
    superseded_by UUID
);

-- Vector embeddings for semantic search
CREATE TABLE memory_embeddings (
    id        UUID PRIMARY KEY REFERENCES memory_facts(id),
    embedding FLOAT[384]
);
```

## Correctness Properties

### Property 1: Dual-Write Consistency

*For any* fact written through `MemoryStore.write_fact()`, the fact SHALL
appear in the JSONL store. If DuckDB is available, the fact SHALL also appear
in the `memory_facts` table. JSONL is never skipped, even if DuckDB fails.

**Validates:** 12-REQ-1.1, 12-REQ-1.2, 12-REQ-1.E1

### Property 2: Embedding Non-Fatality

*For any* fact write where the embedding API call fails, the fact SHALL still
be present in both JSONL and DuckDB `memory_facts`. The `memory_embeddings`
table MAY lack a row for this fact. No exception SHALL propagate to the caller.

**Validates:** 12-REQ-2.E1

### Property 3: Search Result Ordering

*For any* vector search with k results, the returned list SHALL be sorted
in descending order of similarity score. For i < j,
`results[i].similarity >= results[j].similarity`.

**Validates:** 12-REQ-3.1

### Property 4: Search Excludes Unembedded Facts

*For any* fact in `memory_facts` that has no corresponding row in
`memory_embeddings`, that fact SHALL NOT appear in vector search results.

**Validates:** 12-REQ-3.3

### Property 5: Superseded Fact Exclusion

*For any* fact where `superseded_by IS NOT NULL`, that fact SHALL NOT appear
in default vector search results (with `exclude_superseded=True`).

**Validates:** 12-REQ-7.2

### Property 6: Oracle Answer Groundedness

*For any* oracle query, every fact ID cited in `OracleAnswer.sources` SHALL
correspond to a fact that was retrieved by the vector search step. The oracle
SHALL NOT cite facts it did not retrieve.

**Validates:** 12-REQ-5.1, 12-REQ-5.2

### Property 7: Ingestion Idempotency

*For any* knowledge source (ADR or git commit), ingesting it twice SHALL NOT
create duplicate facts. The second ingestion SHALL skip already-ingested
sources and report them as `facts_skipped`.

**Validates:** 12-REQ-4.1, 12-REQ-4.2

## Error Handling

| Error Condition | Behavior | Requirement |
|----------------|----------|-------------|
| Embedding API fails on fact write | Fact written to JSONL + DuckDB without embedding, warning logged | 12-REQ-2.E1 |
| Embedding API fails on ask query | Error reported, suggest retrying | 12-REQ-2.E2 |
| DuckDB unavailable on fact write | Fact written to JSONL only, warning logged | 12-REQ-1.E1 |
| DuckDB unavailable on ask command | Error message explaining store unavailable | 12-REQ-5.E2 |
| Knowledge store empty (no embeddings) | Message suggesting running sessions first | 12-REQ-5.E1 |
| Contradicting facts retrieved | Synthesis model flags contradiction in response | 12-REQ-6.1 |
| ADR directory does not exist | Ingest returns 0 facts, no error | 12-REQ-4.1 |
| Git log fails | Warning logged, ingest returns 0 facts | 12-REQ-4.2 |
| Superseded fact in search results | Excluded from default search | 12-REQ-7.2 |

## Technology Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| duckdb | >=1.0 | Vector storage and similarity search |
| sentence-transformers | >=2.0 | Local embedding generation (all-MiniLM-L6-v2) |
| Python | 3.12+ | Runtime |
| Click | 8.1+ | CLI command registration |
| pytest | 8.0+ | Test framework |
| hypothesis | 6.0+ | Property-based testing |

## Definition of Done

A task group is complete when ALL of the following are true:

1. All subtasks within the group are checked off (`[x]`)
2. All spec tests (`test_spec.md` entries) for the task group pass
3. All property tests for the task group pass
4. All previously passing tests still pass (no regressions)
5. No linter warnings or errors introduced
6. Code is committed on a feature branch and pushed to remote
7. Feature branch is merged back to `develop`
8. `tasks.md` checkboxes are updated to reflect completion

## Testing Strategy

- **Unit tests** validate individual functions: embedding generation (mocked
  API), vector search (in-memory DuckDB), oracle pipeline (mocked embedder
  and search), dual-write (mocked JSONL + in-memory DuckDB), ingestion
  (filesystem fixtures + mocked git).
- **Property tests** (Hypothesis) verify invariants: dual-write consistency,
  embedding non-fatality, search result ordering, superseded fact exclusion,
  ingestion idempotency.
- **All DuckDB tests use in-memory databases** (`duckdb.connect(":memory:")`)
  to avoid polluting the real knowledge store.
- **The Anthropic API is always mocked** in tests. No network calls.
  Mock responses provide realistic embedding vectors (384 floats) and
  synthesis text.
- **CLI tests use Click's CliRunner** with mocked oracle and knowledge store.
- **Ingestion tests use `tmp_path`** for ADR fixtures and mocked
  `subprocess.run` for git log.
