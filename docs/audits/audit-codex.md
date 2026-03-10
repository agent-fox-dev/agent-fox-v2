# Codebase Audit: agent-fox-v2 (Codex)

**Date:** 2026-03-10  
**Assessment Branch:** `develop`  
**Scope:** Spec intent vs implementation, wiring holes, code smells, test coverage gaps

---

## Method Used

- Read repository docs and project memory (`README.md`, `docs/adr/*`, `docs/memory.md`, `docs/errata/*`).
- Read specs in numeric order under `.specs/*`, including `fix_*` specs and precedence notes.
- Read code deeply across `agent_fox/*` (CLI, session/backend, engine, workspace, tools, spec validator, reporting, security).
- Inspected tests for requirement coverage and quality gaps.
- No code changes were made in this assessment.

---

## Spec Precedence / Intent Notes

1. `.specs/19_git_and_platform_overhaul` explicitly supersedes `.specs/10_platform_integration`.
2. `docs/errata/28_github_issue_rest_api.md` supersedes spec-26 `gh`-CLI issue requirements with REST API behavior.
3. `docs/errata/unwired_cli_commands.md` states `ask`, `patterns`, `compact` remain intentionally unwired and `ingest` is lifecycle-based.
4. Some active specs still mention those removed commands (notably spec 23), so spec-vs-errata authority is currently split.

---

## Findings (Ordered by Severity)

### P0 - Custom tool registration is only partially implemented (spec 29 mismatch risk)

**Intent:** `29-REQ-6.2`, `29-REQ-6.3`, `29-REQ-8.2` require backend availability + invocation of custom tools.  
**Evidence:**
- Protocol and runner pass tools correctly:
  - `agent_fox/session/backends/protocol.py` (`execute(..., tools=...)`)
  - `agent_fox/session/session.py` (builds fox definitions and passes `tools=fox_tools`)
- Claude backend accepts `tools` parameter but never uses it:
  - `agent_fox/session/backends/claude.py` (`tools` appears in signature only; not wired into SDK options/tool handling)

**Impact:** With `tools.fox_tools = true`, config path exists, but real backend behavior may not expose/invoke tools as required.

**Test gap:** Current tests mostly prove signatures and registry objects, not real backend registration/invocation path.

---

### P1 - JSON error envelope bug for Click exceptions

**Intent:** `23-REQ-6.1` expects meaningful error envelope content.  
**Evidence:** In `agent_fox/cli/app.py`, `BannerGroup.invoke()` catches `click.ClickException` and emits:

- `emit_error(str(ctx.invoked_subcommand or "unknown"))`

This emits subcommand name (e.g., `"lint-spec"`) instead of the actual exception message.

**Impact:** JSON clients receive incorrect error content for Click-level failures.

**Test gap:** `tests/unit/cli/test_app.py` checks Click exception behavior in non-JSON mode; no assertion for JSON envelope message correctness on this path.

---

### P1 - Spec governance drift for unwired CLI commands

**Intent conflict:**  
- Spec 23 still requires JSON behavior for `ask`, `patterns`, `compact`, `ingest` (`23-REQ-3.5`, `23-REQ-3.6`, `23-REQ-3.7`, `23-REQ-5.2`).  
- CLI intentionally does not register those commands now (`agent_fox/cli/app.py`), per `docs/errata/unwired_cli_commands.md`.

**Impact:** Either implementation diverges from active specs, or errata is effectively overriding specs without a numbered successor spec.

**Test gap:** Coverage for removed commands is naturally absent from runtime tests, while spec text still asserts behavior.

---

### P2 - Permission gating semantics for custom tools are under-specified and weak

**Intent:** `29-REQ-6.4` says existing permission callback should gate custom tools as built-ins.  
**Evidence:** `agent_fox/hooks/security.py` allows all non-`Bash` tools by default:
- `if tool_name != "Bash": return {"decision": "allow"}`

**Impact:** Custom tools can bypass meaningful policy checks unless additional policy is added elsewhere.

**Note:** This may be technically compatible with current “same mechanism” wording, but practically weak for security posture.

---

### P2 - `lint-spec --fix` has high side effects (branch creation + commit)

**Evidence:** `agent_fox/cli/lint_spec.py` (`_create_fix_branch`, `_commit_fixes`, auto-checkout + commit in command flow).

**Impact:** A lint/fix command mutates git state and creates commits automatically; this is surprising behavior and risky in automation contexts.

**Spec fit:** May be intentional, but should be explicitly affirmed as product policy.

---

### P2 - `spec/validator.py` is a maintainability hotspot

**Evidence:**
- Very large file (`~2439` lines) with mixed responsibilities.
- Mid-file imports and redefinitions (Ruff `E402`, `F811`) around AI-validation section.

**Impact:** Hard to reason about, fragile edits, higher regression risk.

---

### P3 - Test quality gaps in backend coverage

**Evidence:** `tests/unit/session/backends/test_claude.py` contains placeholder-style tests that assert existence/importability rather than behavior (“will be implemented…” comments).

**Impact:** Critical behavior (stream mapping, options, custom tools, handler exceptions) is under-verified in backend-specific tests.

---

## Coverage Gaps vs Spec Intent

1. **Spec 29 backend tool lifecycle**
   - Missing end-to-end test where `tools.fox_tools=true` causes actual tool registration and invocation through `ClaudeBackend`.
2. **Spec 23 JSON error semantics**
   - Missing JSON-mode ClickException test asserting actual exception message in envelope.
3. **Spec/errata reconciliation**
   - No single authoritative, machine-checkable source saying spec-23 command requirements are superseded/deferred.
4. **Security behavior for custom tools**
   - No tests proving explicit allow/deny policy for custom tool names beyond Bash allowlist behavior.
5. **Backend tests**
   - Existing tests for `ClaudeBackend` are structural, not behavioral.

---

## Get-Well Plan (No Code Changes Yet)

### Phase 1 - Governance and Contract Alignment (first)

1. Decide and codify authority for command removals (`ask`, `patterns`, `compact`, `ingest` behavior).
2. Add a numbered superseding spec or explicit “deferred” spec amendment for spec 23 command requirements.
3. Add a small “spec precedence matrix” doc so CI and contributors interpret requirements consistently.

**Exit criteria:** No ambiguous requirement ownership between `.specs/*` and `docs/errata/*`.

---

### Phase 2 - Functional Correctness Fixes

1. Implement real custom-tool registration/invocation path in `ClaudeBackend` for `tools`.
2. Ensure custom tool handler exceptions return tool error results and session continues (`29-REQ-6.E2`).
3. Fix JSON ClickException envelope in `BannerGroup.invoke()` to emit actual exception text.

**Exit criteria:** Behavior matches `29-REQ-6.*`, `29-REQ-8.2`, and `23-REQ-6.1` with explicit tests.

---

### Phase 3 - Security and Policy Hardening

1. Make policy for custom tools explicit:
   - Either intentionally allow all non-Bash tools and document it,
   - Or add allow/deny controls for custom tool names.
2. Add tests for permission_callback decisions on custom tools.

**Exit criteria:** Security behavior is deliberate, documented, and test-locked.

---

### Phase 4 - Test and Quality Debt Reduction

1. Replace placeholder `ClaudeBackend` tests with behavior-driven tests (mock SDK stream, tool invocation path, exception path).
2. Add integration test for config flag -> backend receives and uses custom tools.
3. Add JSON-mode ClickException test (error envelope content).
4. Break down `spec/validator.py` into focused modules (static lint, AI validation, dependency checks).
5. Resolve current lint debt in touched files and establish clean quality-gate baseline.

**Exit criteria:** Critical paths are behavior-tested; maintainability hotspots reduced.

---

## “Crazy Ideas” for Differentiation

1. **Capability Graph Runtime**
   - Replace hardcoded backend/tool wiring with a runtime capability graph (backend advertises tool protocol support; tools are mounted declaratively).  
   - Big simplification and future-proofing for multiple backends.

2. **Spec-as-Executable Contracts**
   - Generate coverage contracts directly from spec requirement IDs and fail CI when a requirement has no mapped behavioral test.
   - Eliminates silent spec drift and placeholder-test debt.

3. **Adaptive Context Engine (User-facing leap)**
   - Use knowledge DB + fox tools to build minimal, intent-aware context bundles per task automatically.
   - Could materially reduce token spend and improve task success consistency from user perspective.

---

## Worktree Plan for Implementation (When Approved)

Per your instruction, implementation should happen in a worktree forked from `develop` (assessment remains on `develop`).  
Suggested start command for execution phase:

```bash
git worktree add ../agent-fox-v2-audit-fix -b codex/get-well-phase1 develop
```

