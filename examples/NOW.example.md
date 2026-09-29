# NOW.md — filled example (fictional but realistic)

> Two weeks after install, same project as examples/MEMORY.example.md.
> Notice how short this is. Short is the point.

## In flight

- [2026-09-28] Rate-limit tuning — probe shows p99 down; decide 10-02 whether to keep; data: ops/latency_probe.py
- [2026-09-27] Checkout redesign — assets arrived; wiring the payment step; spec: docs/specs/checkout.md

## Recently touched

- [2026-09-19] Blog pipeline moved to static gen → ops/README.md#blog
- [2026-09-12] Pricing experiment concluded, kept 5% margin → LOG.md
- [2026-09-05] Switched DNS to Cloudflare; registrar login in the password manager

<!--
What to notice:

1. Two lines in flight. If yours has fifteen, fifteen lines load into
   every session. Finished things leave; idle things move down.
2. Every line is dated. The date is what makes "30 days idle" executable —
   and it is exactly what the health check's staleness scan reads.
3. Each line ends with a pointer. NOW.md is a signpost, not a story.
-->
