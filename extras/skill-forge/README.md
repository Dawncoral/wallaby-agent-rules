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

## Generated skill forms

`core` is the default: description, project facts, the shortest executable steps, concrete red lines, and key completion criteria in one file. `core-shell` keeps that executable core with less surrounding material; it is not a pointer-only shell. The legacy `single`, `layered`, and `shell` forms remain, and `combo` still uses its pointer-only `shell` alongside an SOP.

Only full mode adds the maintenance and optimize rhythm. Both standalone and full keep one unnumbered feedback footer. Move it to a numbered step only when your own real ledger shows a benefit.

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
python3 mcp/smoke_test.py   # 89 assertions against a live server instance
```

## Evidence

Behavioral claims below belong to their experiment setups. The design defaults above are not cross-model laws.

- We pre-registered the rule that would kill our own hypothesis, [and it fired](https://wallabytoken.com/blog/p/skill-forge-kill-rule-falsified). Trigger accuracy: one-shot 98.3% vs forge 91.7% — Wilson intervals overlap; no significant win at the routing layer.
- A later P1 experiment used real `skill_feedback` ledgers across 240 executions. The baseline without the instruction in the skill produced 0–5% valid calls; footer, section, and step placements were at or near the ceiling. Step did not show a reliable advantage over footer. A shared tool prompt and fixed arm order limit generalization, so this does not prove position universally irrelevant.
- [Same skill, opposite effects](https://wallabytoken.com/blog/p/skill-engineering-three-regimes) was an earlier small-sample result. P2 later ran 180 executions plus 180 judged executions under a shared anti-shutdown prompt and did not reproduce a full-vs-shell difference on its main metric. Its shell still kept task steps, concrete red lines, safety constraints, and completion criteria; do not generalize that result to pointer-only files or other environments.
- [The 6KB results](https://wallabytoken.com/blog/p/skill-file-size-6kb-limit) came from weaker-model/short-context samples: 0/8 empty responses under 6KB, ~25% at 6–9KB, and ~50% at ≥9KB for naturally bloated files. They are heuristic warnings, not an automatic `layered` rule. Layer for an explicit context budget, observed empty/truncated responses or cost anomalies, or naturally on-demand content.

## Honest limits

- Skill Forge makes quality requirements consistent across models; it does not make models equally capable of meeting them.
- The generation/rewrite semantics still depend on the executing model: a weak model may not honor a long spec, and no scaffolding removes that.
- P1 and P2 bound their claims to shared prompts, small task sets, and the tested models. Neither a missing difference nor an early positive result becomes a universal rule.
- Evaluation uses the existing P0/P1 harness and per-run ledgers. The MCP does not add a production execution-logging pipeline; see `mcp/README.md#evaluation-evidence`.

## License

MIT + Commons Clause; see the repository root. Free for personal projects, research, and use inside your own organization — selling needs a commercial license.
