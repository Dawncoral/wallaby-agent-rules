<!-- wallaby-agent-rules 1.4.3 -->
# Changelog

All notable changes to wallaby-agent-rules. This project versions by marker comment: every user-facing file carries a first-line `<!-- wallaby-agent-rules vX -->`.

## 1.4.3 — 2026-11-09

**The registries, the change check, and the memory files now work as one loop.** The release checklist counts new commands as a minor version; this one keeps a patch number by maintainer decision.

- **Governance CLI 1.4.3** in `extras/memory-governance/` adds five commands. None needs a dependency or a model, and each skips the checks for files your project does not have.
  - `route "<change>" --paths …` prints one card of about 2 KB: capabilities to reuse, files to register first, the MAP.md components and areas the change touches, event types and surfaces, a light or heavy tier with reasons, and the premises to review. A premise with `depends_on` appears only when a changed path matches it; a premise without one appears every time.
  - `lookup` returns rows of CAPABILITIES.md or MAP.md.
  - `audit` reports unregistered scripts, skills, and workflows; entries and map paths that lead to missing files; active capabilities that nothing mentions; pointer stubs that hold extra text; and edited month volumes. `doctor` runs it.
  - `map sync` keeps a generated block in MAP.md, one row per top-level directory, and prints paste-ready rows to add or retire. Rows you wrote stay as they are. `--check` exits 1 on drift, and `doctor` runs the check.
  - `split volume` moves finished months of LOG.md into `LOG/YYYY-MM.md` automatically. `split topic` nominates MEMORY.md sections or INDEX.md parts once a file passes its budget and applies a nomination only with `--confirm`. Every split checks that the merged text matches the original byte for byte. It keeps a manifest, a backup, and a receipt, and it can be rolled back.
- `impact` also lists the MAP.md components and capabilities the scan touched and records both in the receipt.
- Receipt IDs now increase: `R-000001`, then `R-000002`, and so on. Versions 1.4.0 to 1.4.2 gave every receipt `R-000001`. The upgrade leaves existing receipts as they are.
- **`audit` measures the instructions your agents load.** It finds them with no setup. The always-loaded ones are root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, and `.github/copilot-instructions.md`; it reports their rule count and size. The on-demand ones are nested entry files, skills under `.claude/skills`, `.agents/skills`, `skills`, and `.github/skills`, and the `.cursor/rules`, `.claude/rules`, and `.github/instructions` folders; it reports how many there are and their size. A symlink or a second path to the same file counts once. The first run records the always-loaded part as a baseline, with nothing to edit. Above the baseline, `audit` and `doctor` suggest one rule in, one rule out. A rule that appears almost word for word in more than one file gets a paste-ready fix: keep it in one place and point to it from the others. All of this is report only and silent when there is nothing to report; `init` adds one line to its report. `audit --rules` gives the agent JSON for the weekly review. The agent judges which rules mean the same thing and which a tool could enforce, and asks once before installing a guardrail; `--rules-answer` records that answer. The closeout in PROMPT.md, PROMPT.zh-CN.md, AGENTS.md, and the skill adds the one-in, one-out step; the weekly guide adds the review and a table of common guardrails.
- **Memory MCP server 0.3.0**, new in this release under `extras/memory-mcp/`: one zero-dependency stdio server that opens the memory files to agents that do not load the entry file. Nine tools cover the session-start read, INDEX lookup, proposals, log notes, in-flight updates, the weekly checks, version status, capability lookup, and change routing. The last two, `memory_lookup` and `memory_route`, are read-only and call the governance CLI. `memory_locate` also reads the INDEX parts that INDEX.md points to. `memory_propose` queues facts in `PROPOSALS.md` and never writes `MEMORY.md`. Every write is redacted first. `--tools` limits what a client sees, and `--origin` tags each proposal with the task that made it.
- **health_check.py and reconcile.py 1.4.3**: health_check.py counts month volumes as registered through their volume list and reads INDEX parts as part of INDEX.md. reconcile.py reads the volumes. Both skip `.memory/`.
- **Entry-file rules**: two optional lines — search CAPABILITIES.md before you build, and run `route` or `impact` after you change a component listed in MAP.md. Added to PROMPT.md L0 and L1, PROMPT.zh-CN.md, AGENTS.md, and the installable skill, now skill version 1.2.0. The L2 upgrade check recognizes 1.4.3.
- MEMORY.md, NOW.md, INDEX.md, and LOG.md keep their 1.0.1 format.

### Migrating from 1.4.2

Nothing is required. To use the new commands:

1. Preview the CLI upgrade with `python3 scripts/memory_governance.py upgrade --source /path/to/wallaby-agent-rules/extras/memory-governance/memory_governance.py`, then add `--apply`.
2. Replace `scripts/health_check.py` and `scripts/reconcile.py` with the 1.4.3 templates before your first split, so the weekly checks read volumes and INDEX parts.
3. Run `python3 scripts/memory_governance.py doctor`. If MAP.md or CAPABILITIES.md exists, the new audit may report problems that already existed; `map sync` prints rows to paste. The first `audit` or `doctor` also records the instruction baseline, silently.

To try the MCP server, add it to your MCP client as shown in `extras/memory-mcp/README.md`, then run `python3 extras/memory-mcp/smoke_test.py` (32 checks on a temporary project). The governance tests run with `python3 -m unittest discover -s extras/memory-governance/tests` (71 tests).

## 1.4.2 — 2026-10-30

**Lossless governance CLI upgrades.** New `upgrade` command: a default dry run shows current and available versions, refuses downgrades, and changes nothing. With `--apply`, it replaces only the CLI after making a backup, verifies that the new CLI starts, and restores the original if validation fails. Memory files, `.memory/` configs, receipts, and all other project files stay untouched.

### Migrating from 1.4.1

Run `python3 scripts/memory_governance.py upgrade --source /path/to/newer/memory_governance.py` to preview. Add `--apply` only after reviewing the preview. No data migration is needed.

## 1.4.1 — 2026-10-30

**Documentation: weekly reconciliation, from principles to a working routine.** New `extras/memory-governance/WEEKLY_RECONCILE.md` covers scope selection, deterministic checks, a small semantic sample, premise and contradiction review, finding ownership, a report template, and a worked rename example. No installed files change, and there is no separate Release or announcement for this patch.

### Migrating from 1.4.0

Nothing is required. Read the guide when you want to introduce a weekly review or evaluate the health of an existing memory process.

## 1.4.0 — 2026-10-30

**Memory governance becomes executable.** A new optional pack connects change conduction, premise checks, contradiction history, and verification receipts; the existing install remains valid.

- **New: `extras/memory-governance/`** — one zero-dependency CLI with nine conduction event types, three premise levels, append-only contradiction history, and impact receipts that cannot verify while old references or unread files remain. `init` never overwrites user files; `doctor` runs the complete check.
- **New: `templates/MAP.md`** — map system components, change keywords, and authoritative detail files.
- **New: `templates/CAPABILITIES.md`** — register reusable scripts, skills, templates, and jobs before building another implementation.
- **New: `templates/FAILURES.md` and `examples/FAILURES.example.md`** — a failure-to-regression format plus ten sanitized composite examples. No private project or customer incidents are included.
- **Closeout update**: when tracked work closes, LOG.md and NOW.md must be written in the same action. Pending entries use an anchor and current status, not a deferral placeholder. Updated in AGENTS.md, PROMPT.md, PROMPT.zh-CN.md, and the installable skill (now skill version 1.1.0).
- **New: `upgrade/1.3-to-1.4.md`** — the optional additions, governance installation, and closeout wording on one page. The L2 upgrade check recognizes 1.4.0.

### Migrating from 1.3.0

Nothing is required. The core file layout is unchanged. Adopt the templates or governance pack independently, then add the closeout wording if you want it. Health check 1.4.0 only adds the three new filenames to its root whitelist; reconcile.py is unchanged. See `upgrade/1.3-to-1.4.md`.

## 1.3.0 — 2026-10-14

**Skill lifecycle governance joins the repo.** One new standalone toolkit under `extras/`; nothing changes inside your project.

- **New: `extras/skill-forge/`** — Skill Forge runs the part of a skill's life that starts after creation: requirement derivation with a high-stakes checklist, generation to a measured spec, a failure ledger the skill itself writes to, and an optimize loop driven by that evidence. Three forms, one protocol: an MCP server (`mcp/`, zero dependencies, stdio, 78-assertion smoke suite), a paste-ready prompt pack (`prompt-pack/`), and a SKILL.md-compatible skill (`skill-form/`) generated from the same source. Versions independently, starting at 1.0.0. Every behavioral claim was measured on real models; the write-ups are linked from its README.
- README (EN + zh-CN): a Skill Forge note in the "New in" line and a row in "Also in this repo".
- PROMPT (EN + zh-CN): the L2 upgrade check now recognizes 1.3.0; installed files are unchanged from 1.1.0.

### Migrating from 1.2.0

Nothing to migrate. 1.3.0 adds a standalone toolkit; the files installed in your project are identical to 1.1.0, and an install that fingerprints as 1.1.0 is current.

## 1.2.0 — 2026-10-06

**The memory system, now as an installable skill.** One new distribution surface and one new tool card; nothing changes inside your project.

- **New: `skills/agent-memory-rules/`** — the whole system packaged as a SKILL.md: what gets built (entry file, MEMORY.md, NOW.md, INDEX.md, LOG.md), the standing rules, the closeout ritual, and both check scripts bundled under `scripts/`. Install into Hermes Agent with `hermes skills install Dawncoral/wallaby-agent-rules/skills/agent-memory-rules`; the same directory works with any tool that reads the SKILL.md convention. The skill versions independently, starting at 1.0.0. Passes the Hermes community security scan at the cleanest verdict (safe — no findings beyond informational notes).
- **New: `templates/integrations/hermes.md`** — entry file, three gotchas verified on Hermes v0.21.5 (only the entry file is auto-injected — MEMORY.md is pulled in by the protocol rule; context files pass a prompt-injection scan; oversized files truncate head/tail against a cap that scales with the model's context window, 20K chars floor), and the 30-second self-check.
- README (EN + zh-CN): Hermes row in the tool table, a third get-started path, and the `skills/` listing.

### Migrating from 1.1.0

Nothing to migrate. 1.2.0 adds distribution surfaces; the files installed in your project are identical to 1.1.0, and an install that fingerprints as 1.1.0 is current.

## 1.1.0 — 2026-10-06

**Hygiene layer, hardened by our own failure log.** Three additions to `health_check.py` (now ten scans), one protocol rule change, and one design boundary made explicit. Every addition maps to a failure mode we logged running this system on our own business — 45 dated cases as of today.

**Added**

- **MEMORY.md aging** (protocol + scan 8): a threshold-triggered rule replaces "nothing ages out". Past the soft wall (~150 dated lines or ~8k estimated tokens, CJK-weighted), facts idle 30+ days move to `LOG.md` at the next closeout; below the wall, nothing happens and nothing nags. The health check lists the demote candidates. Calibrated to the ranges we run internally.
- **Secrets hygiene** (scan 9): credential files (`.env`, `.credentials/`) tracked by git, and common key patterns (`sk-…`, `AKIA…`, private-key blocks, `ghp_…`, `xox…-…`) in text files, are flagged. Placeholders and examples are whitelisted; `.credentials/` may exist, it just may not be committed. It is a reminder, not a safety net — the real defense is the habit.
- **Commit-silence detection** (scan 10): when the last git commit is newer than the newest dated entry in `NOW.md`/`LOG.md`, work happened with no record — flagged. Skipped without `.git` (fail-open).
- **`extras/pre-commit.sample`**: an optional 23-line hook for those who want enforcement. It stays a sample on purpose: detection plus the closeout rhythm is the system; a blocking hook gets bypassed (`--no-verify`) the first time it annoys.

**Changed**

- `MEMORY.md` pointer discipline: one dated line per fact *with a pointer to where the detail lives* — the detail itself never gets inlined.
- `INDEX.md` scope made explicit (EN + zh-CN): it maps documents and knowledge files; code is tracked by git and the changelog, not duplicated in the index.
- The receipts line now links the 45-case failure taxonomy write-up.
- Version markers move to `<!-- wallaby-agent-rules 1.1.0 -->` on changed files.

**Migrating from 1.0.x**: nothing breaks. Paste the L2 prompt — it will offer the new `health_check.py` (scaffolding swap), the aging clause, and the pointer-discipline wording as approve-item-by-item diffs.

## 1.0.1 — 2026-10-06

**Ordering semantics fix (EN + zh-CN).** `NOW.md` updates were scheduled "at the end of every task" while `INDEX.md` registration was already "the moment it is created" — one protocol, two cadences, which quietly teaches "state can be backfilled". Both files now say: update `NOW.md` the moment tracked work moves; register new files the moment they are created. No action needed for existing users; adopting the wording is a one-line edit. (Patch — no Release, per RELEASE_CHECKLIST.)

## 1.0.0 — 2026-10-04

**Renumbered to semantic versioning.** All earlier public iterations (v1 → v4.1, September–October 2026) are folded into this 1.0.0; their details are preserved under "Pre-1.0 history" below. From here on: **patch** (1.0.1) = fixes and small adjustments, **minor** (1.1.0) = feature-level additions, **major** (1.4.0) = theme-level or breaking change. Cadence rules live in [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

Everything in the repo today — the closeout ritual, the reconcile audit, trust-building mode, the tool integrations, the code-version module, the Chinese edition, MIT + Commons Clause licensing — is 1.0.0.

**Migrating from a pre-1.0 version**: your files carry `vX` markers; treat them as the same system. Paste the L2 prompt or read [upgrade/pre-1.0.md](upgrade/pre-1.0.md) — nothing breaks, nothing is required.

## Pre-1.0 history

## v4.1 — 2026-10-04

Theme: **Memory covers versions too — and it speaks Chinese.** Two additions, one structural, one linguistic.

**Added**

- **Code & releases memory module** (conditional): a `## Code & releases` section in the entry file for projects that involve code — the current released/deployed version becomes a dated memory fact updated the moment it changes; every release, migration, or rollback gets a dated log line with the commit or tag; deploys require a committed tree (local repo = source of truth). The L1 interview mounts it via a new question 2 ("Does this project involve writing or maintaining code?") and skips it entirely for non-code projects; L0 assumes code. L3's closeout triage gains a version-state question.
- **Chinese edition**: `README.zh-CN.md` + `PROMPT.zh-CN.md` — the full system in Chinese, same prompts, same logic.

**Changed**

- L1 is now a 9-question interview (the code-or-not gate joins).
- Version markers move to `<!-- wallaby-agent-rules v4.1 -->` on changed files.

## Migrating from v4 / v4.0.1

Nothing breaks. Code projects: paste L2 and it will offer the `## Code & releases` section as an optional addition. Non-code projects: nothing to do.

## v4.0.1 — 2026-10-04

**Licensing**: MIT + [Commons Clause](LICENSE) — free for personal projects, research, and use inside your own organization; selling it (bundled, hosted, or as paid services built on it) requires a commercial license — see [COMMERCIAL.md](COMMERCIAL.md). Commits prior to this release remain under plain MIT.

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
