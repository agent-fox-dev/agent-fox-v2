# Tasks: Fix Issue #313 — Exception during command "night-shift"

## Task Group 1: Add timeout and retry to GitHubPlatform HTTP calls

- [x] Add explicit `httpx.Timeout` (connect >= 15s) to every `httpx.AsyncClient()` call in `github.py`
- [x] Add `_request()` helper method on `GitHubPlatform` that wraps HTTP calls with retry-with-backoff for transient errors (`ConnectTimeout`, `ConnectError`, `ReadTimeout`)
- [x] Retry up to `_MAX_RETRIES` times with exponential backoff; after exhaustion, re-raise the original exception
- [x] Ensure only transport-level exceptions trigger retries; HTTP-level errors (4xx, 5xx responses) are not retried
- [x] Update all 11 HTTP call sites in `GitHubPlatform` methods to use `_request()`
- [x] Write unit tests covering: retry succeeds on second attempt (AC-2), retries exhausted raises (AC-3), timeout configured (AC-1), 401 not retried (AC-5)
