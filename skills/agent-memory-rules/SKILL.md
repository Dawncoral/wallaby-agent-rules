---
name: agent-memory-rules
description: Build and maintain a file-based long-term memory system in any project — entry file (AGENTS.md or per-tool variant), tiered MEMORY.md with aging, session closeout ritual, weekly health-check scripts. Use when project context gets re-explained every session, files are hard to locate, or the user says "remember this".
version: 1.0.0
author: Wallaby Token
license: MIT
metadata:
  hermes:
    tags: [Memory, Context, Productivity, Agent Workflow]
---

# Agent Memory Rules

Agents forget everything between sessions. This skill builds a small file-based memory system inside the project: a few Markdown files plus two zero-dependency check scripts, wired together by standing rules that keep it true. Once built, the agent reads its memory at every session start and the user stops repeating themselves.

## When to Use

- Project facts, decisions, or conventions get re-explained at the start of sessions.
- The user says "remember this", "wrap up", or "that's wrong" and expects it to stick.
- The project is large enough that finding a file takes searching instead of knowing.
- An existing memory setup (MEMORY.md, CLAUDE.md, .cursorrules) needs an upgrade path that never overwrites user content.

## What You Build

Six pieces, all inside the project:

1. **Entry file** at the project root — pick by tool: `AGENTS.md` (default; also read by Hermes, Codex, and most agents), `CLAUDE.md` (Claude Code), `GEMINI.md` (Gemini CLI), `.cursorrules` (legacy Cursor). If one exists, merge, never overwrite.
2. **`MEMORY.md`** — long-term memory. Permanent facts and iron rules only, one dated line per fact with a pointer to where the detail lives. The detail itself never gets inlined.
3. **`NOW.md`** — current state. Work in flight on top, recently touched (last 30 days) below. Entries idle 30 days drop out at the next update.
4. **`INDEX.md`** — the project map. One line per file: `path | what it is`. Scope: documents and knowledge files; code is tracked by git, not duplicated here. Build the first version by actually scanning the project — never hand over an empty template.
5. **`LOG.md`** — dated, append-only, newest on top. Releases, migrations, evidence for future judgment calls.
6. **`scripts/health_check.py` and `scripts/reconcile.py`** — copy them from this skill's `scripts/` directory (or fetch the current versions from the wallaby-agent-rules repo — see Source below). Zero dependencies, Python 3, exit 0 when clean and 1 with findings.

## Procedure

1. **Recon first — no writing before this.** Scan the project as it exists: directory tree, README, existing docs, the last 20 git log entries, config files. Answer three questions: what is this project, where is it now, what rules must never be broken.
2. **Write the entry file** with these sections:
   - One paragraph of project orientation: what it is, what "done" looks like. Facts only.
   - `## Memory protocol` — the standing rules in the next section.
   - `## Ritual words` — map the user's own words to actions: "wrap up" → run the closeout ritual, "note this" → append the conclusion dated to LOG.md, "that's wrong" → record what happened and what should have happened.
   - `## Red lines` — credentials: never read, never print, never commit. Before deleting data, changing a database, or touching a live service: list what will be affected and wait for approval. The agent drafts; the user releases.
   - `## Code & releases` (code projects only) — the current released version is a dated memory fact, updated the moment it changes; every release, migration, or rollback gets one dated LOG.md line with the commit or tag; deploy only from a committed tree.
   - `## Trust-building mode` (optional, recommended for the first two weeks; record the install date). While active, new MEMORY.md entries are proposed at session end marked ⏳ pending, dated, with a source, and promoted only after the user's yes. It expires two weeks after install, or the moment the user says "trust mode off".
3. **Create MEMORY.md, NOW.md, INDEX.md, LOG.md** from recon. Guesses go on the to-confirm list, never into the files as facts.
4. **Copy the two scripts** into `scripts/` and run both once to confirm the exit-code contract works.
5. **Report back in ≤15 lines**: files built, your understanding of the project, and a numbered to-confirm list. The user confirms or corrects item by item; you write the results back. Only then is the build complete.

## Standing Rules (what goes into the entry file)

- At the start of every session, read `MEMORY.md` and `NOW.md` before taking work. Before searching for any file, check `INDEX.md` first.
- Conflict order: what the memory files say > what you remember > what you infer. On conflict, follow the file and flag it to the user.
- Update `NOW.md` the moment tracked work moves; register new files in `INDEX.md` the moment they are created; delete process scratch; git history already holds the trace.
- Aging: when MEMORY.md passes its soft wall (~150 dated lines or ~8k estimated tokens, CJK-weighted), facts untouched for 30+ days move to `LOG.md` at the next closeout. Git keeps the history.

## Closeout Ritual (on "wrap up")

Two minutes at the end of a session:

1. **Triage** everything the session produced: lasting fact or rule → one dated, sourced line in MEMORY.md (propose instead, while trust-building mode is active); evidence for later → LOG.md; version state change → LOG.md line with the commit or tag plus the version line update; "this got done" → NOW.md with a pointer; process scratch → delete.
2. **Update INDEX.md** if files were created or removed.
3. **Drift check**: compare what the session set out to do with what happened, one line per drift, recorded in LOG.md.
4. **Report in ≤8 lines**: what moved where, what is pending approval, what drifted, and a to-confirm list.

## Weekly Checks

```bash
python3 scripts/health_check.py   # ten scans: clutter, unregistered files, stale entries, size walls, secrets hygiene, commit silence
python3 scripts/reconcile.py      # two scans: closure contradictions, evidence-free closures
```

Both exit 0 when clean, 1 with findings. Run them weekly, or wire them into a cron job.

## Pitfalls

- **The entry file is the only auto-loaded piece.** Most tools inject the entry file at session start but not MEMORY.md; the read-protocol rule is what pulls it in. Keep the entry file lean: several tools truncate context files (a ~32 KiB cap is common; Hermes scales the cap with the model's context window, 20K chars floor).
- **Never invent facts.** Anything uncertain goes on the to-confirm list.
- **No secrets in memory files.** Not keys, not tokens, not "temporary" credentials. The health check scans for common key patterns and will flag them.
- **The closeout is the maintenance schedule.** Skip it and the files drift from reality within a week; after that the agent quotes stale memory with confidence, which is harder to debug than no memory.

## Verification

Thirty seconds: start a new session in the project and ask "what do you remember about this project?" The answer should quote `MEMORY.md` and `NOW.md`. If it does not, the entry file is not wired, so check which file your tool actually reads at startup.

## Source

Maintained at [wallaby-agent-rules](https://github.com/Dawncoral/wallaby-agent-rules): templates, per-tool integration cards, version history, and the current copies of both scripts. MIT + Commons Clause; adapt freely, attribution appreciated.
