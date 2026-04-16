---
Title: 06. Allow unauthenticated Hugging Face Hub access for embedding model downloads
Date: 2026-04-16
Status: Accepted
---
## Context

Agent-fox uses local vector embeddings for semantic similarity search over the
knowledge store. The embedding model (`all-MiniLM-L6-v2` by default, configurable
via `[knowledge] embedding_model`) is provided by the `sentence-transformers`
library, which downloads model weights from the Hugging Face Hub on first use and
caches them locally (`~/.cache/huggingface/`).

Hugging Face Hub supports both authenticated and unauthenticated access.
Unauthenticated requests are subject to lower rate limits and slower download
speeds. When no token is found, `huggingface_hub` emits a warning:

> Warning: You are sending unauthenticated requests to the HF Hub. Please set
> a HF_TOKEN to enable higher rate limits and faster downloads.

This warning surfaces in the night-shift daemon, which triggers embedding model
loading through multiple code paths:

1. **Spec executor stream** — `_SpecBatchRunner.run()` → `run_code()` →
   `_setup_infrastructure()` creates an `EmbeddingGenerator`
   (`engine/run.py:118-128`).
2. **Fix pipeline** — `fix/analyzer.py:331` creates its own `EmbeddingGenerator`
   to query the knowledge oracle for context during error analysis.
3. **Background ingestion** — `knowledge/ingest.py` creates an embedder when
   ingesting ADRs and git commit metadata.

The project already attempts to suppress this warning in two places:

- `knowledge/embeddings.py:49-52` — silences the
  `huggingface_hub.utils._headers` Python logger (targets `logging` module).
- `engine/run.py:236-238` — applies `warnings.filterwarnings("ignore")` for
  `huggingface_hub` and `sentence_transformers` modules (targets `warnings`
  module).

The logger suppression is applied at model load time and covers all paths. The
`warnings.filterwarnings` suppression is only applied inside `run_code()`, so
night-shift code paths that create `EmbeddingGenerator` instances outside
`run_code()` (fix pipeline, standalone ingestion) do not benefit from it. The
warning mechanism also varies across `huggingface_hub` versions — some versions
use `logging`, others use `warnings.warn()`, and the warning text itself was
removed entirely in v1.10.x.

## Decision Drivers

- **Zero-configuration experience** — users should be able to run `agent-fox`
  out of the box without signing up for external services or managing API tokens.
- **Model is public** — `all-MiniLM-L6-v2` is a public model on Hugging Face
  Hub that does not require authentication to download.
- **One-time download** — the model is cached locally after the first download;
  subsequent loads are local file reads with only a lightweight version check
  hitting the network.
- **Operational simplicity** — requiring an HF_TOKEN adds a setup step, a
  secret to manage, and a failure mode (expired/revoked tokens) with no
  functional benefit for public model access.

## Options Considered

### Option A: Require HF_TOKEN in the environment

Mandate that users provide a Hugging Face API token before running agent-fox.

**Pros:**
- Eliminates the warning entirely.
- Higher rate limits for initial model download.
- Future-proofs against Hugging Face tightening unauthenticated access.

**Cons:**
- Breaks zero-configuration experience — new users must register on Hugging
  Face and configure a token before they can use agent-fox.
- Adds a managed secret (rotation, expiry, CI/CD secrets configuration).
- Provides no functional benefit: the model is public and downloads fine
  without a token.
- Creates a hard failure mode: expired tokens cause cryptic download failures.

### Option B: Suppress the warning, do not require a token

Allow unauthenticated access. Apply best-effort suppression of the warning
across all code paths. Document that users *may* set `HF_TOKEN` for faster
initial downloads but it is not required.

**Pros:**
- Zero-configuration: works out of the box.
- No secrets to manage.
- Model downloads succeed without authentication.
- Warning is cosmetic, not functional.

**Cons:**
- Lower rate limits on initial download (rarely hit — model is ~80 MB,
  single download).
- Warning may leak through in some code paths or library versions despite
  suppression attempts.
- If Hugging Face ever requires authentication for public models, this
  breaks silently.

### Option C: Bundle the model or use an offline-only model

Ship the embedding model weights with agent-fox (in the package or as a
separate download step) to eliminate all Hub interaction at runtime.

**Pros:**
- No network dependency at all after installation.
- No warning, no rate limits, no authentication.

**Cons:**
- Adds ~80 MB to the package size (sentence-transformers + model weights).
- Complicates the build and distribution pipeline.
- Makes it harder for users to swap in alternative models via configuration.
- Model updates require a new agent-fox release.

## Decision

We will **allow unauthenticated Hugging Face Hub access and suppress the
warning** (Option B) because the embedding model is public, the download is a
one-time operation cached locally, and requiring a token adds setup friction
with no functional benefit.

The warning suppression should be consolidated so that it covers all code paths
consistently, not just the `run_code()` path. Specifically, the logger-level
suppression in `EmbeddingGenerator.model` already runs at model load time and
covers all paths. The `warnings.filterwarnings` call in `engine/run.py` should
be moved earlier or replicated at the `EmbeddingGenerator` level to close the
gap for night-shift paths that bypass `run_code()`.

## Consequences

### Positive
- Users can run agent-fox immediately after installation with no external
  account or token configuration.
- No managed secrets for embedding model access.
- Users who *want* faster downloads can optionally set `HF_TOKEN` — the
  library respects it automatically.

### Negative / Trade-offs
- The warning may still surface in some environments or library versions
  despite suppression. This is cosmetic, not functional.
- If Hugging Face changes its public access policy, a future update will be
  needed (likely requiring Option A or Option C).

### Neutral / Follow-up actions
- Consolidate the `warnings.filterwarnings` suppression into
  `EmbeddingGenerator.model` alongside the existing logger suppression so
  all code paths (including night-shift fix pipeline and standalone
  ingestion) are covered uniformly.
- Document in the configuration reference that `HF_TOKEN` is optional but
  respected if set.
- Revisit if Hugging Face tightens unauthenticated access to public models.

## References

- `agent_fox/knowledge/embeddings.py` — lazy model loading and logger
  suppression
- `agent_fox/engine/run.py:236-238` — `warnings.filterwarnings` suppression
- `agent_fox/core/config.py:260-261` — `embedding_model` and
  `embedding_dimensions` configuration
- `agent_fox/fix/analyzer.py:331` — standalone `EmbeddingGenerator` in fix
  pipeline (outside `run_code()`)
- Hugging Face Hub rate limits: https://huggingface.co/docs/hub/models-downloading#rate-limits
- all-MiniLM-L6-v2 model card: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
