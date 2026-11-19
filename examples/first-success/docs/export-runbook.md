# Field runbook: CSV export (fictional)

> Part of the fictional `first-success` example. The details are invented.

## Steps

1. Open the export settings screen and choose a date range.
2. The screen calls the export endpoint; the endpoint writes UTF-8 CSV with one
   header row, as decided in `docs/export-decision.md`.
3. Download the file and open it once before sending it to a customer.

## When it fails

- An empty file means the date range matched no rows. That is not an error.
- A permission error means the API token lacks the export scope. Rotate the
  token in the operations console; never paste a token into a ticket.
