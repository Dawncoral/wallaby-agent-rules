<!-- wallaby-agent-rules v3.1 -->
# PROMPT.md — paste-in prompts for your AI

Four self-contained prompts. Pick one, copy the whole fenced block, and paste it to the AI that works in your project (Kimi Code, Claude Code, Cursor, Codex, or any agent that can read and write files). No install, no dependencies — the AI builds everything itself.

| Prompt | Time | What it does |
|---|---|---|
| **L0 — One-click install** | ~30 seconds | Builds the full memory system with sensible defaults (solo developer profile). Zero questions asked. |
| **L1 — 7-question interview** | ~2 minutes | The AI asks you 7 short questions, then builds the same system tuned to your answers. |
| **L2 — Upgrade check** | ~2 minutes | For projects that already have memory files. The AI detects your version and proposes an incremental upgrade — your content is never overwritten. |
| **L3 — Closeout ritual** | ~2 minutes, daily | The end-of-session routine that keeps the system true: triage what happened, check the drift, update the files. Hang it on a word you already say. |

L0 is not a separate system: it is L1 with every question answered by default. Both run the same build (described inside each prompt), so there is one logic, two entry points.

> Chat-only AI (no file access)? Paste the prompt anyway and add one line: *"Output each file's full content as text; I will save them myself."*

---

## L0 — One-click install

Copy everything between the rules and paste it to your AI:

````
I want a long-term memory system for this project, and you will build it now. The problem it solves: **you lose your memory every session, and the project's facts, decisions, and progress should not depend on me repeating myself — and I should be able to find any file in this project in seconds.** Once built, you run on these rules permanently.

Build with the default profile (no questions — just build):

- AI tool: generic — generate `AGENTS.md` as the entry file
- Project size: 50–300 files — one flat index
- Solo developer
- Conversation volume: 10–30 rounds/day — standard memory budget
- Record style: balanced — concise entries, generous pointers
- Weekly health check: ON
- Ritual words: defaults — "wrap up" / "note this" / "that's wrong"

## What you build (6 files)

1. **Entry file: `AGENTS.md`** at the project root (if one exists, merge — never overwrite what is already there). Contents, in order:
   - One paragraph of project orientation: what this project is, what "done" looks like. Facts only.
   - A `## Memory protocol` section with these standing rules:
     - At the start of every session, read `MEMORY.md` and `NOW.md` before taking work.
     - Before searching for any file, check `INDEX.md` first.
     - Conflict order: what the memory files say > what you remember > what you infer. On conflict, follow the file and flag it to me.
     - At the end of every task: update `NOW.md` if tracked work moved, register any new file in `INDEX.md` the moment it is created, and delete process scratch (git history already holds the trace).
   - A `## Ritual words` section mapping my words to actions:
     - "wrap up" (and variants like "that's it for today") → run the closeout ritual: triage every conclusion into MEMORY.md / LOG.md / NOW.md / the bin, run the drift check, report in a few lines. (Full routine: the "L3 — Closeout ritual" prompt in the wallaby-agent-rules repo.)
     - "note this" → append the current conclusion, dated, to `LOG.md`.
     - "that's wrong" → record what happened and what should have happened, so the same miss gets caught next time.
   - A `## Red lines` section:
     - Keys, credentials, passwords: never read, never print, never commit.
     - Before deleting data, changing a database, or touching a live service: list what will be affected and wait for my approval.
     - You draft; I release. Deploying, publishing, and sending require my confirmation.

2. **`MEMORY.md`** — long-term memory. Permanent facts and iron rules only: what the project is, key decisions and why, constraints that must never be broken (compliance, security, money). One line per fact, dated, with a source for each (file path, commit, or "told by owner"). **Never invent anything you are unsure of — put it on the to-confirm list instead.** Nothing in this file ages out.

3. **`NOW.md`** — current state. Top section: work in flight right now, one dated line per item with a pointer to details. Bottom section: recently touched (last 30 days), one-line pointers only. Anything idle for 30 days gets removed at the next update — its history lives in git. Use the layout in `templates/NOW.md` from the wallaby-agent-rules repo as the reference structure.

4. **`INDEX.md`** — the project map. One line per file: `path | what it is, in a few words`. **Build the first version right now by actually scanning this project** — do not leave it as an empty template. Group by directory if the project is large. From now on, every new file gets registered here the moment it is created.

5. **`scripts/health_check.py`** — a zero-dependency Python 3 script that runs seven scans: (a) stray files in the project root beyond a whitelist, (b) generated artifacts (.zip/.tmp/.pyc/.log) sitting at the top level of subdirectories, (c) .md files not registered in INDEX.md, (d) NOW.md entries idle past 30 days, (e) INDEX.md registrations pointing at files that no longer exist, (f) entry files past the size wall — ~32 KiB bytes, ~500 lines, or ~8k estimated tokens, whichever bursts first (CJK text fills byte budgets ~3x faster per character), (g) MEMORY.md bullet lines with no date. Exit code 0 when clean, 1 when findings. If you can fetch `templates/health_check.py` from the wallaby-agent-rules repo, use it verbatim; otherwise write it to that spec.

6. **`scripts/reconcile.py`** — a zero-dependency Python 3 script that runs two scans: (a) closure contradictions — LOG.md entries that claim something is done (shipped / fixed / merged / published / ...) while the same topic still sits in NOW.md's "In flight" section; (b) evidence-free closures — "done" entries with no path, ticket, link, or backtick reference to verify against. Same exit-code contract as the health check. If you can fetch `templates/reconcile.py` from the wallaby-agent-rules repo, use it verbatim; otherwise write it to that spec.

## How you build it

1. **Recon first — no writing before this.** Scan the project as it exists: directory tree, README, existing docs, the last 20 git log entries, config files. Answer three questions: what is this project, where is it now, what rules must never be broken.
2. **Build the 6 files above**, inferring content from recon. Guesses go on the to-confirm list, never into the files as facts.
3. **Report back in ≤15 lines**: which files you built (one line each), your understanding of the project, and a numbered **to-confirm list** of facts you were unsure about. I confirm or correct item by item; you write the results back. Only then is the build complete.
4. **Finish with a 5-line "how to use this from now on"** for me: what happens at every new chat (you read MEMORY + NOW automatically), how I find files (INDEX.md), when to run the weekly checks (`python3 scripts/health_check.py` and `python3 scripts/reconcile.py`), how I close a session (say "wrap up"), and how I change the rules (edit MEMORY.md directly).
````

---

## L1 — 7-question interview

Copy everything between the rules and paste it to your AI:

````
I want a long-term memory system for this project — so that you remember across sessions and I can find any file in seconds. You will build it, but first you will calibrate it by asking me exactly 7 questions. Ask them one by one, numbered, with the options listed. Wait for each answer before asking the next.

1. **Which AI coding tool do you mainly use?** (Kimi Code / Claude Code / Cursor / other)
   → Decides the entry file: AGENTS.md (Kimi Code and most tools) / CLAUDE.md (Claude Code) / .cursorrules (Cursor). This is the file your tool reads at the start of every session.
2. **Roughly how many files are in this project?** (<50 / 50–300 / >300)
   → Decides index granularity: one flat table, or a section per top-level directory.
3. **Solo or team?**
   → Team adds a "Shared conventions" section to the entry file: anyone may edit the memory files, and every edit needs a one-line reason appended.
4. **How many rounds do you talk with the AI per day?** (<10 / 10–30 / >30)
   → Decides the memory budget: heavy use gets tighter caps (shorter NOW.md, faster pruning); light use gets looser ones.
5. **Detailed records or lean ones?**
   → Decides entry length and summary depth. Detailed also adds a `LOG.md` — a dated, append-only log, newest entry on top.
6. **Should the AI periodically check for file clutter and remind you to tidy up?** (yes, default / no)
   → Installs `scripts/health_check.py` and `scripts/reconcile.py` plus a weekly-run reminder in the entry file, or skips all three.
7. **What words do you actually say when you're done, or when something must be remembered?** (defaults: "wrap up" / "note this" / "that's wrong")
   → Installs a `## Ritual words` section in the entry file: when you say one of these words, the AI runs the matching ritual — closeout triage, log the conclusion, or record a failure. The system adapts to your language, not the other way around.

After my last answer, tell me in 3 lines which profile you derived, then build immediately — no further questions.

## What you build

The same files as the one-click install, parameterized by my answers:

1. **Entry file** (per Q1) at the project root — merge, never overwrite, if one exists. Contents: one paragraph of project orientation; a `## Memory protocol` section (read MEMORY.md + NOW.md at every session start; check INDEX.md before searching for files; conflict order: files > your memory > your inference — on conflict follow the file and flag it; at every task end update NOW.md, register new files in INDEX.md, delete process scratch); a `## Ritual words` section (per Q7 — each word mapped to its ritual: "wrap up" → closeout triage + drift check, "note this" → dated log entry, "that's wrong" → record the failure and the expected behavior); a `## Red lines` section (credentials: never read/print/commit; destructive or live-service actions: list the blast radius and wait for approval; you draft, I release); plus the Q3/Q6 additions if applicable.
2. **`MEMORY.md`** — long-term memory: permanent facts, key decisions with reasons, iron rules. One dated line per fact with a source. Never write guesses as facts — unsure items go on the to-confirm list. Nothing here ages out.
3. **`NOW.md`** — current state: work in flight (dated lines with pointers) on top, recently-touched pointers below; entries idle 30 days are pruned at the next update. Caps per Q4/Q5.
4. **`INDEX.md`** — one line per file (`path | what it is`), granularity per Q2. **Build the first version now by actually scanning the project** — never hand me an empty template. New files get registered on creation from now on.
5. **`scripts/health_check.py`** (if Q6 = yes) — zero-dependency Python 3, seven scans: stray root files beyond a whitelist; generated artifacts (.zip/.tmp/.pyc/.log) at subdirectories' top level; .md files missing from INDEX.md; NOW.md entries idle past 30 days; INDEX.md registrations pointing at missing files; entry files past the size wall — ~32 KiB bytes, ~500 lines, or ~8k estimated tokens, whichever bursts first (CJK text fills byte budgets ~3x faster per character); MEMORY.md bullets with no date. Exit 0 clean / 1 findings. Use `templates/health_check.py` from the wallaby-agent-rules repo verbatim if you can fetch it.
6. **`scripts/reconcile.py`** (if Q6 = yes) — zero-dependency Python 3, two scans: closure contradictions (LOG.md claims done while NOW.md still lists the topic in flight) and evidence-free closures ("done" with no path, ticket, link, or backtick reference). Same exit-code contract. Use `templates/reconcile.py` from the wallaby-agent-rules repo verbatim if you can fetch it.
7. **`LOG.md`** (if Q5 = detailed) — dated, append-only, newest on top.

## How you build it

1. **Recon first** — directory tree, README, existing docs, last 20 git log entries, config files. No writing before this.
2. **Build the files**, inferring content from recon; guesses go to the to-confirm list.
3. **Report in ≤15 lines**: files built, your understanding of the project, numbered to-confirm list. I confirm or correct item by item; you write the results back.
4. **Finish with a 5-line "how to use this from now on"**: new chats auto-read MEMORY + NOW; find files via INDEX.md; run the weekly checks (`python3 scripts/health_check.py` and `python3 scripts/reconcile.py`); close sessions with your ritual word; change rules by editing MEMORY.md directly.
````

---

## L2 — Upgrade check

Already have memory files from an earlier version of this system (or your own)? Paste this to your AI:

````
This project already has memory/instruction files. I want to upgrade them to the latest wallaby-agent-rules setup — incrementally, without losing anything I wrote.

## Three iron rules (these override everything below)

1. **Add, never overwrite.** New files (NOW.md, INDEX.md, scripts/health_check.py, scripts/reconcile.py, LOG.md) are simply created. Changes to files that already exist are only ever *proposed as diffs*.
2. **My content is sacred.** Every line I wrote in existing files stays untouched. You may only add empty sections, new slots, or structural markers — and only after I approve.
3. **Nothing changes without my confirmation.** You produce a checklist; I approve item by item; you execute only what I approved.

One explicit exception: `scripts/health_check.py` and `scripts/reconcile.py` are scaffolding — they contain none of my content, so when a newer version exists you may offer to replace them outright (show me the diff summary first).

## Step 1: Scan and identify the version

Find every memory/instruction file in this project (AGENTS.md, CLAUDE.md, .cursorrules, MEMORY.md, NOW.md, INDEX.md, LOG.md, COLD_START.md, and anything similar).

- A first-line comment `<!-- wallaby-agent-rules vX -->` states the version directly.
- No marker → infer from fingerprints:
  - **v3.1**: as v3, plus `scripts/reconcile.py` exists (two scans).
  - **v3**: a `## Ritual words` section in the entry file; health_check.py (if present) runs seven scans; no `scripts/reconcile.py`.
  - **v2**: NOW.md and INDEX.md exist; no `## Ritual words` section in the entry file; health_check.py (if present) runs three scans.
  - **v1**: an AGENTS.md built around a forbidden list, a MEMORY.md with Active/Standby/Dormant tiers, no NOW.md or INDEX.md.
- Tell me which version you detected and the evidence, before proposing anything.

## Step 2: Propose an incremental upgrade list

Compare what exists against the v3.1 layout (entry file with Memory protocol + Ritual words + Red lines; MEMORY.md long-term facts; NOW.md current state; INDEX.md project map; scripts/health_check.py with seven scans; scripts/reconcile.py with two scans; optional LOG.md). Output a numbered checklist:

- **Add** — files that do not exist yet. For INDEX.md, scan the project and show me the first full version you would write.
- **Suggest change** — for each existing file, show a diff: what you would add (the `## Ritual words` section, the v3.1 version marker) and, if anything looks redundant under v3.1, what you *recommend* moving — clearly marked as optional, never executed without my explicit yes per item.
- **Replace (scaffolding only)** — if scripts/health_check.py exists and is older than seven scans, or scripts/reconcile.py exists and is older than two scans, offer to swap in the current version from the wallaby-agent-rules repo. These are the only files you may replace outright.

## Step 3: Execute only what I approve

I reply with the item numbers I accept. You execute exactly those, then re-report the final file layout. Anything I skipped stays as it is.
````

---

## L3 — Closeout ritual

The two-minute routine that keeps the whole system true. Run it at the end of a work session — or better, hang it on a ritual word in your entry file and just say the word. Paste this to your AI:

````
Run the closeout ritual for this session.

## Step 1: Triage everything this session produced

For each outcome, one question decides where it goes:

1. **Did it change a lasting fact or rule?** → Add one dated line, with a source, to `MEMORY.md`.
2. **Is it evidence for a future judgment call?** → Append one dated line to `LOG.md`. Append-only — never rewrite history.
3. **Is it just "this got done"?** → One dated line in `NOW.md`, with a pointer to where the detail lives. While here: move anything idle 30+ days out of NOW.md — git history keeps the record.
4. **Is it process scratch?** → Delete it. Intermediate notes and abandoned approaches are the largest source of context garbage; git already holds the trace.

If files were created or removed this session, update `INDEX.md` now.

## Step 2: Drift check

Compare what this session set out to do with what actually happened — one line per drift, with the reason. Record the drift itself in `LOG.md`: next session's plan will be built on what I think happened, so keep that true.

## Step 3: Report

In ≤8 lines: what moved where (MEMORY / LOG / NOW / INDEX), what drifted and why, and a to-confirm list of anything you were unsure of — unsure items never go into the files as facts.
````

Two minutes, once, at the end of the session. Skip it twice and you are back to trusting the context window — which is where the rot started.

---

Maintained as part of [wallaby-agent-rules](https://github.com/Dawncoral/wallaby-agent-rules). Version history and migration notes: [CHANGELOG.md](CHANGELOG.md).
