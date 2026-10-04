<!-- wallaby-agent-rules v4 -->
# Changelog

All notable changes to wallaby-agent-rules. This project versions by marker comment: every user-facing file carries a first-line `<!-- wallaby-agent-rules vX -->`.

## v4 — 2026-10-04

Theme: **Trust is earned before it is assumed.** v3 taught the system to close; v4 makes new memory earn its way in — and makes the system easier to land in your tool.

**Added**

- **Trust-building mode** (default ON for new installs): for the first two weeks, new `MEMORY.md` entries are proposed at session end (⏳ pending, dated, sourced) and become permanent only after your yes. It expires two weeks after install, or the moment you say "trust mode off". L0 enables it by default; L1 gains an 8th question; L3 proposes instead of writing while it is active.
- **Tool integration matrix** in README + per-tool cards in `templates/integrations/`: Claude Code, Codex, Cursor, GitHub Copilot, OpenHands, Gemini CLI — entry file, gotchas, and a 30-second self-check for each.
- `upgrade/v3-to-v4.md` — the one-page upgrade card.
- **GitHub Releases from v4 onward**: every version ships as a Release with migration notes, so watchers get notified. (This is the first one.)

**Changed**

- Version markers move to `<!-- wallaby-agent-rules v4 -->` on the files that changed (README, PROMPT, this changelog, and the new files).

**Unchanged**

- The upgrade rules: add, never overwrite; your content is sacred; nothing changes without your confirmation. `health_check.py` / `reconcile.py` are unchanged since v3.1 and remain the only outright-replaceable files.

## Migrating from v3.1

Nothing breaks and nothing is required. Two options:

1. Paste the **L2 — Upgrade check** prompt; it will offer the optional trust-building section, a pointer to your tool's integration card, and the v4 marker — item by item, your call.
2. Or read the one-page card: `upgrade/v3-to-v4.md`.

## v3.1 — 2026-10-01

Theme: **Memory is not written, it is audited.** v3 kept the system alive day to day; v3.1 catches the days you skipped.

**Added**

- `templates/reconcile.py` — zero-dependency weekly audit, two scans: closure contradictions (LOG.md claims something is done while NOW.md still lists it in flight) and evidence-free closures (a "done" with no path, ticket, or link to verify against). Same zero dependencies, same exit-code contract as `health_check.py`.
- The L0/L1 installs now build `scripts/reconcile.py` alongside the health check; the L2 upgrade check detects v3.1 by its presence.

**Changed**

- Version markers move to `<!-- wallaby-agent-rules v3.1 -->` on the files that changed (README, PROMPT, this changelog).

**Unchanged**

- The upgrade rules: add, never overwrite. Like `health_check.py`, `reconcile.py` is scaffolding — the upgrade may offer to replace it outright.

## Migrating from v3

1. Copy `templates/reconcile.py` into your project as `scripts/reconcile.py`.
2. Run it next to the health check, weekly: `python3 scripts/reconcile.py`.
3. Optionally paste the **L2 — Upgrade check** prompt to refresh the version marker in your entry file.

## v3 — 2026-09-29

Theme: **It remembers because you close.** v2 installed the system; v3 keeps it alive day to day.

**Added**

- `PROMPT.md` — a fourth paste-in prompt: **L3 — Closeout ritual** (four-question triage, drift check, report). The interview becomes the **7-question** interview: the new question installs your own ritual words.
- `## Ritual words` section in the entry-file spec (L0/L1): say "wrap up" and the AI runs the closeout; "note this" logs a conclusion; "that's wrong" records a failure. Defaults included — the point is to use *your* words.
- `templates/health_check.py` — four new scans: NOW.md entries idle past 30 days; INDEX.md registrations pointing at missing files; entry files past the size wall — bytes, lines, or estimated tokens, whichever bursts first (CJK text fills byte budgets ~3x faster, so the script counts all three); MEMORY.md bullets with no date. Same zero dependencies, same exit codes.
- `examples/NOW.example.md`, `examples/INDEX.example.md` — what "good" looks like two weeks in, not just on day one.

**Changed**

- Version markers move to `<!-- wallaby-agent-rules v3 -->`.
- README roadmap updated: the closeout ritual and the deeper health check shipped here; deeper governance (architecture review, managed oversight) is planned as a hosted offering rather than an open drop.

**Unchanged**

- The upgrade rules: add, never overwrite; your content is sacred; you approve item by item.

## Migrating from v2

The v1→v2 rules still apply — add, never overwrite; your content is sacred; you confirm before anything moves — with one explicit exception: **`health_check.py` is scaffolding.** It contains none of your content, so the upgrade offers to replace it outright.

1. Paste the **L2 — Upgrade check** prompt from `PROMPT.md`; approve item by item.
2. Replace `scripts/health_check.py` with the v3 version (seven scans).
3. Add the `## Ritual words` section to your entry file — the defaults, or your own words.
4. Try the closeout once via **L3**; then hang it on your word.

## v2 — 2026-09-21

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
