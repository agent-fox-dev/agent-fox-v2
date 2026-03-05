# Errata: Property 4 (Zero Float Implies Critical Path) for Tied Paths

**Spec:** 20_plan_analysis
**Property:** Property 4 / TS-20-P4

## Issue

The design document states Property 4 as strict equality:
`{n | float(n) == 0} == set(critical_path)`.

This does not hold for graphs with tied critical paths (e.g., diamond
graphs or disconnected components of equal length). In such graphs,
multiple nodes have zero float but the `critical_path` list is one
representative chain.

## Resolution

The property test was updated to:
- When `has_alternative_critical_paths` is False: strict equality holds.
- When `has_alternative_critical_paths` is True: `set(critical_path)` is
  a subset of the zero-float set.
- In all cases: every node on the critical path has float 0.
