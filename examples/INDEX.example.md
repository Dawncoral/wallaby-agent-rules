# INDEX.md — filled example (fictional but realistic)

> Same fictional project as examples/MEMORY.example.md and
> examples/NOW.example.md. One flat table still works at this size;
> past ~50 files, split into one section per top-level directory.

| File | What it is |
|---|---|
| `README.md` | Project overview and setup |
| `AGENTS.md` | Standing instructions for the AI — entry point |
| `MEMORY.md` | Long-term memory: permanent facts and iron rules |
| `NOW.md` | Current state: work in flight and recently touched |
| `LOG.md` | Dated append-only log of decisions and events |
| `docs/specs/checkout.md` | Checkout redesign spec (in flight) |
| `ops/README.md` | Ops runbook; `#blog` covers the static-gen pipeline |
| `ops/latency_probe.py` | Nightly rate-limit probe; writes to `ops/data/` |
| `scripts/health_check.py` | Weekly tidy-up check — seven scans, zero dependencies |

<!--
What to notice:

1. One line per file, in plain words. If a line needs two clauses, the
   file is probably doing two jobs.
2. It covers the files you actually look for — not every file that
   exists. Generated directories (node_modules, dist) stay out by
   convention.
3. An index drifts the moment you stop registering files on creation.
   The health check flags both directions: files registered nowhere,
   and registrations pointing at files that no longer exist.
-->
