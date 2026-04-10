# Erratum 93: TS-93-4 Placement Contradiction

**Spec:** 93 (fix_branch_push)
**Identified by:** Skeptic review (severity: major)

## Issue

`test_spec.md` classifies TS-93-4 as type `integration`, but `tasks.md`
task 1.1 instructs implementing "TS-93-1 through TS-93-9" in the unit test
file `tests/unit/nightshift/test_fix_branch_push.py`.

The `tasks.md` traceability table maps 93-REQ-3.1 (the requirement TS-93-4
validates) to `test_fix_branch_push_smoke.py::test_push_before_harvest`, which
is an integration smoke test.

## Resolution

TS-93-4 is placed in the integration smoke test file:
`tests/integration/nightshift/test_fix_branch_push_smoke.py`

This respects the type annotation in `test_spec.md` (integration) and aligns
with the traceability table in `tasks.md`. The unit test file covers TS-93-1
through TS-93-3 and TS-93-5 through TS-93-9 (excluding TS-93-4).

The SMOKE-1 test also validates the same ordering requirement (93-REQ-3.1),
so coverage is maintained even with a single test covering this property.
