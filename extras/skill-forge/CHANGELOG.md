# Changelog — Skill Forge

## 1.0.0 — 2026-10-14

First public release. Three forms of one protocol:

- `mcp/` — the MCP server (`skill_forge` / `skill_optimize` / `skill_feedback`), zero dependencies, with a 78-assertion smoke suite.
- `prompt-pack/` — the same protocol as paste-ready Markdown, no install.
- `skill-form/` — the protocol as a SKILL.md-compatible skill; `references/` is generated from `prompt-pack/` by `sync_skill_form.sh`.
- `schema/ledger.md` — the failure-ledger format and redaction rules.
