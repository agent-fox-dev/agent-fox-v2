# Tasks: fix-issue-320 — Use SDK Notification hooks for activity progress events

## Task Group 1: Implement SDK Notification hook wiring and clean up session.py

- [x] Add `activity_callback`, `node_id`, `archetype` parameters to `AgentBackend.execute()` protocol
- [x] Add `activity_callback`, `node_id`, `archetype` parameters to `ClaudeBackend.execute()`
- [x] Implement `_build_notification_hook()` helper in `claude.py` that converts `NotificationHookInput` to `ActivityEvent`
- [x] Register the Notification hook in `ClaudeAgentOptions.hooks` when `activity_callback` is not None
- [x] Remove `_extract_activity()` function from `session.py`
- [x] Remove activity extraction branching (old lines 242-255) from `_execute_query()` message loop
- [x] Pass `activity_callback`, `node_id`, `archetype` through `_execute_query()` to `backend.execute()`
- [x] Update `MockBackend` in `test_runner.py` to accept and fire activity events
- [x] Add tests for AC-1 through AC-7 in `test_claude.py`
