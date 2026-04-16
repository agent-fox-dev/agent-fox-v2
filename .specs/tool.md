Current State: What's In the Box

The Database (.agent-fox/knowledge.duckdb)

31 tables, organized into these domains:

┌──────────────┬───────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────┐
│    Domain    │                        Tables                         │                                What's Stored                                │
├──────────────┼───────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Plan state   │ plan_nodes, plan_edges, plan_meta                     │ Task graph, dependencies, completion status                                 │
├──────────────┼───────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Run tracking │ runs, session_outcomes                                │ Per-run totals, per-session tokens/cost/duration/errors/commit SHA          │
├──────────────┼───────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Knowledge    │ memory_facts, memory_embeddings, fact_causes          │ Extracted facts, vector embeddings, causal chains                           │
├──────────────┼───────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Entity graph │ entity_graph, entity_edges, fact_entities             │ Code entities (files, classes, functions), relationships, fact-entity links │
├──────────────┼───────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Reviews      │ review_findings, verification_results, drift_findings │ Reviewer/verifier verdicts, oracle drift                                    │
├──────────────┼───────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Complexity   │ complexity_assessments, execution_outcomes            │ Predicted vs. actual task difficulty                                        │
├──────────────┼───────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Audit        │ audit_events (30+ event types)                        │ Structured audit trail with JSON payloads                                   │
├──────────────┼───────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
│ Telemetry    │ tool_calls, tool_errors                               │ Debug-level tool invocation tracking                                        │
└──────────────┴───────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────┘

What Humans Can See Today

Exactly one thing: docs/memory.md — a flat rendering of active facts grouped by category. That's it. Everything else requires opening a DuckDB CLI or writing Python.

What's Invisible

┌────────────────────────────────────┬─────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────┐
│            Information             │               Where It Lives                │                                  Why It Matters                                   │
├────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ Causal chains between facts        │ fact_causes                                 │ Understanding why a pattern exists — "this convention exists because of that bug" │
├────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ Entity graph                       │ entity_graph + edges                        │ Which facts relate to which files/classes — spatial orientation                   │
├────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ Session history                    │ session_outcomes                            │ Cost tracking, failure patterns, retry rates                                      │
├────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ Run summaries                      │ runs                                        │ How many sessions, total cost, success rate                                       │
├────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ Confidence decay                   │ memory_facts.confidence                     │ Which facts are becoming stale                                                    │
├────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ Supersession history               │ memory_facts.superseded_by                  │ What was replaced by what                                                         │
├────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ Signal contributions               │ Computed transiently                        │ Why the retriever ranked a fact high — keyword? vector? entity? causal?           │
├────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ Consolidation decisions            │ Not persisted at all                        │ Merge/prune/promote choices have no audit trail                                   │
├────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ Review/drift findings              │ review_findings, drift_findings             │ Quality trends over time                                                          │
├────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ Complexity predictions vs. actuals │ complexity_assessments + execution_outcomes │ Are estimates improving?                                                          │
└────────────────────────────────────┴─────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────┘

---
The Two Audiences

A) Agents (during sessions)

- Currently get knowledge via AdaptiveRetriever — 4-signal RRF fusion injected into the system prompt
- Cannot query the DB ad-hoc. Can't ask "what went wrong last time this file was touched?" or "what's the causal chain behind this convention?"
- Cannot see their own session history, cost, or failure patterns

B) Humans (debugging, auditing, understanding)

- Get docs/memory.md — a flat list
- Cannot see session cost trends, failure rates, which specs are expensive
- Cannot explore the causal graph ("why does this convention exist?")
- Cannot see what knowledge the agent was given for a specific session
- Cannot audit consolidation decisions (merges, promotions, pruning)

---
Workshop: Making It Accessible

Here are several ideas, ranging from quick wins to deeper features. Let's discuss which resonate.

Idea 1: af knowledge CLI subcommand group

A set of read-only inspection commands:

af knowledge list                    # list active facts (with filters)
af knowledge show <fact-id>          # full detail including causal links + entities
af knowledge search "keyword"        # keyword + vector search
af knowledge graph <file-path>       # show facts linked to a file via entity graph
af knowledge causal <fact-id>        # trace causal chain (causes + effects)
af knowledge stats                   # summary: fact count by category, avg confidence, staleness

For agents: These could double as tool calls — an agent could af knowledge search "DuckDB migration" to find relevant prior learnings beyond what the retriever surfaced.

Idea 2: af status / af history for run/session inspection

af history runs                      # list recent runs (date, sessions, cost, status)
af history sessions --run <id>       # sessions in a run (tokens, duration, pass/fail)
af history cost --last 7d            # cost breakdown over time
af history failures                  # recent failures with error messages

This gives humans visibility into operational health and cost.

Idea 3: Richer docs/memory.md rendering

Enhance the existing render_summary() to include:
- Causal chains (indented under facts, like "caused by: ...")
- Entity links (which files a fact relates to)
- Confidence with staleness indicator
- Supersession history ("replaces: older fact content")

Cheap to implement, immediately useful, and already git-tracked.

Idea 4: Export/dump commands

af knowledge export --format json    # full DB dump for external tools
af knowledge export --format dot     # causal graph as Graphviz DOT
af knowledge export --format csv     # for spreadsheet analysis

Enables humans to use their own tools (Graphviz, Excel, jq) for analysis.

Idea 5: Retrieval transparency

When the retriever assembles context for a session, persist:
- Which facts were selected
- What each signal scored them
- What intent profile was used
- What was included/truncated by token budget

This creates an audit trail: "the agent got these facts because of these signals." Useful for debugging when an agent makes a bad decision because it was missing (or given wrong) knowledge.

Idea 6: Agent self-query tools

Give agents MCP tools or internal commands to query the knowledge DB during sessions:
- "What facts exist about this file?"
- "What happened in the last session that touched this spec?"
- "What causal chain led to this convention?"

This goes beyond the pre-session retriever injection — it gives agents on-demand access to institutional memory.