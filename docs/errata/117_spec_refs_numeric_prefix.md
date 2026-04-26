# Errata: Spec Refs Extract Numeric Prefix Only

**Spec:** 117_adr_ingestion
**Date:** 2026-04-26
**Status:** Active
**Severity:** Spec inconsistency

## Problem

Requirement 117-REQ-6.4 specifies three regex patterns for extracting spec
references, including `(\d{1,3}_[a-z][a-z_]+)` for spec folder names. This
capture group extracts the full folder name (e.g., `03_base_app`).

However, the test specification TS-117-19 asserts that `"03"` (just the
numeric prefix) should be in the extracted refs when the content contains
`03_base_app`.

## Resolution

The implementation should extract only the numeric prefix from spec folder
names to match the test specification. The regex pattern becomes
`(\d{1,3})_[a-z][a-z_]+` (capturing only the digits), or the implementation
post-processes the match to extract just the numeric prefix. This aligns
with the other two patterns which also extract only the spec number.

The test follows the test specification assertion: `"03" in refs`.

## Spec Reference

Addresses major finding on 117-REQ-6.4: "Spec folder name regex is
inconsistent with TS-117-19 assertion."
