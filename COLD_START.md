# Cold-start prompt: bootstrap an agent memory system

A companion to `AGENTS.md` / `MEMORY.md`. Those two files are the steady state — this prompt is how you get there in a blank project. Paste the block between the rules into any agent as its first message (or into its system prompt). The agent then runs five steps on its own: recon → build the files → adopt the standing rules → pick a reconciliation mode → report for acceptance.

Nothing here is tied to a domain, a stack, or a folder layout you already have. Works with any agent that can read and write files; a chat-only agent can still run it if you save its output yourself (see the operator notes at the bottom).

---

I want a memory system for this project, and you will cold-start it. The problem it solves: **you lose your memory every session, and the project's facts, decisions, progress, and capabilities should not depend on me repeating myself.** Once built, you run on these rules permanently.

## What you are building

```
project root
└── 00_governance/
    ├── memory/
    │   ├── map.md           Structure: what the project is made of, what touches what (one line per item)
    │   ├── L1_baseline.md   Permanent: unchanging facts and iron rules (append-only, edits need my approval)
    │   └── L2_current.md    Current: top half = in flight, bottom half = standby (touched within 30 days)
    ├── capabilities.md      Capability layer: the single registry of scripts/tools/templates/automations
    ├── changelog.md         Chronological log of events; newest entry always on top, dated
    ├── decisions.md         Decision log (numbered D-001 up, newest first), append-only
    └── doc-index.md         One-line index of every document in the repo (register each new doc on creation)
```

Two core principles:

1. **Instructions (how to work) live in AGENTS.md or the system prompt and never age out; state (facts/progress/decisions) lives in the layered memory, tiered by activity.** Side by side, never overlapping.
2. **Capabilities (what I can do) get their own layer.** Finding an existing capability costs ~1k tokens; rebuilding one costs ~1M — a mechanistic estimate (whole-file rewrites vs. one lookup), not an A/B measurement. A lost tool that gets rebuilt from scratch is the biggest hidden waste in agent work.

## Step 1: Recon — no writing before this

Scan the project as it exists: directory tree, README, existing docs, the last 20 git log entries, config files. Goal: answer three questions — what is this project, where is it now, and what rules must never be broken (compliance, security, money).

## Step 2: Build the files

- **L1**: only long-term facts (entity, positioning, key people and roles, infrastructure, pricing/resource anchors, iron rules). Cite a source for each. **Never invent anything you are unsure of — put it on the to-confirm list instead.**
- **L2**: infer "what has been happening lately" from git log and document freshness. Top half active, bottom half standby, each entry dated.
- **map.md**: one line per item — `name | one-liner | propagation keywords`. Inclusion test, exactly one: **if this changes, would I need to judge what else it affects?** If yes, it goes in. Details, parameters, and scratch work do not.
- **capabilities.md**: one line per capability — `name | one-liner | trigger/entry point | path`. An empty table header is fine on day one — **its discipline matters more than its contents** (see step 3).
- **changelog.md**: the first entry records this cold-start itself.
- **decisions.md**: factual decisions you found during recon, numbered from D-001.
- **doc-index.md**: register every existing document, one line each.

Size discipline: L1 soft cap 150 lines / hard cap 180; L2 soft 200 / hard 240; map.md around 2,500 tokens. Split files only when a hard cap is breached — never cut just to be tidy.

## Step 3: Standing rules (you follow these every session from now on)

**Boot sequence**: at the start of every session, read map.md → L1 → L2 (about 250 lines total), then scan the top 10 changelog entries. Only then take work.

**Conflict arbitration**: what the files say > what you remember > what you infer. On conflict, follow the file and point the conflict out to me.

**Three-step lookup chain**: ① follow in-line pointers in memory files straight to the target file → ② check doc-index.md → ③ full-text search as last resort.

**Capability reuse discipline**: before building any script/tool/template/automation, grep capabilities.md first — hit means reuse, miss means build, and **register the new capability the moment it lands**. Minimum bar for making something permanent: the need has recurred ≥2 times or has a clear cadence. One-off things do not get made permanent.

**Closeout routing** (after every task, each outcome goes exactly one of four ways):

- Changed a long-term fact → propose an L1 edit (you edit only after I approve)
- Was a judgment call / decision → append to decisions.md (append-only)
- Just "got done" → insert one entry at the top of changelog.md (local time with timezone, format copied from existing entries; **re-read the file top before writing** — a parallel session may have just written)
- Process chatter → discard it (git already has the trace; scratch is the biggest token garbage source)

**Red lines**:

1. Keys/credentials/passwords: never read, never print, never commit
2. Before any external-facing text goes out, ask me whether an established style guide / forbidden list exists; if none, we write one together before the first release
3. External dates = actual publication dates; never pass off a drafting date as a release date
4. I hold the release button: you produce drafts/staged work; going live, deploying, and sending require my confirmation
5. Before deleting data, changing a database, or touching a live service: list the blast radius and wait for my approval

## Step 4: Reconciliation fallback (pick one of three modes, by platform capability)

Memory drifts (the file says A, reality is already B). The fallback is a **weekly reconciliation**: check line-count caps, broken pointers, L2 entries untouched for 30 days that should drop a tier, gaps in the changelog, drift from the style guide. Output: **a checklist for me to tick**. **Red line: the checklist only — you never edit L1 on your own; you execute only what I ticked.**

Pick one trigger mode by what your platform can do (tell me which you picked at cold-start):

- **Mode A — has scheduled tasks** (cron / scheduled jobs): run at a fixed time each week, send me the result or save it to a file
- **Mode B — no scheduler, but cross-session state**: self-check at the start of the first session each week — if the last reconciliation was ≥7 days ago, run it before taking new work
- **Mode C — pure stateless chat**: teach me the trigger words — when I say "reconcile" / "audit", you run it; and at every closeout you remind me how many days it has been since the last one

## Step 5: Acceptance report (what "cold-start done" means)

Report back in ≤15 lines:

1. Which files you built and what each holds (one line per file)
2. Your understanding of the project (what it is / where it is / what the rules are)
3. Which reconciliation mode you picked, and why
4. **To-confirm list**: facts you were not sure about and need me to confirm personally (numbered)

I confirm or correct the list item by item, you write the results back into L1/L2 — only then is cold-start complete.

---

## Operator notes (not part of the prompt)

- **The acceptance gate is step 5.** The to-confirm list is the anti-hallucination core: when an agent builds files it is most tempted to write guesses as facts. Forcing it to isolate uncertainties for human sign-off is the whole trick.
- **Chat-only agent (no file access)?** Paste the step-3 rules into its system prompt; change steps 1/2/5 so it outputs the file contents as text and you save them yourself. Reconciliation defaults to mode C.
- **Where this evolves once running** (not in this prompt): scripted reconciliation (mechanical checks, zero model tokens), change-propagation scans (edit A, find every mention of A), and a bill-based evaluation of whether the system actually saves tokens.
- Version: v1.0 (initial) → v1.1 (2026-09-17) added the capability layer and the three-mode reconciliation abstraction.

---

Maintained as part of [wallaby-agent-rules](https://github.com/Dawncoral/wallaby-agent-rules) — the memory discipline above is what runs our own operation daily.
