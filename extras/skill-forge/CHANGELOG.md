# Changelog — Skill Forge

## 1.1.0 — 2026-10-30

- Add `core` as the default generated-skill form and `core-shell` as a lean form that still keeps executable steps, concrete red lines, and key completion criteria. Keep `single`, `layered`, `shell`, full mode, and combo's pointer-only shell behavior.
- Keep one unnumbered feedback footer in standalone and full. Recommend a numbered step only when the deployer's own real ledger shows a benefit; P1 did not reproduce a step-only advantage, and P1/P2 are not treated as cross-model laws.
- Limit maintenance rituals and the optimize rhythm to full mode. Make pitfall placeholders optional rather than penalizing core files that omit them.
- Downgrade the 6KB/9KB checks to weaker-model/short-context heuristics. Use `layered` only for an explicit context budget, observed empty/truncated responses or cost anomalies, or naturally on-demand content.
- Synchronize the MCP, prompt pack, and skill form. Expand the offline smoke suite from 78 to 89 assertions; no new MCP tools, model benchmark, or production execution-logging pipeline.

## 1.0.0 — 2026-10-14

First public release. Three forms of one protocol:

- `mcp/` — the MCP server (`skill_forge` / `skill_optimize` / `skill_feedback`), zero dependencies, with a 78-assertion smoke suite.
- `prompt-pack/` — the same protocol as paste-ready Markdown, no install.
- `skill-form/` — the protocol as a SKILL.md-compatible skill; `references/` is generated from `prompt-pack/` by `sync_skill_form.sh`.
- `schema/ledger.md` — the failure-ledger format and redaction rules.
