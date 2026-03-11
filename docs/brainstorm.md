# Brainstorm — Future Directions

*2026-03-11 — ideas for exploration, not commitments.*

---

## 1. Research: sudocode-ai/sudocode

**What it is:** [github.com/sudocode-ai/sudocode](https://github.com/sudocode-ai/sudocode) — an AI coding tool worth investigating for ideas and competitive positioning.

**What to look for:**
- How do they handle spec-to-code workflows? Compare with our `.specs/` pipeline.
- Task decomposition and dependency management — do they have graph-based planning?
- Isolation strategy — worktrees, branches, or something else?
- Memory and context management — do they accumulate knowledge across sessions?
- Prompt engineering patterns — what archetype-like abstractions do they use?
- Model routing — fixed model or adaptive?

**Assessment:** Low urgency, high value. Understanding the landscape informs our
roadmap. Timebox to 1-2 hours of exploration, capture findings here.

---

## 2. Telemetry

**Why:** Understanding how agent-fox performs in the wild — which archetypes are
most effective, where failures cluster, what model tiers are selected, how
token spend correlates with task complexity.

**Current state:** We track tokens, cost, and outcomes in `state.jsonl` and
DuckDB (`execution_outcomes`, `complexity_assessments`). But this data stays
local. There is no aggregation, no trend analysis, no feedback loop.

**Ideas:**
- **Local telemetry dashboard** — aggregate DuckDB data into periodic reports
  (daily/weekly). Cost trends, success rates, archetype effectiveness, routing
  accuracy. Could power the status page (see below).
- **Opt-in remote telemetry** — anonymous, aggregated metrics sent to a central
  service. Useful for improving routing heuristics and prompt templates across
  the user base. Must be strictly opt-in with clear data policies.
- **OpenTelemetry integration** — structured spans for session lifecycle,
  archetype execution, merge operations. Enables correlation with external
  observability stacks (Grafana, Datadog).
- **Cost anomaly detection** — alert when a session's token usage exceeds
  2-3x the historical mean for its complexity tier.

**Recommendation:** Start with local telemetry (DuckDB queries + CLI command
`agent-fox telemetry`). It's the lowest-risk, highest-signal option. Remote
telemetry is a separate decision with privacy implications — defer until the
local version proves its value.

---

## 3. Status Page

**Why:** A persistent, at-a-glance view of orchestration state — especially
valuable during long multi-spec runs where `agent-fox status` is a one-shot
snapshot.

**Options:**

| Approach | Effort | UX | Notes |
|----------|--------|----|-------|
| **Terminal UI (TUI)** | Low | Good | Rich Live display, auto-refresh. Already have Rich. |
| **Local web dashboard** | Medium | Great | FastAPI/Flask + htmx or React. Query DuckDB directly. |
| **Static HTML export** | Low | OK | Generate HTML report, open in browser. No server needed. |

**What to show:**
- Task graph with status coloring (pending/running/done/failed)
- Live token counter and cost accumulator
- Active session details (archetype, model tier, duration)
- Recent audit log entries
- Memory fact count and growth

**Recommendation:** Start with a TUI using Rich Live — we already depend on
Rich, and it fits the CLI-native workflow. A web dashboard is a natural
evolution once the data model stabilizes (especially after the audit log lands).

---

## 4. Menu Bar App

**Why:** For developers who run agent-fox and context-switch to other work — a
macOS/Linux menu bar presence that shows status without switching terminals.

**Approaches:**
- **rumps** (macOS) — lightweight Python menu bar framework. Could show: run
  status (idle/running/done/failed), task progress (3/12 complete), cost so
  far, click-to-open terminal.
- **Electron/Tauri tray app** — cross-platform but heavier. Overkill unless we
  want a full GUI.
- **Native OS notifications only** — skip the menu bar, just fire notifications
  on key events (see below). Lightest option.

**Data source:** Poll `state.jsonl` or DuckDB on an interval, or have the
engine write to a known socket/pipe.

**Recommendation:** This is a nice-to-have. If we build notifications first
(below), a menu bar app becomes "notifications + persistent status indicator."
Consider after notifications are proven useful. rumps is the right starting
point for macOS.

---

## 5. Notifications (Slack / Discord)

**Why:** Get notified when things happen — run complete, task failed, cost
threshold exceeded, merge conflict needs human intervention.

**Architecture:**

```
Engine events  →  Notification dispatcher  →  Channel adapters
                                               ├── Terminal (bell/toast)
                                               ├── macOS Notification Center
                                               ├── Slack webhook
                                               ├── Discord webhook
                                               └── Email (SMTP)
```

**Event types worth notifying on:**
- Run completed (with summary: tasks done, cost, duration)
- Task failed after max retries
- Merge conflict requiring manual resolution
- Cost threshold exceeded
- Archetype flagged critical issue (skeptic/oracle)

**Configuration:**
```toml
[notifications]
enabled = true
channels = ["terminal", "slack"]

[notifications.slack]
webhook_url = "https://hooks.slack.com/..."
events = ["run_complete", "task_failed", "cost_exceeded"]

[notifications.discord]
webhook_url = "https://discord.com/api/webhooks/..."
events = ["run_complete"]
```

**Recommendation:** High value, moderate effort. Start with terminal
notifications (macOS `osascript` / `notify-send` on Linux) and Slack webhooks —
these cover the primary "walk away and get pinged" use case. The dispatcher
pattern keeps it extensible. Discord and email are trivial additions once the
dispatcher exists.

**Implementation priority within this group:**
1. Terminal/OS notifications (immediate value, zero config)
2. Slack webhooks (team visibility)
3. Discord webhooks (community/personal)
4. Menu bar app (persistent status)
5. Email (least urgent, most infrastructure)

---

## Summary Assessment

| Idea | Value | Effort | Dependencies | Suggested Timing |
|------|-------|--------|-------------|-----------------|
| sudocode research | Medium | Low | None | Anytime (timebox) |
| Local telemetry | High | Medium | Audit log helps | After audit log |
| Status page (TUI) | High | Low | None | Next sprint |
| Status page (web) | High | Medium | Audit log, telemetry | Later |
| Menu bar app | Medium | Medium | Notifications | After notifications |
| Notifications | High | Medium | Config model update | Next sprint |

The highest-leverage items are **notifications** and **status page TUI** — both
directly improve the "run and walk away" workflow that is agent-fox's core
value prop.
