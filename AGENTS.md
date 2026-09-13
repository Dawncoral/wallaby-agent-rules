# AGENTS.md — token-budget starter template
# Source: Wallaby Token engineering practice — https://www.wallabytoken.com/blog/p/agents-md-token-budget
# License: MIT — adapt freely, attribution appreciated.
#
# Setup: copy to your repo root as AGENTS.md, replace <angle brackets>,
# then DELETE this comment block — every line left in this file is loaded
# into every session, so the file itself is a recurring tax. 100–300 lines
# total; several tools truncate at ~32 KiB.
#
# The architecture in one sentence:
#   AGENTS.md = standing instructions (never age)  ↔  MEMORY.md = state (always ages)
# This file defines how memory works; MEMORY.md holds what is going on.

# Project

<One paragraph: what this repo is, what "done" looks like. No history,
no marketing — the agent needs orientation, not motivation.>

## Memory protocol (read this first)

State lives in `MEMORY.md` beside this file, in three tiers:

- **Active** — work in flight right now. At session start, read ONLY this
  section.
- **Standby** — one-line pointers to anything touched in the last 30 days.
  Follow a pointer only when the current task needs it.
- **Dormant** — aged-out entries. Append-only history; never rewrite.

Maintenance rules:

- Anything idle for 30 days moves down one tier at closeout.
- Standing rules live HERE and never age; state lives THERE and always
  ages. Never write state into this file, and never write rules into
  MEMORY.md.
- Conflict order: this file > MEMORY.md > your own recollection.

## Scope

- Start in the directory named by the task: `<main dirs and what lives
  where>`. Repo-wide exploration requires a stated reason.
- Out of bounds unless explicitly asked: `<dirs>`.
- Why: unscoped exploration is the largest single token leak in agentic
  coding — it re-reads the same files every session.

## Verify

- One canonical check: `<test/build command>`. Run it before declaring any
  task done. Do not invent a new verification ritual per task.

## Forbidden without explicit human approval

- DO NOT write unit tests for presentational UI (no business logic to
  break). Visual verification is a human's three-second job; the agent's
  version costs thousands of tokens in screenshots and DOM comparisons.
- DO NOT use computer-use / browser automation as acceptance testing.
  Produce an impact checklist; a human clicks.
- DO NOT refactor, reformat, or "improve" code outside the task scope.
- DO NOT add features, fallbacks, or configurability nobody asked for.
- DO NOT write prose explanations into instruction or memory files —
  operational statements only.

Each of these is a default behavior of coding agents. Each default is a
recurring token leak. Ban the leak, keep the capability: anything here is
allowed the moment a human asks for it.

## Closeout (end of every task)

1. **Drift check**: state what changed vs. what was planned. One line per
   drift, with the reason. Intent and outcome drift apart silently unless
   you check.
2. **Memory update**: touch MEMORY.md only if the task changed a settled
   fact, produced a decision worth keeping, or finished tracked work.
   Otherwise write nothing.
3. **Delete process notes.** Git history and the decision log already hold
   what matters; blow-by-blow scratch is the biggest token garbage source
   in any memory system.
