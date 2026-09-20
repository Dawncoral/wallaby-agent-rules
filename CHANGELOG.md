<!-- wallaby-agent-rules v2 -->
# Changelog

All notable changes to wallaby-agent-rules. This project versions by marker comment: every user-facing file carries a first-line `<!-- wallaby-agent-rules vX -->`.

## v2 — 2026-09-20

Theme: **AI remembers, you find.** The repo grows from a template pack into a two-prompt onboarding system.

**Added**

- `PROMPT.md` — three paste-in prompts: L0 one-click install (all defaults), L1 6-question interview (tuned build), L2 upgrade check (incremental migration).
- `templates/NOW.md`, `templates/INDEX.md`, `templates/LOG.md` — plain-named templates for current state, the project map, and the dated log.
- `templates/health_check.py` — zero-dependency weekly check: stray root files, generated artifacts (.zip/.tmp/.pyc/.log) inside the project, .md files missing from INDEX.md. Exit 0 clean / 1 findings.
- `CHANGELOG.md` — this file.
- Version markers: every user-facing Markdown file now opens with `<!-- wallaby-agent-rules v2 -->`.

**Changed**

- `README.md` rewritten around the two-prompt onboarding flow: pain contrast, two paths, what you get, updating, roadmap.
- `COLD_START.md` superseded by `PROMPT.md`; kept as a short pointer so existing links do not break.

**Unchanged**

- `AGENTS.md` and `MEMORY.md` v1 starter templates (token-budget discipline, three-tier memory, stakeholder register) remain valid; `examples/` untouched.

## Migrating from v1

Three principles: **add, never overwrite** — new files are simply created, existing-file changes are only proposed as diffs. **Your content is sacred** — every line you wrote stays untouched. **You confirm before anything moves** — the AI produces a checklist, you approve item by item.

Three steps:

1. Copy the new pieces into your project — `templates/NOW.md`, `templates/INDEX.md`, `templates/LOG.md`, `templates/health_check.py` (as `scripts/health_check.py`). Zero changes to your existing files required.
2. For the new usage flow (one-click install, interview, upgrade check), read [README.md](README.md) and [PROMPT.md](PROMPT.md).
3. If you bootstrapped with `COLD_START.md`, switch to the L0 section of [PROMPT.md](PROMPT.md) for new projects — and run its **L2 — Upgrade check** prompt in your existing project to get a personalized migration checklist.

## v1 — 2026-09-17

Initial public release (7 commits):

- `AGENTS.md` token-budget starter template: positive rules plus a forbidden list (no tests for presentational UI, no browser-automation acceptance testing, no out-of-scope refactoring, no unrequested features, no prose in instruction files).
- `MEMORY.md` three-tier memory convention (Active / Standby / Dormant) with the 30-day downgrade rule and the example file `examples/MEMORY.example.md`.
- Delta-audit discipline: audit by baseline, close items on live evidence, not records.
- Stakeholder register: PMP-inspired perspective rules for people-facing output.
- `COLD_START.md`: paste-in bootstrap prompt — recon, build the governance files, adopt standing rules, pick a reconciliation mode (cron / weekly self-check / trigger words), report with a to-confirm list.
- MIT license.
