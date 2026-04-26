# Errata: ADREntry Section-Presence Fields

**Spec:** 117_adr_ingestion
**Date:** 2026-04-26
**Status:** Active
**Severity:** Design divergence

## Problem

The design document specifies `ADREntry` with no fields to track which
MADR sections were found during parsing. However, requirement 117-REQ-3.1
requires `validate_madr(entry: ADREntry)` to check for the presence of
mandatory sections (Context, Considered Options, Decision Outcome).

Since `validate_madr` only receives an `ADREntry`, it has no way to verify
section presence without additional metadata. The context section in
particular has no corresponding extracted data field (unlike `chosen_option`
for Decision Outcome or `considered_options` for Considered Options).

## Resolution

Three boolean fields are added to `ADREntry`:

- `has_context_section: bool = False`
- `has_options_section: bool = False`
- `has_decision_section: bool = False`

These are set by `parse_madr()` when the respective headings are found,
and consumed by `validate_madr()` to check section presence. They are
transient metadata that do not persist to the DuckDB `adr_entries` table.

## Impact

- `ADREntry` dataclass gains three optional boolean fields (backward
  compatible via defaults).
- No database schema change required.
- Tests construct `ADREntry` with these flags set explicitly.

## Spec Reference

Addresses critical finding on 117-REQ-3.1: "validate_madr(entry: ADREntry)
cannot check for context section presence."
