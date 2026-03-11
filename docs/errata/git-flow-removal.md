# Errata: git-flow.md removed

**Date:** 2026-03-11
**Issue:** [#157](https://github.com/agent-fox-dev/agent-fox-v2/issues/157)

## Summary

`agent_fox/_templates/prompts/git-flow.md` was dead code — no archetype
included it in its templates list, and the `inclusion: always` frontmatter
was stripped before any code could read it.

`coding.md` already contained a GIT WORKFLOW section covering the same
content. The one useful piece (`Merge .gitignore updates manually; never
overwrite unrelated ignore rules`) was merged into `coding.md`.

## Affected specs

The following specs reference `git-flow.md` in their documentation. These
references are now historical:

- `.specs/15_session_prompt/` — design.md, test_spec.md, requirements.md, prd.md
- `.specs/19_git_and_platform_overhaul/` — design.md, test_spec.md, tasks.md, prd.md, requirements.md
- `.specs/26_agent_archetypes/` — design.md, test_spec.md

## Affected tests

`tests/unit/prompts/test_template_content.py::TestGitFlowTemplate` (TS-19-8)
was removed — the file it tested no longer exists.
