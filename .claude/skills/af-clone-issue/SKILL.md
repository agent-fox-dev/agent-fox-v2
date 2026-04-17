---
name: af-clone-issue
description: >
  Copies a GitHub issue (title, body, and all comments in chronological order)
  from an upstream repository into a fork or other target repo using the GitHub
  CLI and optional jq. Use when mirroring an issue locally, syncing a report into
  a fork, or when the user asks to copy, clone, or duplicate a GitHub issue across
  repos.
---

# Copy GitHub issue to another repo

## Project Steering Directives

If `.agent-fox/specs/steering.md` exists in the project root, read it and follow any
directives it contains before proceeding. These project-level directives apply
to all agents and skills working on this project.

GitHub does not offer “duplicate this issue to my fork.” This workflow creates a **new** issue on the target repository and replays upstream comments as new comments with attribution.

## Prerequisites

- **`gh`** installed and authenticated (`gh auth login`).
- Read access to the source issue; permission to open issues on the target repo.
- **`jq`** recommended for parsing comment JSON in the shell. If `jq` is missing, install it or expand the JSON manually (same fields: `user.login`, `created_at`, `body`).

## Parse URLs

From an issue URL `https://github.com/OWNER/REPO/issues/N`:

- Source: `SRC_OWNER`, `SRC_REPO`, `ISSUE_NUM` (= N).

From a repo URL `https://github.com/OWNER/REPO` or shorthand `OWNER/REPO`:

- Target: `DST_OWNER`, `DST_REPO`.

Reject references that resolve to a **pull request** (issues and PRs share numbers). After fetching the issue JSON, if `pull_request` is present, stop and tell the user this number is a PR, not an issue.

## Step 1 — Fetch the source issue

```bash
gh api "repos/${SRC_OWNER}/${SRC_REPO}/issues/${ISSUE_NUM}"
```

Confirm the response is an issue (`pull_request` must be absent). Note `title`, `body` (may be null), and `html_url`.

## Step 2 — Fetch all comments (paginated)

```bash
gh api "repos/${SRC_OWNER}/${SRC_REPO}/issues/${ISSUE_NUM}/comments" --paginate
```

The CLI returns a single JSON array of all pages. Sort by `created_at` ascending before replaying (e.g. pipe through `jq 'sort_by(.created_at)'`).

## Step 3 — Build the new issue body

Prepend a provenance block, then the original body (use empty string if `body` was null):

```markdown
> **Copied from** [SRC_OWNER/SRC_REPO#N](ISSUE_HTML_URL) on YYYY-MM-DD.

[original issue body]
```

Use UTC date for `YYYY-MM-DD`. Write the full body to a temp file (e.g. `mktemp` + heredoc or redirect) so multiline content is preserved.

## Step 4 — Create the issue on the target repo

```bash
gh issue create \
  --repo "${DST_OWNER}/${DST_REPO}" \
  --title "TITLE_FROM_SOURCE" \
  --body-file /path/to/body.md
```

Capture stdout: it contains the new issue URL. Parse the new issue number from the path (`.../issues/<num>`).

## Step 5 — Replay each comment

For each comment in **chronological** order, post one new comment on the **new** issue:

```markdown
**@LOGIN** commented at `CREATED_AT_ISO`

COMMENT_BODY
```

- `LOGIN` from `user.login` (use `unknown` if missing).
- `CREATED_AT_ISO` from `created_at`.
- `COMMENT_BODY` from `body` (empty string if null).

Write each combined block to a temp file and run:

```bash
gh issue comment NEW_ISSUE_NUM \
  --repo "${DST_OWNER}/${DST_REPO}" \
  --body-file /path/to/comment.md
```

## Shell pattern (gh + jq)

Set variables, then:

```bash
ISSUE_JSON=$(gh api "repos/${SRC_OWNER}/${SRC_REPO}/issues/${ISSUE_NUM}")
if echo "$ISSUE_JSON" | jq -e 'has("pull_request")' >/dev/null 2>&1; then
  echo "Ref is a pull request, not an issue." >&2
  exit 1
fi

TITLE=$(echo "$ISSUE_JSON" | jq -r '.title')
UPSTREAM_URL=$(echo "$ISSUE_JSON" | jq -r '.html_url')
RAW_BODY=$(echo "$ISSUE_JSON" | jq -r '.body // ""')
TODAY=$(date -u +%Y-%m-%d)

BODY_FILE=$(mktemp)
{
  printf '> **Copied from** [%s/%s#%s](%s) on %s.\n\n' \
    "$SRC_OWNER" "$SRC_REPO" "$ISSUE_NUM" "$UPSTREAM_URL" "$TODAY"
  printf '%s' "$RAW_BODY"
} >"$BODY_FILE"

OUT=$(gh issue create --repo "${DST_OWNER}/${DST_REPO}" --title "$TITLE" --body-file "$BODY_FILE")
rm -f "$BODY_FILE"
NEW_NUM=$(echo "$OUT" | sed -n 's/.*\/issues\/\([0-9][0-9]*\).*/\1/p')

COMMENTS_JSON=$(gh api "repos/${SRC_OWNER}/${SRC_REPO}/issues/${ISSUE_NUM}/comments" --paginate)
echo "$COMMENTS_JSON" | jq -c 'sort_by(.created_at) | .[]' | while read -r row; do
  login=$(echo "$row" | jq -r '.user.login // "unknown"')
  created=$(echo "$row" | jq -r '.created_at')
  cbody=$(echo "$row" | jq -r '.body // ""')
  CF=$(mktemp)
  printf '**@%s** commented at `%s`\n\n%s' "$login" "$created" "$cbody" >"$CF"
  gh issue comment "$NEW_NUM" --repo "${DST_OWNER}/${DST_REPO}" --body-file "$CF"
  rm -f "$CF"
done

echo "$OUT"
```

On macOS and Linux, `date -u +%Y-%m-%d` works for `TODAY`.

## What this does not copy

Labels, milestones, assignees, projects, reactions, edits, or links to PRs. Label names often do not exist on the fork; recreate manually if needed.

## Limits

GitHub enforces maximum sizes for issue and comment bodies; extremely large threads may need splitting (rare).

## Optional dry run

Before `gh issue create`, show the user the resolved `SRC_*`, `DST_*`, title, body length, and comment count. Use `gh api .../comments --paginate | jq 'length'` for count after sort if needed.
