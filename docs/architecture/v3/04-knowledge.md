# Chapter 04 — Memory, Knowledge & Maintenance

## The Knowledge System

The knowledge system is agent-fox's institutional memory. It captures what agents learn during execution and makes that knowledge available to future sessions. Over time, it transforms the system from a stateless contractor into a project-aware collaborator.

v3 elevates the knowledge system from an internal component to a standalone library (`agent_fox.knowledge`) usable outside the orchestrator. A developer can use it as a project knowledge base, queried from scripts, notebooks, or other tools.

### Storage: DuckDB In-Process

The knowledge store uses DuckDB as an embedded analytical database. No server, no daemon, no connection string. The database file lives at `.agent-fox/knowledge.db` and is accessed in-process.

DuckDB was chosen over SQLite because the query patterns are analytical (semantic search with vector similarity, aggregation over confidence scores, time-series queries over fact history) rather than transactional. DuckDB's columnar storage and vectorized execution handle these patterns efficiently.

Over Postgres: the system is designed for single-user, single-project use. Adding a database server to the dependency chain would violate the "time to first run under 15 minutes" constraint. If a team needs centralized knowledge (across projects or developers), the export/import protocol handles that (see Knowledge Sharing below).

### What Gets Stored

The knowledge store holds five record types: facts, findings, work items, session summaries, and metrics.

#### Facts

Discrete pieces of project knowledge extracted from session transcripts. Facts cover things like: "The auth module uses JWT with RS256 signing," "Running tests requires `DATABASE_URL` to be set," "The payment gateway returns 200 with an error body for rate-limited requests."

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key, generated at creation |
| `topic` | text | Short category label (e.g., "auth", "testing", "payment-gateway") |
| `statement` | text | Natural-language description of the fact |
| `confidence` | float (0.0–1.0) | Current confidence level |
| `state` | enum | `proposed`, `confirmed`, `superseded`, `stale` |
| `source_session_id` | UUID (FK) | Session that produced this fact |
| `superseded_by` | UUID (FK, nullable) | Points to the replacing fact, if superseded |
| `created_at` | timestamp | When the fact was first extracted |
| `last_confirmed_at` | timestamp | When the fact was last confirmed or referenced |
| `source_files` | text[] (nullable) | Repository-relative file paths referenced in the fact's evidence. Used for change-triggered staleness decay. |
| `embedding` | float[384] | Embedding vector (dimension matches the configured model) |

**Fact lifecycle transitions:**

- **Proposed** — Extracted from a session transcript by the Maintainer (knowledge extraction mode). Initial confidence: **0.3**.
- **Confirmed** — Triggered when the knowledge extraction Maintainer extracts a fact whose embedding similarity to an existing proposed or confirmed fact exceeds **0.92**, and the LLM judges them as semantically equivalent. The equivalence judgment is a lightweight call within the extraction session: the Maintainer's system prompt instructs it to compare the new statement against the matched existing statement and produce a judgment field (`"equivalence": "equivalent" | "contradicts" | "new"`). If equivalent, the existing fact transitions to confirmed. Confidence increases by **+0.2** added to the current value, capped at 1.0 (e.g., a proposed fact at 0.3 confirmed once becomes 0.5). Each match within a single extraction session triggers one increment. `last_confirmed_at` is updated to the extraction timestamp. **Outcome gating:** Confirmation only triggers when the source Coder session's outcome is `success` or `partial`. Facts extracted from `failure` sessions are still written as `proposed` (they may contain valid observations), but they do not confirm existing facts. This prevents echo-chamber reinforcement — if a Coder keeps repeating the same wrong assumption, each failure session produces a proposed fact that does not boost the confidence of the incorrect existing fact.
- **Superseded** — Triggered when the equivalence judgment is `"contradicts"` (similarity above **0.85**, same topic, incompatible statements). The old fact transitions to superseded, `superseded_by` points to the new fact. The new fact starts at proposed (0.3). Confidence levels do not block supersession — the LLM contradiction judgment is the quality gate, not the confidence score. Confidence measures how frequently a fact was encountered, not whether it is correct. If the supersession was wrong (the old fact was actually right), the old fact's information will be re-extracted from future sessions and re-proposed, eventually reaching confirmed status again. This self-correcting property depends on the old fact's information still being observable in the codebase or session transcripts.
- **Stale** — Staleness is driven by two signals: time without confirmation and code changes to referenced files.

  **Time-based decay:** Confidence decays linearly at **0.05 per 7-day period** since `last_confirmed_at`. This is a baseline decay — even facts about stable code should eventually be re-validated.

  **Change-triggered decay:** If a fact has `source_files` and any of those files have been modified since `last_confirmed_at` (checked via `git log --since` on the relevant paths), the fact receives an additional penalty of **0.3** (configurable as `knowledge.change_decay_penalty`). This penalty is applied once per detection — it does not stack for multiple changed files or multiple changes to the same file. Once the penalty has been applied, subsequent queries do not re-apply it until the fact is re-confirmed (which resets `last_confirmed_at`). Facts without `source_files` are subject to time-based decay only.

  Both decays are computed **on-demand** during search and knowledge injection, not as a background task. The effective confidence is: `effective_confidence = stored_confidence - time_decay - change_penalty`, floored at 0.0, where `time_decay = 0.05 × floor(days_since_last_confirmed / 7)` and `change_penalty = 0.3` if any `source_files` were modified since `last_confirmed_at`, else 0. Facts whose effective confidence falls below **0.1** are excluded from search results but retained in the store. The `state` field transitions to `stale` when the stored confidence is explicitly updated (e.g., during a periodic cleanup or export), but the on-demand calculation ensures search results are always current without requiring a background process.

**Similarity threshold scope:** Three different similarity thresholds are used for different purposes. They are not interchangeable:

| Threshold | Value | Scope | Configurable? |
|-----------|-------|-------|--------------|
| Confirmation | 0.92 | Fact lifecycle — triggers confirmation check during extraction | No (hardcoded) |
| Supersession | 0.85 | Fact lifecycle — triggers contradiction check during extraction | No (hardcoded) |
| Search | 0.7 | Search results — minimum similarity for `af knowledge query` and context injection | Yes (`knowledge.similarity_threshold`) |

Confirmation and supersession thresholds are intentionally fixed to prevent accidental tuning that would corrupt the fact lifecycle. The search threshold is user-facing and safe to adjust.

#### Findings

Structured review outputs from Reviewer and Verifier sessions.

| Field | Type | Description |
|-------|------|-------------|
| `id` | text | Finding ID (e.g., `F-01-3`) |
| `severity` | enum | `critical`, `major`, `minor`, `info` |
| `category` | text | Finding type (e.g., "ambiguity", "missing-test", "drift") |
| `description` | text | What was found |
| `source_session_id` | UUID (FK) | Session that produced this finding |
| `resolution_status` | enum | `open`, `resolved`, `wontfix` |
| `resolved_by_session_id` | UUID (FK, nullable) | Coder session that addressed this finding |

#### Work Items

Actionable problems stored as structured, semantically-searchable records. Work items are a general-purpose knowledge record type — not a night-shift internal. Night-shift is the primary producer, but spec audits (`af-spec-audit`), Reviewers, and manual entry also create work items. Work items are embedded alongside facts and participate in the same composite-scored search, enabling cross-type queries ("what does the system know about the auth module?").

Full schema, lifecycle, and knowledge integration: see **Work Items — Context-First Work Management** below.

#### Session Summaries

Structured metadata per completed session: what was attempted, what was achieved, what failed, turn count, model tier used. Generated deterministically from session transcripts (not LLM-generated — fields are extracted from harvest data). Used for "what happened before" context and historical analysis.

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | UUID | Primary key |
| `spec_name` | text | Which spec this session belongs to |
| `group_number` | int | Task group number |
| `archetype` | text | Which archetype ran |
| `model_tier` | text | Which model tier was used |
| `outcome` | enum | `success`, `partial`, `failure` |
| `attempted` | text | What the session tried to do |
| `achieved` | text | What was accomplished |
| `struggled_with` | text (nullable) | What went wrong, if anything |
| `turn_count` | int | Number of turns |
| `started_at` | timestamp | Session start |
| `completed_at` | timestamp | Session end |

#### Metrics

Quantitative data per session for cost reporting and routing model training.

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | UUID (FK) | References the session |
| `spec_name` | text | Spec name for grouping |
| `group_number` | int | Task group number |
| `archetype` | text | Archetype used |
| `model_tier` | text | Model tier used |
| `token_input` | int | Input tokens consumed |
| `token_output` | int | Output tokens consumed |
| `turn_count` | int | Total turns |
| `duration_seconds` | float | Wall-clock time |
| `test_pass_rate` | float (nullable) | Fraction of tests passing (0.0–1.0) |
| `outcome` | enum | `success`, `partial`, `failure` |
| `cost_usd` | float | Computed cost in USD |

### Semantic Search

Facts, findings, and work items are embedded using an ONNX-based model at write time. Queries embed the search term and find the nearest neighbors by cosine similarity.

**Default embedding model:** `gte-small` (Alibaba DAMO Academy), producing 384-dimensional embeddings, distributed as an ONNX artifact of approximately 67MB. This model is committed as the default — the embedding dimension (384) determines the storage schema and must be consistent within a knowledge store. Changing the model requires re-embedding all existing records (a migration that `af knowledge reindex` handles).

**Execution provider auto-detection:** The execution provider is selected by the following chain: (1) if `embedding_device` is set in project config, use it; (2) if `auto` (the default): on macOS + arm64, attempt CoreML provider (Neural Engine / GPU), fall back to CPU if CoreML initialization fails; on Linux, check for CUDA provider availability, fall back to CPU. The CoreML path eliminates the torch dependency entirely — this is the primary reason ONNX was chosen over sentence-transformers.

For projects that need higher-quality retrieval, a full torch-backed model (e.g., `all-MiniLM-L6-v2` or larger) can be installed via `uv pip install agent-fox[knowledge-torch]` and selected in config. This changes the embedding dimension and triggers a reindex.

**Vector storage:** Embedding vectors are stored as `FLOAT[384]` array columns. Similarity search uses cosine similarity computed via SQL (dot product over normalized vectors). The experimental `duckdb-vss` extension (HNSW indexes) is not required — brute-force search is sufficient for the expected fact counts (hundreds to low thousands per project). If `vss` is available, it is used opportunistically.

**Composite scoring.** Search results are ranked by: `score = similarity × effective_confidence × recency`. All three terms are in the range [0.0, 1.0]:

- **Similarity:** Cosine similarity between query embedding and fact embedding.
- **Effective confidence:** The fact's confidence after staleness decay (see Fact lifecycle, item 4). This is the on-demand computed value, not the stored value.
- **Recency:** An exponential decay applied to time since last confirmation: `recency = exp(-0.01 × days_since_last_confirmed)`. This gives a half-life of approximately 69 days. A fact confirmed yesterday has recency ~1.0; a fact last confirmed 6 months ago has recency ~0.16.

**How staleness decay and recency scoring interact:** These are two distinct mechanisms operating at different stages. Staleness decay (time-based + change-triggered) modifies the fact's effective confidence — it determines whether the fact is trustworthy enough to appear in results at all (excluded below 0.1). Recency scoring (exponential) is a separate multiplier in the composite score — it determines the fact's rank among results that passed the confidence filter. Both penalize old facts, but staleness is a hard filter (below 0.1 = excluded) while recency is a soft rank signal. Time-based decay alone will exclude a fact with initial confidence 0.3 after approximately 4 weeks of no confirmation (0.3 - 4×0.05 = 0.1). A confirmed fact at 0.8 survives approximately 14 weeks without code changes. If the referenced files change, the 0.3 change penalty accelerates exclusion — a proposed fact at 0.3 is immediately excluded (0.3 - 0.3 = 0.0), while a confirmed fact at 0.8 drops to an effective 0.5 with approximately 8 weeks of time-based decay remaining.

The three terms are multiplied with equal weight. Configurable weights are a potential future extension but not in scope for v3.

**Work item scoring.** Work items participate in the same search but use a simplified composite score: `score = similarity × status_weight × recency`. The `status_weight` substitutes for confidence: `discovered` = 1.0, `approved` = 1.0, `in_progress` = 0.8, `fixed` = 0.3, `wontfix` = 0.0 (excluded from results). Recency is computed from `updated_at` using the same exponential decay. This ensures active work items rank highly alongside confirmed facts, while resolved items fade but remain discoverable.

### Knowledge Extraction

After each Coder session, the engine dispatches a Maintainer session in knowledge extraction mode. The `agent_fox.knowledge` package owns the extraction prompt template (a system prompt that instructs the LLM to identify facts from a transcript) and the fact-writing logic (comparison, confirmation, supersession). The `agent_fox.engine` package is responsible for dispatching the extraction session and passing the transcript. This split means spec `08_engine_v1` handles dispatch orchestration while spec `10_knowledge_pipeline` handles the extraction prompt, output parsing, and knowledge store writes.

The extraction Maintainer receives the transcript and a prompt asking it to identify:

- Causal relationships ("X caused Y because Z").
- Architectural decisions ("We chose approach A over B because...").
- Failure patterns ("Attempting X leads to error Y; the fix is Z").
- Environment requirements ("Feature X requires service Y to be running").

The extraction prompt asks for structured output. Each extracted fact is a JSON object:

```
{
  "topic": "auth",
  "statement": "The auth module uses JWT with RS256 signing",
  "evidence": "Agent discovered RS256 config in auth/jwt.py line 42",
  "category": "decision",
  "source_files": ["auth/jwt.py"]
}
```

Fields: `topic` (short label), `statement` (natural-language fact), `evidence` (quote or reference from the transcript supporting the fact), `category` (one of: `causal`, `decision`, `failure`, `environment`), `source_files` (optional list of repository-relative file paths referenced in the evidence — used for change-triggered staleness decay). Structured output via the harness (`structured_output` capability) ensures parseable results. If the harness does not support structured output, the Maintainer's response is parsed as a JSON code block from the final message.

Extracted facts are written to the knowledge store with state `proposed` and initial confidence **0.3**. The confirmation and supersession logic (described above) runs on write — each new fact is compared against existing facts before insertion.

Extraction runs as a separate Maintainer session dispatched by the engine after each Coder group completes. It runs in a background thread outside the dispatch pool — it does not consume a dispatch slot or block downstream nodes, even in single-threaded Phase 1 dispatch. Extraction failure is logged but does not block spec execution — knowledge extraction is best-effort. No automatic retry on failure.

**Timing guarantee:** Because extraction is asynchronous and non-blocking, facts extracted from session N are **not guaranteed** to be available in session N+1's context assembly if N+1 is dispatched immediately after N completes. Facts become available as soon as the extraction Maintainer writes them to the knowledge store. In practice, extraction completes quickly (single LLM call on a transcript), so facts are typically available within minutes. For the same plan run, later sessions benefit from earlier extractions. Across separate `af run` invocations, all prior extractions are available.

### Context Assembly from Knowledge

When preparing a Coder session, the context assembler queries the knowledge store for facts relevant to the task. The query uses the task group description and the affected file paths as search terms.

Relevant facts are injected into the session prompt as structured context — not as a wall of text, but as a categorized list: "Known facts about `auth/jwt.py`," "Previous failure patterns for payment integration tests."

The system caps the injected knowledge at a token budget (configurable, default 2000 tokens, measured by approximate character count / 4). The budget is aggregate across all knowledge types (facts, findings, session summaries). If more relevant results exist than fit in the budget, they are ranked by composite score and truncated. This prevents knowledge injection from consuming the entire context window.

**Note:** Knowledge injection is delivered in Phase 1 as part of the feedback loop (see ch 05 §Phase 1). Context assembly queries the knowledge store from the first spec execution.

### Knowledge Sharing (cq Protocol)

The knowledge system can export and import knowledge units in a format compatible with mozilla-ai/cq, enabling cross-project and cross-team learning.

**Export:** Facts with confidence above a threshold can be exported as knowledge units with domain tags, the fact statement, metadata (confidence, confirmation count, timestamps), and provenance (project name, session ID). Exported units are scrubbed of project-specific paths and identifiers.

**Import:** Knowledge units from external sources (a team cq server, another project's export) can be imported into the local store. Imported facts start at low confidence and must be confirmed by local sessions before they influence context assembly.

This is explicitly a future integration point, not a v3 launch requirement. The knowledge store's internal format is designed to be compatible, so the export/import protocol can be added without schema changes.

## Work Items — Context-First Work Management

Work items are a first-class record type in the knowledge store. They represent actionable problems — technical debt, spec drift, test coverage gaps, deprecated API usage — stored as structured, semantically-searchable records alongside facts, findings, and session summaries. Work items are not a night-shift internal; they are a general-purpose knowledge record created by multiple subsystems (see **Work Item Producers** below).

### Why Not Issues

Traditional agent systems that discover problems face a routing question: where do the discoveries go? The obvious answer — file an issue on GitHub/Jira/Linear — creates three problems:

1. **Platform coupling.** The agent system now depends on an external tracker. Every team's tracker is different: different APIs, different field schemas, different workflows. The agent either supports one tracker (limiting adoption) or becomes a tracker integration platform (scope explosion).
2. **Signal fragmentation.** Machine-discovered issues live in the same queue as human-filed bugs. Labels and tags are the only distinction. The tracker's UI, designed for human triage, becomes cluttered with high-volume, low-context machine output. Humans start ignoring the noise.
3. **Lost actionability.** A GitHub issue is freeform text. The structured metadata that made the discovery actionable — affected files, suggested fix, deduplication fingerprint, severity classification — either gets flattened into markdown or lost entirely. A downstream agent that wants to fix the issue has to re-parse what the upstream agent already knew.

v2 hit all three: it filed GitHub issues for every night-shift discovery. It worked, but it was the wrong abstraction.

### What Makes Work Items Different

The schema of a work item — title, description, severity, affected files, suggested fix — is deliberately similar to what you'd put in a well-structured issue template. The record format is not the innovation. **Co-location is.**

Work items live in the same DuckDB store as facts about the codebase, findings from code review, session summaries, and metrics. They are embedded alongside facts and participate in the same semantic search. This co-location enables three capabilities that an external tracker cannot provide:

1. **Knowledge-assembled fix context.** When the fix pipeline picks up a work item, the context assembler queries the knowledge store for facts whose `source_files` overlap with the work item's `affected_files`. The Coder fixing "auth module has 3 untested error paths" is pre-briefed with "the auth module uses JWT with RS256 signing" and "running tests requires DATABASE_URL." A GitHub issue can contain this information in comments if someone manually adds it. The knowledge store assembles it automatically because the data is structured and co-located. See **Knowledge-Integrated Fix Context** below.

2. **Cross-type semantic search.** `af knowledge query "authentication problems"` returns facts ("auth uses JWT with RS256"), findings ("Reviewer flagged missing token expiry check"), and work items ("auth module has 3 untested error paths") in a single ranked result set. One query across everything the system knows — not separate queries to separate stores.

3. **Structured fix history.** Work items carry machine-readable records of prior fix attempts — which sessions tried, what they attempted, what the outcomes were. When a second fix attempt runs, the Coder receives "Session X tried approach A and failed because Y" as structured context, not a human-written comment thread. Failed approaches are not repeated.

External trackers can store some of this information in custom fields and linked items. But they cannot assemble context from it automatically, they cannot embed and search it semantically, and they cannot inject it into an agent's prompt. The work item model's value is not in what it stores — it's in what the system does with it because it controls the store.

### Work Item Schema

Work item record fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `title` | text | Short description of the issue |
| `description` | text | Detailed explanation |
| `category` | text | Hunt category that found it (e.g., "linter-debt") |
| `affected_files` | text[] | List of file paths involved |
| `severity` | enum | `critical`, `major`, `minor`, `info` |
| `suggested_fix` | text | High-level approach for fixing |
| `fingerprint` | text | Deduplication hash |
| `status` | enum | `discovered`, `approved`, `in_progress`, `fixed`, `wontfix` |
| `source_session_id` | UUID (FK) | Hunt session that found it |
| `created_at` | timestamp | Discovery time |
| `updated_at` | timestamp | Last status change |
| `embedding` | float[384] | Embedding vector for semantic search across all knowledge types |
| `fix_attempts` | JSON[] (nullable) | Ordered list of fix attempt records: `{session_id: UUID, outcome: str, attempted_at: timestamp}`. Populated by the fix pipeline when a fix session completes (success or failure). Null for items that have never entered the fix pipeline. |

**Work item status transitions:**

| From | To | Trigger |
|------|----|---------|
| `discovered` | `approved` | `af nightshift approve <id>`, or automatic in `--auto` mode |
| `discovered` | `wontfix` | `af nightshift approve <id> --wontfix` (operator decision) |
| `approved` | `in_progress` | Fix pipeline picks up the item (fix timer fires, item is next in queue) |
| `in_progress` | `fixed` | Coder+Verifier pipeline completes successfully and merges |
| `in_progress` | `approved` | Fix attempt fails after exhausting retries — item returns to queue. The failed attempt is appended to `fix_attempts` with the session ID and outcome. |
| Any except `fixed` | `wontfix` | Operator marks as will-not-fix |

**Fingerprint algorithm:** The fingerprint is a SHA-256 hash of `(category, sorted(canonical_file_paths), normalized_description)`. Normalization: `normalized_description` is the description lowercased, with all runs of whitespace (spaces, tabs, newlines) replaced by a single space, and leading/trailing whitespace stripped. `canonical_file_paths` are resolved to repository-relative paths (no leading `./`), sorted lexicographically. Non-ASCII characters are preserved.

**Deduplication behavior:** If a critic candidate's fingerprint matches an existing work item:
- Status `discovered`, `approved`, or `in_progress` → candidate is discarded (no duplicate created).
- Status `fixed` or `wontfix` → a new `discovered` work item is created with the same fingerprint. This represents a re-occurrence of a previously resolved issue (the fix may have regressed, or the `wontfix` decision may need revisiting). The new item has no structural link to the old one — the shared fingerprint is the relationship.
- Candidates with similar but non-identical fingerprints always create separate work items. Near-duplicate detection is not performed — fingerprint match is exact. Deduplication is exact fingerprint match — the same issue type in different files produces different work items (different fingerprints) unless the issue is project-wide (e.g., "dependency X is outdated" with no file-specific paths).

Work items can be queried, triaged, and prioritized from the CLI (`af nightshift list`, `af nightshift triage`). They can optionally be synchronized to GitHub Issues via `af nightshift sync-issues` — a one-way push, not a bidirectional sync. The knowledge store remains the system of record.

### Knowledge-Integrated Fix Context

This is where co-location pays off. When the fix pipeline picks up an approved work item, context assembly goes beyond the work item record itself:

1. **Related facts.** Query facts where `source_files` overlaps with the work item's `affected_files`. Inject as categorized context: "Known facts about `auth/jwt.py`: [list]." The Coder receives institutional knowledge about the area it's modifying — architectural decisions, environment requirements, known failure patterns — not just a bug description.

2. **Prior session history.** Query session summaries where the `spec_name` or `attempted` fields reference the affected files. Inject as: "Previous work in this area: Session X attempted Y and achieved Z." This prevents the Coder from repeating approaches that already failed or duplicating work that already succeeded.

3. **Related work items.** Query other work items (any non-`wontfix` status) whose `affected_files` overlap with the current item. Inject as: "Other known issues in this area: [list]." The Coder can consider related problems and avoid fixes that would exacerbate adjacent issues.

4. **Fix attempt history.** If the work item has prior `fix_attempts`, query the session summaries for those sessions. Inject the `struggled_with` and `achieved` fields. The Coder knows what was tried, what worked partially, and what failed — as structured data, not a comment thread to parse.

Context assembly for fixes follows the same token budget model as spec execution context injection (default 2000 tokens, configurable). Related facts, session history, related work items, and fix attempt history compete for budget space, ranked by the composite score. If the work item's area is well-known (many high-confidence facts), the Coder gets a rich briefing. If the area is new (few or no facts), the briefing is thin — and the extraction after the fix session will populate the knowledge store for next time.

**This is what "context-first" means in practice.** The fix session is not "here's a bug, go fix it." It is "here's a bug, here's everything the system knows about the affected area, here's what was tried before, here are related problems." A GitHub issue cannot assemble this context because it doesn't have access to the project's knowledge graph. The knowledge store can, because facts, findings, work items, and session summaries are peers in the same queryable system.

### Work Item Producers

Work items are not exclusively a night-shift artifact. Any subsystem that discovers actionable problems can write work items to the knowledge store:

| Producer | Category Prefix | Description |
|----------|----------------|-------------|
| Night-shift hunt | `linter-debt`, `dead-code`, `test-coverage`, etc. | Primary producer. Eight built-in categories + custom hunters. |
| Spec audit (`af-spec-audit`) | `spec-drift` | Drift findings from compliance audits. See ch 02 §af-spec-audit. |
| Reviewer (audit-review mode) | `review-finding` | Findings from audit-review that identify issues beyond the current spec's scope. Optional — enabled via `archetype.reviewer.promote_findings` config. |
| Manual entry | Any | `af work-item create --title "..." --affected-files "..."` allows humans to add structured work items for agent execution. |

The multi-producer model is what makes work items a context system rather than a night-shift feature. All producers write to the same DuckDB table, use the same fingerprint deduplication, and their work items participate in the same semantic search. A query for "authentication problems" returns night-shift-discovered test coverage gaps, spec-audit-discovered drift, and Reviewer findings — regardless of origin.

**Future producers.** The cq import protocol (Phase 5) can import work items from other projects. Cross-project work items (e.g., "upstream library X deprecated API Y, all consumers need to migrate") are a natural extension of the multi-producer model.

### Team Visibility

The "system of record is local" decision has a team visibility cost. Team members without `af` CLI access cannot see work items. The team's existing triage workflow (GitHub Projects, Linear boards, Jira sprints) is disconnected from agent-fox's discoveries. This is a deliberate trade-off, not an oversight.

**What you gain from local-first:**
- No platform coupling — agent-fox works without GitHub/Linear/Jira.
- Structured metadata preserved for machine consumption — not flattened to markdown.
- Semantic queryability across all knowledge types in one store.
- Automatic context assembly for fixes (the core innovation).

**What you lose:**
- Team members without CLI access can't see discoveries until they're synced.
- No comment threads, assignments, or linked PRs on work items.
- The team's existing triage workflow is a separate system.

**Mitigations:**
- `af nightshift sync-issues` pushes to GitHub/Linear as a read-only view. The sync includes knowledge context (related facts, fix attempt history) in the issue body — making synced issues richer than v2's bare issues, even though they're a secondary artifact.
- `PROJECT_MEMORY.md` includes a work item summary section when work items exist (see Project Memory File below).
- `af status --work-items` provides a quick terminal view without the full CLI workflow.
- For teams that need full bidirectional sync (work item status updated from GitHub, comments imported), a sync adapter is a Phase 5 extension point. The schema supports it — `source_session_id` can be nullable for externally-created items. But bidirectional sync adds complexity that the 1-5 person target team does not need at launch.

See ch 06 "Local-first work items have a team visibility cost" for ongoing monitoring.

---

## Night-Shift Mode

Night-shift is the autonomous maintenance daemon. It runs continuously, discovering technical debt and fixing it. The core loop is simple: **hunt** for problems, **triage** what was found, **fix** approved items. Night-shift is the primary producer of work items (see **Work Items** above for the record type, schema, and knowledge integration). This section covers the hunt categories, fix pipeline, and daemon lifecycle.

### Fix Pipeline

The fix pipeline takes an approved work item and attempts to resolve it. The pipeline is two agents: Coder → Verifier. v2 used a three-agent pipeline (Skeptic → Coder → Verifier), but the Skeptic pre-review was rarely useful for night-shift fixes — the "spec" is auto-generated from the work item and is inherently narrow in scope. Review adds latency without proportional quality improvement for mechanical repairs.

For high-severity work items (security vulnerabilities, failing tests), a Reviewer pre-review can be optionally enabled via config. The default is off.

#### Lightweight Fix Specs

Night-shift fixes do not use the full five-artifact spec package. Instead, the fix pipeline generates a **lightweight spec** — a minimal, ephemeral task description assembled deterministically from the work item:

- **Task description:** The work item's `title`, `description`, `suggested_fix`, and `affected_files` are formatted into a structured prompt that the Coder receives as its task body.
- **Knowledge context:** The context assembler injects related facts, prior session history, related work items, and fix attempt history from the knowledge store (see **Knowledge-Integrated Fix Context** above). This is the knowledge briefing that makes fix sessions more effective than raw bug-fix prompts.
- **Success criteria:** The fix must not introduce test regressions (test pass rate >= baseline) and must resolve the specific issue identified by the work item (e.g., linter warning no longer fires on the affected files).
- **No artifacts on disk:** Lightweight specs are not persisted to `.specs/`. They exist only in the fix session's context. This is intentional — night-shift fixes are narrow, mechanical repairs that don't warrant the overhead of a full spec package.

The Verifier receives the same success criteria and validates them after the Coder completes.

### Hunt Categories

The eight hunt categories from v2 are retained. All categories run in parallel. Each category runs its tool, then passes the raw output through a lightweight LLM critic call. The critic is implemented as a single `ClaudeCodeHarness` session (standard model tier, permission callback restricts to read-only) — not a full Maintainer session. The critic receives the tool output and the category definition, and produces structured work item candidates as JSON. One critic call per category. Deduplication against existing work items uses fingerprint matching after the critic produces candidates.

| Category | Tool / Analysis | Critic Input | Output |
|----------|----------------|--------------|--------|
| Linter Debt | Run configured linter (ruff by default) | Linter warnings + affected file snippets | Work items per distinct warning pattern |
| Dead Code | Static analysis (vulture or equivalent) | Unused function/import list | Work item per dead code cluster |
| Test Coverage | Coverage report (pytest-cov) | Uncovered files/functions | Work item per uncovered module |
| Dependency Freshness | Check outdated packages (pip-audit, npm outdated) | Outdated dependency list with current/latest versions | Work item per outdated dependency |
| Deprecated API | Grep for known deprecation patterns + LLM scan | Deprecated call sites with context | Work item per deprecated usage |
| Documentation Drift | Compare README/docstrings against function signatures | Mismatched documentation + code | Work item per drifted section |
| TODO/FIXME | Grep for `TODO`, `FIXME`, `HACK`, `XXX` markers | Marker text + surrounding context | Work item per actionable marker |
| Quality Gate | Run project-configured quality command (e.g., `make check`) | Command output, exit code | Work item per failing check |

Categories that require tools not present in the project (e.g., no linter configured) are skipped with a warning. If a critic call fails (API error, rate limit, timeout), the category is skipped for this hunt cycle with a warning logged to `af nightshift list` output. The raw tool output is not converted to work items without critic consolidation — the critic's role is to filter noise, and bypassing it would create low-quality work items.

#### Custom Hunt Categories

The eight built-in categories are defaults, not the universe. Teams can define project-specific hunters by placing TOML files in `.agent-fox/hunters/`:

```
.agent-fox/hunters/
  accessibility.toml
  performance_budget.toml
```

Each hunter file defines the full category tuple — what to run, how to interpret the output, and how to classify the results:

```toml
[hunter]
name = "accessibility"
description = "WCAG compliance audit via pa11y"
severity_default = "major"

[tool]
command = "pa11y-ci --reporter json"
prerequisites = ["pa11y-ci"]    # Required binaries; category skipped if absent

[critic]
prompt = """
Analyze the following accessibility audit output. For each violation:
- Classify severity: critical if WCAG AA failure, major if WCAG AAA, minor otherwise
- Identify the affected file or component
- Suggest a concrete fix approach
Output structured work item candidates as JSON.
"""

[output]
format = "json"
```

Field definitions:

- **`hunter.name`** — Unique category name. Used in work item `category` field and in `nightshift.enabled_categories` config.
- **`hunter.description`** — One-line description for `af nightshift list` output.
- **`hunter.severity_default`** — Default severity if the critic does not classify a finding.
- **`tool.command`** — Shell command to run. Executed inside the hunt session's container with the workspace mounted. Must produce output on stdout.
- **`tool.prerequisites`** — List of binaries that must be on `PATH`. If any are missing, the category is skipped with a warning (same behavior as built-in categories with missing tools).
- **`critic.prompt`** — The prompt template for the LLM critic call. The critic receives this prompt plus the tool's stdout. It must produce structured work item candidates as JSON.
- **`output.format`** — Expected format of the tool's output (`json` or `text`). Determines how the output is passed to the critic (as a JSON block or as raw text).

**Override semantics:** If a custom hunter has the same `name` as a built-in category, the custom definition replaces the built-in. This lets teams swap tool commands (e.g., replace `ruff` with `flake8` for the Linter Debt category) or adjust critic prompts without forking agent-fox.

**Category enablement:** Custom categories are enabled by default when their file exists. To disable a custom category without deleting the file, remove it from `nightshift.enabled_categories` in project config. Built-in categories that are not overridden remain active unless explicitly removed from the enabled list.

**No remote registry.** Hunter definitions are local files, shared by committing them to the repository. A remote registry (discovery, download, versioning) introduces trust and security concerns — you are downloading shell commands that will be executed in your containers. Local-first is the right model for v3. A registry could be layered on later if demand and a trust model justify it.

### Lifecycle

Night-shift runs as a daemon process with two independent timers:
- **Hunt timer** (default: 4 hours) — Scan for problems.
- **Fix timer** (default: 15 minutes) — Check for approved work items and execute fixes.

Both fire immediately on startup. Cost and session limits enforce a ceiling. Graceful shutdown on SIGINT/SIGTERM.

In `--auto` mode, all discovered work items are automatically approved for fixing. In default mode, a human must approve via `af nightshift approve <id>` (the CLI command wraps `knowledge.work_items.approve(id)`).

## Project Memory File

For tools and workflows that don't have access to the DuckDB knowledge store (e.g., a human reading the codebase, a different agent framework), the knowledge system can export a `PROJECT_MEMORY.md` file to the project root.

This is a curated, size-capped markdown file (default cap: 4000 tokens, configurable via `knowledge.memory_size_cap`) that summarizes the most important, highest-confidence facts about the project. It follows the "update don't append" pattern: each export regenerates the file from the current knowledge state rather than appending to it.

**Regeneration algorithm:** The export is deterministic — it queries all confirmed facts ordered by confidence descending, then by `created_at` ascending (oldest first for ties), then by fact UUID ascending (final tiebreaker for identical timestamps). Facts are grouped by topic (topics sorted alphabetically), and rendered as a markdown document with topic headings and fact bullet points. Facts below confidence 0.5 are excluded. The output is truncated at the size cap. No LLM is involved in regeneration — this keeps the operation free and predictable.

The export is triggered manually (`af knowledge export-memory`) or automatically after each successful spec execution (defined as: all task groups for that spec completed with status `success` or `partial`, and the Verifier passed). The file is committed to git, making project knowledge portable and version-controlled.

This is not a replacement for the knowledge store — it is a lossy projection for contexts where the store is unavailable.

## Cost Management

v3 treats cost as a first-class constraint, not an afterthought. Cost is measured in USD, computed from token counts at model-specific rates.

**Per-session budgets:** Each session has a turn budget (default: 200 turns) and a token budget (default: 500K tokens). Both are configurable per-archetype in project config. When the turn count reaches 90% of the budget, the orchestrator injects a wind-down message instructing the agent to commit progress and summarize remaining work. When the budget is exhausted, the session is stopped and assessed as partial or failed.

**Per-spec budgets:** The sum of all session costs for a spec is tracked against a configurable ceiling (config key: `execution.spec_cost_ceiling_usd`, no default — must be set explicitly for enforcement). Per-spec ceilings are enforced independently of each other and independently of the project ceiling. Exceeding a spec's ceiling halts execution of that spec only — other specs continue. The spec's nodes are marked `cost-blocked` and their downstream nodes are blocked. Per-spec costs do count toward the project-wide ceiling.

**Per-project budgets:** Night-shift and spec execution share a project-wide cost ceiling (config key: `execution.cost_ceiling_usd`, no default — must be set explicitly). Night-shift's ceiling defaults to 50% of the project ceiling (config key: `nightshift.cost_ceiling_usd`). If `execution.cost_ceiling_usd` is not set, `nightshift.cost_ceiling_usd` also defaults to none (cost tracking is informational only). When no ceiling is configured, cost tracking is informational only. When configured:
- At **80%** of the ceiling (configurable as `execution.cost_warning_ratio`, default: 0.8): emit a warning to stderr and CLI status.
- At **100%** of the ceiling: graceful shutdown — complete in-flight sessions but dispatch no new ones.

**Reporting:** `af status` includes cost breakdowns by spec, archetype, and model tier. `af cost` gives detailed per-session cost reporting.

Cost data is stored as metrics in the knowledge store, making it queryable for trend analysis.

---

*Previous: [03 — Archetypes, Planning & Execution](./03-execution.md)*
