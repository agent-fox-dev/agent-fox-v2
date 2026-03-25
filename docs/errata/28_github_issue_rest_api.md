# Errata: GitHub Issue REST API (Spec 28)

## Divergence from Spec 26 (Agent Archetypes)

Spec 26 requirements 26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3, and 26-REQ-10.E1
originally specified GitHub issue operations (search, update, create) via the
`gh` CLI tool.

Spec 28 replaced the `gh` CLI implementation with direct GitHub REST API calls
through the `GitHubPlatform` class (`agent_fox/platform/github.py`). The
behavioral contracts remain identical — search before create, update existing,
create new, graceful degradation on failure — but the transport layer changed
from subprocess invocations of `gh` to HTTP requests using the REST API with
`GITHUB_PAT` authentication.

### Affected Requirements

| Requirement | Original (Spec 26) | Current (Spec 28) |
|-------------|--------------------|--------------------|
| 26-REQ-10.1 | Search via `gh issue list` | Search via REST API `GET /repos/{owner}/{repo}/issues` |
| 26-REQ-10.2 | Update via `gh issue edit` + `gh issue comment` | Update via REST API `PATCH` + `POST` |
| 26-REQ-10.3 | Create via `gh issue create` | Create via REST API `POST /repos/{owner}/{repo}/issues` |
| 26-REQ-10.E1 | `gh` CLI unavailable | REST API call failure or missing `GITHUB_PAT` |
