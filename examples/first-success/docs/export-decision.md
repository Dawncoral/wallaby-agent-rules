# Export format decision (fictional)

> Part of the fictional `first-success` example. The details are invented.

## Decision

Decision: CSV (RFC 4180), not XLSX.

## Why

- The downstream importer reads CSV only; XLSX would add a parser dependency.
- Every spreadsheet tool the customers use can open CSV.
- One header row and UTF-8 with a BOM keeps non-ASCII customer names readable.

## What changes

The export endpoint writes `text/csv; charset=utf-8`. The settings screen keeps
its file-name field, and the customer note links to this decision instead of
repeating the reasoning.
