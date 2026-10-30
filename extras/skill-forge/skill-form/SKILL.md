---
name: skill-forge
description: Create, stress-test, and maintain agent skills that stop failing the same way twice — requirement derivation, generation spec with a birth certificate, failure ledger, and an optimize loop. Use when the user wants to turn a repeating workflow into a skill, when a skill keeps misfiring, or when they say "make this into a skill" or "this skill broke again".
version: 1.1.0
author: Wallaby Token
license: MIT
metadata:
  hermes:
    tags: [Skills, Agent Workflow, MCP, Prompt Engineering]
---

# Skill Forge

A skill is a living thing: it gets created, it fails, it should learn. This skill runs that lifecycle: derive the requirements, generate to a spec, log every failure, optimize on evidence. The full protocol lives in `references/`; read the file for the stage you are in and follow it exactly.

## When to use

- The user wants to turn a repeating task into a skill or an SOP, or isn't sure which.
- An existing skill misfires, fires wrong, or its output drifted.
- The user says "make this a skill", "optimize this skill", "this skill broke again".

## The flow

1. **Route**: form unclear? Read `references/00-route.md`. Skill vs SOP vs combo, four criteria. If the user named the form, skip this.
2. **Interview**: read `references/10-forge-interview.md` for a skill or `references/11-sop-interview.md` for an SOP. Derive every answer from the description; ask only what is open AND critical, all at once. Confirm anything on the high-stakes checklist with the user — never self-derive those. Produce the structured answers object. Default to `core`; use `core-shell` when you need the same executable core with less surrounding material.
3. **Generate**: read `references/20-generate-skill.md` or `references/21-generate-sop.md` and execute it with the answers filled in. Deliver the skill, one unnumbered feedback footer, and its birth certificate of trigger test pairs.
4. **Optimize**: a week in, or after failures: read `references/30-optimize.md`. Ask the user about recent misfires first, then run the cut / sink / demote / keep substance test and the seven-item health check. Only full flow adds this maintenance rhythm at creation time.

## Red lines for the forge itself

- Never invent failure history. A plausible-looking pitfall that never happened is worse than none.
- Never write input-shape restrictions into a skill's description — routers execute them as do-not-trigger rules.
- Never write blanket shutdown clauses into red lines ("if conditions are not fully met, stop entirely") — strong models execute those as righteous shutdowns.
- Keep the feedback instruction as an unnumbered footer by default. Move it to a numbered step only when the deployer's own real ledger shows a benefit.

## Failure ledger

No server needed: keep `failures.md` next to each skill's `SKILL.md`, one line per failure (date, scene, what broke). For the full schema and redaction rules, read `references/schema-ledger.md`. A ledger that goes quiet for 14 days is a finding, not a comfort; see the idle rule in `references/30-optimize.md`.

## Same protocol, two other forms

- **MCP server** in `../mcp/`: automates the stakes scan, ledger writes with redaction, idle warnings, byte-exact size metering, and the health-check report.
- **Prompt pack** in `../prompt-pack/`: the same files as `references/`, for copy-paste into any agent conversation.
