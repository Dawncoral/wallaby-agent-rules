# wallaby-agent-rules

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](../../pulls)

**AGENTS.md is not documentation — it is a budget.** A starter template that treats your agent-instruction file as a cost-control surface: positive rules, a forbidden list, and a three-tier memory convention that ages on purpose.

Every practice here runs daily in a one-person-plus-agents production project. Every number is measured, with the bill to prove it.

## Quick start

```bash
cp AGENTS.template.md /your-repo/AGENTS.md
cp MEMORY.template.md /your-repo/MEMORY.md
# Edit the <angle bracket> placeholders. Keep the Forbidden section
# verbatim for one week before tuning.
```

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

Heavier alternatives (vector stores, background consolidation) work, but for a solo dev they are opaque infrastructure you cannot `git diff`. Plain files win.

### 3. Closeout ritual with a drift check

Every task ends with: what changed vs. what was planned, one line per drift. Borrowed from spec-driven development's analyze step — intent and outcome drift apart silently unless you check.

## Measured results

Same-class task (agent builds a complete landing page from one prompt), kimi-k3 reasoning model, [Codex CLI setup per this guide](https://www.wallabytoken.com/blog/p/kimi-k3-in-codex):

| Task | Requests | Input tokens | Cached input | Output | Total cost |
|---|---|---|---|---|---|
| Bookstore landing page (300+ lines, incl. self-recovery from a tool error) | 5 | 91,155 | 85,115 (93%) | 5,987 | **$0.16** |

Note the cache column: a disciplined setup makes the agent's repeated framework prompt hit cache at one-tenth price, so the bill goes to actual work instead of overhead. Undisciplined loops (UI unit tests + browser-automation acceptance) multiply request counts several times over on the same task.

## Example

[`examples/MEMORY.example.md`](examples/MEMORY.example.md) shows the three tiers filled in, eight weeks after adoption — two lines in Active, pointers everywhere else, dates making the 30-day downgrade rule executable. Read it before writing your own; the tier boundaries matter more than tidy lines.

## Field notes (failure modes we actually hit)

From running this daily with Codex CLI and Cline on a third-party endpoint:

- **Tool-call shape errors self-heal — let them.** A reasoning model occasionally calls the editor's file tool with mis-shaped arguments. The harness feeds the error back, the model retries differently, and it lands. Don't add prompt rules for this; retries are cheaper than rules loaded forever.
- **A dropped stream is not a lost session.** Type `continue`; the agent picks up mid-task. Know this before you re-prompt from scratch and pay the full framework prompt twice.
- **Never chat casually with a coding agent.** A bare "say ok" through Codex CLI costs 9,481 tokens before the model starts answering — the framework prompt rides on every turn. Give agents tasks, not small talk.

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

## License

MIT — adapt freely, attribution appreciated.
