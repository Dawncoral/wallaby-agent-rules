<!-- wallaby-agent-rules 1.0.1 -->
# Upgrade card: pre-1.0 → 1.0.0

**TL;DR: nothing breaks, nothing is required.** 1.0.0 is a renumbering, not a rebuild. If your files carry `vX` markers (v1–v4.1), you already have this system — read on for the optional extras you may have missed.

## What 1.0.0 folds in

- The closeout ritual (v3), the deeper health check (v3), the reconcile audit (v3.1)
- Trust-building mode (v4): an optional `## Trust-building mode` section in your entry file — while active, new `MEMORY.md` entries are proposed at session end (⏳ pending, dated, sourced) and promoted only after your yes. Built for new installs; on an established project you probably don't need it.
- The code-version module (v4.1): an optional `## Code & releases` section — the current released version as a dated memory fact, releases/rollbacks logged with commit references. Only for code projects.
- Tool integration cards: `templates/integrations/` — entry file, gotchas, and a 30-second self-check for Claude Code, Codex, Cursor, GitHub Copilot, OpenHands, and Gemini CLI.
- The Chinese edition: `README.zh-CN.md` / `PROMPT.zh-CN.md`.
- Licensing: MIT + Commons Clause since v4.0.1 — see [COMMERCIAL.md](../COMMERCIAL.md).
- GitHub Releases: every version from 1.0.0 on ships as a Release with migration notes. Watch the repo (Releases only) and you'll know when there's something new.

## Replaced

- Nothing. `health_check.py` and `reconcile.py` are unchanged since v3.1.

## Your move

Two options:

1. Paste the **L2 — Upgrade check** prompt from [PROMPT.md](../PROMPT.md) — it recognizes both the old `vX` markers and the new semantic ones, and offers any additions item by item (recommended).
2. Do it by hand: add whichever optional sections you want (specs in [PROMPT.md](../PROMPT.md), L0 step 1), bump your files' first-line markers to `<!-- wallaby-agent-rules 1.0.0 -->`, and glance at your tool's card in [templates/integrations/](../templates/integrations/).

Either way, your content stays yours — that rule has not changed since v1 and won't.
