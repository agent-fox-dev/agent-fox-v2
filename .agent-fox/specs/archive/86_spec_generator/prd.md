# PRD: Spec Generator (Issue-to-Spec Pipeline)

## Summary

Implement the `SpecGeneratorStream` work stream for the daemon, enabling
agent-fox to autonomously generate complete specification packages from
GitHub issues labeled `af:spec`. The generator analyzes issue content,
drives a multi-turn clarification loop via issue comments, and produces
the standard 5-file spec package in `.specs/`, committed to develop via
the standard feature-branch workflow.

## Motivation

Today, specification creation requires a human to run the interactive
`/af-spec` skill in Claude Code, manually answering clarification
questions and reviewing each document. This blocks the fully autonomous
pipeline: a user cannot file an issue and walk away expecting the fox to
produce both specs and implementation.

With the spec generator, the workflow becomes:

1. Human creates GitHub issue, labels it `af:spec`
2. Fox analyzes the issue, asks clarification questions via comments
3. Human responds at their pace
4. Fox generates the spec package and commits to develop
5. The spec executor stream picks up the new spec and implements it

Zero human intervention for well-defined issues. Minimal intervention
(answering clarifying questions) for ambiguous ones.

## Goals

1. Autonomously generate spec packages from GitHub issues.
2. Multi-turn clarification via GitHub comments (max 3 rounds, configurable).
3. Stateless design — derive progress from labels and comment history.
4. Graceful escalation for un-implementable issues.
5. Per-spec cost cap to prevent runaway analysis.
6. AI-powered duplicate spec detection before generation.

## Non-Goals

- Supporting attachments (images, PDFs) in issue analysis (text only).
- Deep codebase analysis (uses project structure + existing specs, not
  full code exploration).
- Interactive confirmation between spec documents (fully autonomous).
- Modifying specs after generation (human edits spec files directly).
- Parallel spec generation (issues are processed sequentially, one per cycle).

## Workflow

```
Human creates issue + labels af:spec
         |
         v
  1. DISCOVER: poll for af:spec and af:spec-pending issues
         |
         v
  2. INTAKE: fetch issue body, all comments, referenced issues
         |
         v
  3. ANALYZE: AI reads issue + context, identifies gaps
         |
    +----+----+
  clear?    ambiguous?
    |           |
    v           v
  5. GEN     4. CLARIFY: post numbered questions,
  specs         label af:spec-pending, wait
                     |
              (human replies)
                     |
                     v
              re-analyze with new comments
              (max 3 rounds)
                     |
                +----+----+
            resolved?  still unclear?
                |           |
                v           v
              5. GEN     6. ESCALATE: comment + af:spec-blocked
              specs
         |
         v
  7. LAND: feature branch, commit, merge to develop, close issue
```

### Sequential Processing

The generator processes one issue per cycle. If multiple `af:spec` issues
exist, the oldest (by creation date) is processed first. Remaining issues
are picked up in subsequent cycles. This prevents spec-number collisions
and keeps resource usage predictable.

## Label State Machine

| Label | Meaning |
|-------|---------|
| `af:spec` | Ready for pickup (initial state) |
| `af:spec-analyzing` | Fox is analyzing the issue |
| `af:spec-pending` | Waiting for human clarification |
| `af:spec-generating` | Fox is generating spec documents |
| `af:spec-done` | Spec created successfully |
| `af:spec-blocked` | Too many open questions after max rounds |

**Transitions:**

- `af:spec` -> `af:spec-analyzing` (fox picks it up)
- `af:spec-analyzing` -> `af:spec-pending` (questions posted, remove `af:spec-analyzing`)
- `af:spec-analyzing` -> `af:spec-generating` (clear enough, remove `af:spec-analyzing`)
- `af:spec-pending` -> `af:spec-analyzing` (new human comment detected, remove `af:spec-pending`)
- `af:spec-analyzing` -> `af:spec-blocked` (max rounds, still ambiguous, remove `af:spec-analyzing`)
- `af:spec-generating` -> `af:spec-done` (spec committed, issue closed, remove `af:spec-generating`)

Each transition removes the old label and adds the new one atomically (assign
new label first, then remove old label). This requires `remove_label()` on
the platform — see Platform Extensions below.

## Platform Extensions

This spec adds two new methods to `GitHubPlatform` and `PlatformProtocol`:

### `remove_label(issue_number, label)`

Remove a label from an issue. Uses `DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels/{label}`.
Silently succeeds if the label is not present (idempotent).
Raises `IntegrationError` on API failure (non-404 errors).

### `list_issue_comments(issue_number)`

List all comments on an issue, ordered chronologically.
Uses `GET /repos/{owner}/{repo}/issues/{issue_number}/comments`.
Returns `list[IssueComment]` where `IssueComment` is a new frozen dataclass:

```python
@dataclass(frozen=True)
class IssueComment:
    id: int
    body: str
    user: str        # GitHub login of the comment author
    created_at: str  # ISO 8601 timestamp
```

Both methods are added to `PlatformProtocol` as well.

## Clarification Comment Format

```markdown
## Agent Fox -- Clarification Needed

I've analyzed this issue and need a few clarifications before I can
create a complete specification.

### Questions

1. **<Topic>**: <Question>
2. **<Topic>**: <Question>
3. **<Topic>**: <Question>

---

*Please reply to this comment addressing the numbered questions.
I'll incorporate your answers and either ask follow-up questions
or generate the specification.*

*Round N of M*
```

## Completion Comment Format

```markdown
## Agent Fox -- Specification Created

I've generated a complete specification from this issue.

**Folder:** `.specs/NN_spec_name/`

| File | Content |
|------|---------|
| `prd.md` | Product requirements |
| `requirements.md` | EARS acceptance criteria (N requirements) |
| `design.md` | Architecture and interfaces |
| `test_spec.md` | Test contracts (N test cases) |
| `tasks.md` | Implementation plan (N task groups) |

The spec will be picked up automatically by the spec executor.

Commit: `<hash>`
```

## Escalation Comment Format

```markdown
## Agent Fox -- Specification Blocked

After N rounds of clarification, there are still too many open
questions to produce a reliable specification.

### Remaining Open Questions

1. <unresolved question>
2. <unresolved question>

### Suggestion

Please rewrite the original issue with more detail addressing the
questions above, then re-label it `af:spec` for another attempt.
```

## Spec Generation Strategy

The generator reuses the logic of the existing `/af-spec` skill
(`~/.claude/skills/af-spec`) as a library, but runs non-interactively:

1. **PRD creation**: The issue body (plus clarification answers from
   comments) becomes the PRD. A `## Source` section is appended linking
   back to the GitHub issue URL.
2. **Context gathering**: Read existing specs in `.specs/`, project
   structure, and `steering.md` — same as the skill's Step 2.
3. **Document generation**: Generate `requirements.md`, `design.md`,
   `test_spec.md`, and `tasks.md` sequentially via Anthropic API calls
   (`core/client.py`), following the same structure and rules as the
   `/af-spec` skill output.
4. **No manual review gates**: Unlike the interactive skill, the generator
   does not pause for user confirmation between documents. All five
   documents are generated autonomously in one pass.

Model tier: ADVANCED by default (configurable via `spec_gen_model_tier`
in `[night_shift]` config).

## Relation Harvesting

When analyzing an issue, the generator fetches:

- **Issue body and all comments** (via `list_issue_comments()`)
- **Referenced issues** (parsed from `#N` mentions in body/comments):
  fetch body and comments of each referenced issue for context.
  If a referenced issue is inaccessible (404, permissions), log a
  warning and skip it — do not fail the analysis.
- **Existing specs in `.specs/`** (for overlap/dependency detection)
- **Project steering directives** (`.specs/steering.md`)

## Duplicate Detection

Before generating a spec, the generator uses an AI agent call to check
whether an existing spec in `.specs/` already covers the same scope.
The agent receives the issue body/title and a summary of each existing
spec (name + PRD title/summary). If a likely duplicate is detected:

1. Post a comment on the issue asking whether to supersede or skip.
2. Label the issue `af:spec-pending` and wait for human response.
3. On "supersede": generate the new spec with a `## Supersedes` section.
4. On "skip" or no response: leave the issue as-is.

## Landing Workflow

When the spec package is complete:

1. Create a feature branch from `develop`:
   `spec/<spec_name>` (e.g., `spec/87_webhook_support`)
2. Write all 5 spec files to `.specs/NN_spec_name/`
3. Commit with message: `feat(spec): generate NN_spec_name from #<issue>`
4. Merge to `develop` (or create draft PR, per `merge_strategy` config)
5. Post completion comment on the issue
6. Label the issue `af:spec-done`, remove `af:spec-generating`
7. Close the issue

This follows the same git workflow as any other code change in the project.

## Guardrails

- **Max clarification rounds**: 3 (configurable via `max_clarification_rounds`
  in `[night_shift]` config)
- **Max issue age**: Skip issues with `af:spec` label where the last
  activity (comment or label change) is older than 30 days
- **Duplicate detection**: AI-powered scope overlap check against existing
  specs before generating (see above)
- **Per-spec cost cap**: `max_budget_usd` (default $2.00, configurable in
  `[night_shift]`). If exceeded during generation, abort the current spec,
  post a comment explaining the budget was exceeded, and label the issue
  `af:spec-blocked`. Cost is also reported to the daemon's shared budget.
- **Fox comment signature**: All fox comments start with `## Agent Fox`
  for identification. Human comments are any comment that does not match
  this prefix.

## Configuration

New fields added to `NightShiftConfig` (in `[night_shift]` config section):

```toml
[night_shift]
max_clarification_rounds = 3    # max rounds before escalation
max_budget_usd = 2.0            # per-spec generation cost cap
spec_gen_model_tier = "ADVANCED" # model tier for spec generation
```

`spec_gen_interval` is already defined by spec 85 (default 300s).

## State Derivation

State is fully derived from GitHub labels and comment history. No local
state persistence. If the daemon restarts, it re-derives state on the
next poll:

- Issue has `af:spec` label -> ready for pickup
- Issue has `af:spec-pending` label + a new human comment after the last
  fox comment -> ready for re-analysis
- Issue has `af:spec-pending` label + no new human comment -> still waiting
- Issue has `af:spec-analyzing` label -> stale (fox crashed mid-analysis);
  reset to `af:spec` and re-process
- Issue has `af:spec-generating` label -> stale (fox crashed mid-generation);
  reset to `af:spec` and re-process

Fox comments are identified by checking if the comment body starts with
`## Agent Fox`.

Spec numbering: find the highest `NN_` prefix in `.specs/` and increment,
consistent with the existing convention in `spec/discovery.py`.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 85_daemon_framework | 2 | 1 | WorkStream protocol, SharedBudget, and config fields (spec_gen_interval, enabled_streams) defined in group 2; needed for test setup and stream interface |
