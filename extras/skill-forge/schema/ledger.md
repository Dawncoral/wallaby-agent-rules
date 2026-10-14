# Failure ledger schema

Skill Forge's memory: every failure a skill ever caused, one JSON object per line.

- **MCP version**: `~/.skill-forge/ledger.jsonl` (written by the `skill_feedback` tool, redacted on write)
- **Prompt-pack version**: `failures.md` next to the skill's `SKILL.md`, or a `ledger.jsonl` you maintain yourself — same fields

## Fields

| Field | Values | Meaning |
|---|---|---|
| `date` | ISO date, e.g. `2026-10-14` | When it happened |
| `skill` | skill name | Which skill failed |
| `scene` | one line | What you were trying to do |
| `failure` | one line | How it failed |
| `severity` | `low` / `mid` / `high` (default `mid`) | How much it hurt |
| `source` | `feedback` / `optimize` / … | Where the record came from |
| `domain` | free text, e.g. `governance`, `personal` | Scene domain, for distribution analysis |
| `attribution` | `route` / `content` / `boundary` / `unknown` | `route` = fired wrong or didn't fire → fix the description. `content` = fired but done badly → fix the body. `boundary` = verdict-line problem. `unknown` = default |

## Example

```jsonl
{"date":"2026-10-14","skill":"invoice-extract","scene":"monthly batch of 30 PDFs","failure":"guessed the tax field on two invoices","severity":"high","source":"feedback","domain":"personal","attribution":"content"}
{"date":"2026-10-14","skill":"deploy-preflight","scene":"Friday release","failure":"did not fire when user said 'ship it'","severity":"mid","source":"feedback","domain":"governance","attribution":"route"}
```

## Redaction rules

The MCP server applies these before writing. Maintaining a ledger by hand, do the same:

1. API keys (`sk-…`) → `[REDACTED_KEY]`
2. Bearer tokens → `[REDACTED_TOKEN]`
3. `token:`/`password:`/`secret:` assignments → `name=[REDACTED]`
4. Email addresses → `[REDACTED_EMAIL]`
5. Full IPv4 addresses → `[REDACTED_IP]`
6. Home-directory usernames (`/Users/alice/`) → `~/`

## The idle rule

A ledger with history but nothing new in 14 days means one of two things: nothing failed, or nobody is recording. The handling lives in `../prompt-pack/30-optimize.md` — observational capture, then a one-month re-check of triggers and the feedback hook.
