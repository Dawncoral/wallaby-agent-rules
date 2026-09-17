# wallaby-agent-rules

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](../../pulls)

**AGENTS.md is not documentation — it is a budget.** A starter template that treats your agent-instruction file as a cost-control surface: positive rules, a forbidden list, and a three-tier memory convention that ages on purpose.

Every practice here runs daily in a one-person-plus-agents production project. The bills shown are real; where the argument is mechanistic rather than measured, we say so.

## Quick start

```bash
cp AGENTS.md /your-repo/AGENTS.md
cp MEMORY.md /your-repo/MEMORY.md
# Edit the <angle bracket> placeholders. Keep the Forbidden section
# verbatim for one week before tuning.
```

Yes — the template files double as this repo's own `AGENTS.md` and `MEMORY.md`. We dogfood the standard.

Works with any tool that reads `AGENTS.md` — Codex, Cline, Cursor, Copilot, Gemini CLI, Aider, and 25+ others.

## What's inside

### 1. The forbidden list (where the savings live)

Coding agents default to doing *more* — more tests, more verification, more exploration. Each default is thousands of tokens per session. The template's `Forbidden` section cuts the five biggest leaks:

- No unit tests for presentational UI (no business logic to break)
- No computer-use / browser automation as acceptance testing — agent produces an impact checklist, a human clicks
- No refactoring outside task scope
- No unrequested features, fallbacks, or configurability
- No prose in instruction/memory files — operational statements only (the file itself is a recurring tax on every session)

### 2. Three-tier memory (active / standby / dormant)

`AGENTS.md` holds standing instructions; `MEMORY.md` holds state. Three sections:

| Tier | Contents | Loaded when |
|---|---|---|
| **Active** | Work in flight right now | Every session |
| **Standby** | Touched in the last 30 days, as one-line pointers | On demand |
| **Dormant** | Aged-out entries, append-only, dated | Never (unless asked) |

Two disciplines keep it cheap:

- **Process notes are deleted at closeout.** Git history and the decision log already hold what matters; blow-by-blow scratch is the biggest token garbage source in any memory system.
- **Entries idle for 30 days drop a tier automatically.** The per-session load stays bounded instead of growing forever.
- **Audit by delta, close by evidence.** Pick a dated baseline ("audited up to here"). Each review only scans what changed since the baseline — plus every open item, which stays open until someone checks the live system: the file, the server, the bill. A note saying "done" is a claim, not a fact. Every few weeks, re-audit in full; deltas alone let old entries rot quietly.

Heavier alternatives (vector stores, background consolidation) work, but for a solo dev they are opaque infrastructure you cannot `git diff`. Plain files win.

### 3. Closeout ritual with a drift check

Every task ends with: what changed vs. what was planned, one line per drift. Borrowed from spec-driven development's analyze step — intent and outcome drift apart silently unless you check.

### 4. A stakeholder register (the layer memory standards don't have)

AGENTS.md and CLAUDE.md teach agents how to work with code. Neither says anything about how to talk *about people* — and that failure is silent and expensive. We know, because we shipped it: a co-founder asked "what is this product for and who buys it?", and the agent answered with discount sales copy, as if he were a sales lead. The right frame was internal alignment: equip the partner so he can represent the product upstream. One register row would have prevented it.

The fix is borrowed from PMP's stakeholder register (PMBOK 13.1) and its power/interest grid — the parts of project-management canon that map cleanly onto agent instructions:

- **One row per named party**: role, tier (inner / upstream / external), a *perspective rule*, and a share ceiling (what this party may see).
- **Trigger → action, not prose**: "before writing about any person or org, look the name up; if absent, treat as external and flag." Models follow lookup tables reliably; they do not reliably act on descriptive paragraphs.
- **Manage closely vs. keep informed**: high-power/high-interest parties get decision syncs in the always-loaded tier; keep-informed parties get the filtered partner view only. The visibility tag on every memory entry (`core` / `ally`) is the communication-management plan, enforced at render time.

Cost: ~15 lines in AGENTS.md, loaded every session. Benefit: an entire failure class — right words, wrong audience — becomes structurally impossible instead of merely discouraged.

## A real bill (and an honest caveat)

We have not run the undisciplined control arm, so we will not claim a measured "savings %". What we can show is the itemized bill for a real task run under this discipline — one prompt, a complete landing page, kimi-k3 reasoning model, [Codex CLI setup per this guide](https://www.wallabytoken.com/blog/p/kimi-k3-in-codex):

| Task | Requests | Input tokens | Cached input | Output | Total cost |
|---|---|---|---|---|---|
| Bookstore landing page (300+ lines, incl. self-recovery from a tool error) | 5 | 91,155 | 85,115 (93%) | 5,987 | **$0.16** |

The case for the forbidden list is mechanistic, not an A/B measurement: every banned behavior is an extra request loop, and every extra request resends the agent's framework prompt. Ban the loops and the bill lands on actual work — note the cache column, where 93% of repeated input was served at one-tenth price.

## Example

[`examples/MEMORY.example.md`](examples/MEMORY.example.md) shows the three tiers filled in, eight weeks after adoption — two lines in Active, pointers everywhere else, dates making the 30-day downgrade rule executable. Read it before writing your own; the tier boundaries matter more than tidy lines.

## Cold-start prompt

[`COLD_START.md`](COLD_START.md) is a paste-in first message that bootstraps this whole convention in a blank project: the agent does recon, builds the governance files (three-tier memory, capability registry, decision log, doc index), adopts the standing rules, picks a reconciliation mode that matches its platform (cron / weekly self-check / trigger words), and reports back with a to-confirm list — guesses it almost wrote as facts, isolated for your sign-off. That last step is the anti-hallucination gate; do not skip it.

## Field notes (failure modes we actually hit)

From running this daily with Codex CLI and Cline on a third-party endpoint:

- **Tool-call shape errors self-heal — let them.** A reasoning model occasionally calls the editor's file tool with mis-shaped arguments. The harness feeds the error back, the model retries differently, and it lands. Don't add prompt rules for this; retries are cheaper than rules loaded forever.
- **A dropped stream is not a lost session.** Type `continue`; the agent picks up mid-task. Know this before you re-prompt from scratch and pay the full framework prompt twice.
- **Never chat casually with a coding agent.** A bare "say ok" through Codex CLI costs 9,481 tokens before the model starts answering — the framework prompt rides on every turn. Give agents tasks, not small talk.
- **A log entry is a claim, not a fact.** We once had a hardening item that every record treated as done — until a live check showed the config was never set. Now nothing closes without fresh evidence from the system itself, and a standing baseline means reviews cost minutes, not days.
- **Right words, wrong audience.** A co-founder asked what our product does and who it is for, and the agent answered with discount sales copy — partner treated as lead. Framing errors pass every spell-check; only a register lookup catches them. See section 4.

## FAQ

**Why not a vector store / RAG memory?**
It works, but you cannot `git diff` an embedding. Plain files give you review, rollback, and blame for free — and with three tiers, the retrieval problem they solve mostly disappears: Active is small enough to just read.

**Tools truncate AGENTS.md around 32 KiB — how do I stay under?**
That is the point of the split: standing rules (small, stable) in AGENTS.md, state (grows forever) in MEMORY.md with only the Active tier loaded by default. Our production AGENTS.md is under 200 lines after months of use.

**I use several agent tools (Codex + Cline + Cursor). One file or many?**
One. AGENTS.md is read natively by 30+ tools. Keep tool-specific quirks out of it; they belong in each tool's own config, not in the file every tool pays for.

**Won't the forbidden list block legitimate work?**
Every rule ends with the same escape hatch: "without explicit human approval." You are banning defaults, not capabilities. Anything on the list is allowed the moment you ask for it.

## Full write-up

[AGENTS.md as a token budget: positive rules are not enough — you need a forbidden list](https://www.wallabytoken.com/blog/p/agents-md-token-budget)

## Why we built this

Wallaby Token is a one-person-plus-agents operation running an API
gateway for open-weight models. These rules are not advice we sell —
they are what keeps our own token bill survivable while agents do the
daily coding, deploys, and writing.

We think the interesting question of this decade is how much real
infrastructure one person and a few agents can run. This repo is part
of our answer, in public.

[wallabytoken.com](https://www.wallabytoken.com)

## License

MIT — adapt freely, attribution appreciated.
