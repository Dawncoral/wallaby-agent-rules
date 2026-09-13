# MEMORY.md — three-tier memory template
# Companion to AGENTS.template.md. Source: Wallaby Token engineering practice.
# https://www.wallabytoken.com/blog/p/agents-md-token-budget
# License: MIT

# Memory

> Read `## Active` at session start. Load Standby items only when the task
> touches them. Dormant is append-only history — never rewrite it.

## Active

<!-- Work in flight RIGHT NOW. Each entry: one line + pointer to details.
     This is the only section your agent reads by default — keep it lean.
     Example:
     - [2026-09-13] Checkout redesign — waiting on asset delivery; spec: docs/specs/checkout.md
-->

## Standby

<!-- Touched in the last 30 days. One-line pointers only — the pointed-to
     file holds the detail. Entries idle 30 days move to Dormant at closeout.
     Example:
     - [2026-08-20] Pricing experiment concluded → decisions.md#2026-08-20
-->

## Dormant

<!-- Append-only. One dated line per entry. Never edit or delete.
     Example:
     - [2026-07-02] Migrated billing to Stripe; old processor retired.
-->
