"""Workspace operations: re-exports from focused submodules.

This module re-exports all public symbols from:
- agent_fox.workspace.git (low-level Git wrappers)
- agent_fox.workspace.develop (develop branch management)
- agent_fox.workspace.worktree (worktree lifecycle)

Existing imports from ``agent_fox.workspace.workspace`` continue to work.
"""

from agent_fox.workspace.develop import (  # noqa: F401
    _sync_develop_under_lock,
    _sync_develop_with_remote,
    ensure_develop,
)
from agent_fox.workspace.git import (  # noqa: F401
    abort_rebase,
    checkout_branch,
    create_branch,
    delete_branch,
    detect_default_branch,
    get_changed_files,
    get_remote_url,
    has_new_commits,
    local_branch_exists,
    merge_commit,
    merge_fast_forward,
    push_to_remote,
    rebase_onto,
    remote_branch_exists,
    run_git,
)
from agent_fox.workspace.worktree import (  # noqa: F401
    WorkspaceInfo,
    create_worktree,
    destroy_worktree,
)
