<!-- wallaby-agent-rules v2 -->
# COLD_START.md — superseded by PROMPT.md

This file is kept so existing links do not break. Its content has been replaced by **[PROMPT.md](PROMPT.md)**, which covers the same ground and more:

- New project, zero setup → use the **L0 — One-click install** section.
- New project, tuned to you → use the **L1 — 6-question interview** section.
- Already running the v1 cold-start setup → use the **L2 — Upgrade check** section; it migrates incrementally and never overwrites your content.

What changed in v2: the single cold-start prompt became three paste-in prompts, the governance file layout became plain-named templates (`MEMORY.md` / `NOW.md` / `INDEX.md` / `LOG.md` in [`templates/`](templates/)), and the weekly reconciliation is now a zero-dependency script ([`templates/health_check.py`](templates/health_check.py)). Details and migration notes: [CHANGELOG.md](CHANGELOG.md).
