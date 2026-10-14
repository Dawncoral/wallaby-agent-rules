# Skill Forge

**Skills that failed you once shouldn't fail you the same way twice.**

Skill Forge runs the part of a skill's life that starts after creation: requirement derivation with a high-stakes checklist, generation to a measured spec, a failure ledger that the skill itself writes to, and an optimize loop driven by that evidence. It is an analyst, not a generator: the server does only deterministic work (scaffolds, checks, bookkeeping); the writing belongs to your AI.

Anthropic's skill-creator writes the birth certificate. Skill Forge runs the hospital: checkups, medical records, follow-up visits. The two are complementary — a skill born from skill-creator is exactly what the forge's health checks and ledger serve.

## Three forms, one protocol

| Form | Directory | Install | What you get |
|---|---|---|---|
| MCP server | `mcp/` | one stdio entry | everything automated: stakes scan, ledger writes with redaction, idle warnings, byte-exact size checks, seven-item health reports |
| Prompt pack | `prompt-pack/` | none; paste into any agent chat | the full protocol as Markdown; the five automations become manual checklists |
| Skill form | `skill-form/` | drop into any SKILL.md-compatible tool | the protocol as a loadable skill for Hermes and friends |

The protocol is identical across forms. `skill-form/references/` is generated from `prompt-pack/` at release time by `sync_skill_form.sh` — one source, no drift.

## Quickstart (MCP)

Zero dependencies, Python 3 standard library only. Add to any MCP client that speaks stdio:

```json
{
  "mcpServers": {
    "skill-forge": {
      "command": "python3",
      "args": ["/absolute/path/to/mcp/wallaby_skill_forge_mcp.py"]
    }
  }
}
```

Then three tools are available: `skill_forge` for creating a skill (say "make this a skill"), `skill_optimize` for optimizing one, and `skill_feedback`, which the agent calls when a skill fails. The failure ledger lives at `~/.skill-forge/ledger.jsonl`; extra search directories go in `SKILL_FORGE_DIRS`. Details: `mcp/README.md`.

Verify your copy before trusting it:

```sh
python3 mcp/smoke_test.py   # 78 assertions against a live server instance
```

## Evidence

Every behavioral claim above was measured on real models, and the full write-ups are public:

- We pre-registered the rule that would kill our own hypothesis, [and it fired](https://wallabytoken.com/blog/p/skill-forge-kill-rule-falsified). Trigger accuracy: one-shot 98.3% vs forge 91.7% — Wilson intervals overlap; no significant win at the routing layer. The same experiment surfaced the finding that mattered: embedded feedback hooks went 0/20 across models until we moved failure-logging into the task flow as a numbered step.
- [Same skill, opposite effects.](https://wallabytoken.com/blog/p/skill-engineering-three-regimes) Scaffolding lifted a weaker model's execution quality 0.88 → 2.0 (four dimensions, all up). On hard, fuzzy tasks it pushed a strong model into overcautious shutdowns — four dimensions, all down.
- [The 6KB line.](https://wallabytoken.com/blog/p/skill-file-size-6kb-limit) Empty-response rates by skill-file size: 0/8 under 6KB, ~25% at 6–9KB, ~50% at ≥9KB for naturally bloated files.

## Honest limits

- Skill Forge makes quality requirements consistent across models; it does not make models equally capable of meeting them.
- The generation/rewrite semantics still depend on the executing model: a weak model may not honor a long spec, and no scaffolding removes that.
- On hard tasks with fuzzy boundaries, thick constraints measurably hurt strong models in the current form. The form router steers those to `shell` for this reason.
- Sample sizes are small, n=10–20 per arm; we publish Wilson intervals with the numbers and treat near-ties as noise.

## License

MIT + Commons Clause; see the repository root. Free for personal projects, research, and use inside your own organization — selling needs a commercial license.
