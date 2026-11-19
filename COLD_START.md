<!-- wallaby-agent-rules 1.4.5 -->
# COLD_START.md — superseded by PROMPT.md

This file is kept so existing links do not break. Its content has been replaced by **[PROMPT.md](PROMPT.md)**, which covers the same ground and more:

- New project, zero setup → use the **L0 — One-click install** section.
- New project, tuned to you → use the **L1 — 9-question interview** section.
- Already running an earlier setup → use the **L2 — Upgrade check** section; it migrates incrementally and never overwrites your content.
- Daily closeout → use the **L3 — Closeout ritual** section to update memory and check drift.

The current set has four prompts: L0, L1, L2, and L3. The governance file layout uses plain-named templates (`MEMORY.md` / `NOW.md` / `INDEX.md` / `LOG.md` in [`templates/`](templates/)), and the weekly reconciliation is a zero-dependency script ([`templates/health_check.py`](templates/health_check.py)). Details and migration notes: [CHANGELOG.md](CHANGELOG.md).
