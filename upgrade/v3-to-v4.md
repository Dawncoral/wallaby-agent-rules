<!-- wallaby-agent-rules v4 -->
# Upgrade card: v3.x → v4

**TL;DR: nothing breaks, nothing is required.** v4 is additive on top of v3.1. Your files keep working exactly as they are; everything below is opt-in, item by item.

## Added in v4

- **Trust-building mode** (the only behavior change, and it's opt-in for existing setups): a `## Trust-building mode` section in your entry file. While active, new `MEMORY.md` entries are proposed at session end — ⏳ pending, dated, sourced — and promoted only after your yes. Built for new installs (default on, expires in two weeks); on an established project you probably don't need it. Take it if you've just reset your memory files or onboarded a new tool.
- **Tool integration cards**: `templates/integrations/` — entry file, gotchas, and a 30-second self-check for Claude Code, Codex, Cursor, GitHub Copilot, OpenHands, and Gemini CLI.
- **GitHub Releases**: from v4 on, every version ships as a Release with migration notes. Watch the repo (Releases only) and you'll know when there's something new.
- This card: `upgrade/` now holds one-page cards between versions.

## Replaced in v4

- Nothing. `health_check.py` and `reconcile.py` are unchanged since v3.1.

## Your move

Two options:

1. Paste the **L2 — Upgrade check** prompt from [PROMPT.md](../PROMPT.md) — it detects v3.x and offers the v4 additions item by item (recommended).
2. Do it by hand: add the `## Trust-building mode` section if you want it (spec in [PROMPT.md](../PROMPT.md), L0 step 1), bump your files' first-line markers to `<!-- wallaby-agent-rules v4 -->`, and glance at your tool's card in [templates/integrations/](../templates/integrations/).

Either way, your content stays yours — that rule has not changed since v1 and won't.
