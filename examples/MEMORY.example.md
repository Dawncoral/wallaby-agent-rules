# MEMORY.md — filled example (fictional but realistic)

> This is what the three tiers look like in actual use, about eight weeks
> after adopting the template. Yours will be messier. That is fine — the
> tier boundaries matter more than tidy lines.

# Memory

> Read `## Active` at session start. Load Standby items only when the task
> touches them. Dormant is append-only history — never rewrite it.

## Active

- [2026-09-13] Checkout redesign — waiting on asset delivery; spec: docs/specs/checkout.md
- [2026-09-12] Rate-limit tuning — probe collecting data until 09-15; script: ops/latency_probe.py

## Standby

- [2026-09-05] Blog build pipeline changed to static gen → ops/README.md#blog
- [2026-08-28] Pricing experiment concluded, kept 5% margin → decisions.md#2026-08-28
- [2026-08-20] Switched DNS to Cloudflare; registrar login in password manager

## Dormant

- [2026-07-02] Migrated billing to Stripe; old processor retired.
- [2026-06-18] First paying customer; manual invoicing replaced by dashboard.
- [2026-05-30] Project bootstrapped; chose plain-file memory over vector store (see decisions.md#2026-05-30).

<!--
What to notice:

1. Active is two lines. If yours is fifteen, you are paying for fifteen
   lines in every session. Move finished or idle items down.
2. Every Active/Standby line is a POINTER. The detail lives in the file it
   names; the agent fetches it only when the task touches that area.
3. The [date] prefix is what makes the 30-day downgrade rule executable —
   without dates, "idle for 30 days" is unfalsifiable and nothing ever moves.
4. Dormant entries are one line and final. If a fact changes, you append a
   new line; you do not edit history. Git blame will thank you.
-->
