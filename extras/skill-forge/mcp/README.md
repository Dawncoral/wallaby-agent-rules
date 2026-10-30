# Skill Forge MCP server

Zero-dependency MCP server (Python 3 standard library only), JSON-RPC 2.0 over stdio.

## Install

Point any stdio-capable MCP client at the script:

```json
{
  "mcpServers": {
    "skill-forge": {
      "command": "python3",
      "args": ["/absolute/path/to/wallaby_skill_forge_mcp.py"]
    }
  }
}
```

- **Claude Code**: `claude mcp add skill-forge -- python3 /absolute/path/to/wallaby_skill_forge_mcp.py`
- **Hermes** and other clients: same shape — command `python3`, one arg, the absolute path.

## Tools

| Tool | Say | What happens |
|---|---|---|
| `skill_forge` | "make this a skill" | routes skill/SOP/combo → derives requirements (asks only what's open and critical) → returns the assembled generation prompt for your AI to execute. `core` is the default; both modes keep one feedback footer. `mode="full"` also seeds the failure ledger and adds the maintenance/optimize rhythm. |
| `skill_optimize` | "optimize this skill" | locates the skill → seven machine health checks → failure-ledger history → optimization prompt. Never edits files itself. |
| `skill_feedback` | (called by the agent) | appends one failure record to the ledger, redacted on write. |

## Generated skill forms

- `core` (default): description, project facts, the shortest executable steps, concrete red lines, and key completion criteria in one file.
- `core-shell`: the same executable core with less surrounding material. It still contains steps, red lines, and criteria; it is not pointer-only.
- `single`, `layered`, and `shell`: kept for compatibility. `combo` still forces the legacy pointer-only `shell` alongside an SOP.
- `layered` is for an explicit context budget, observed empty/truncated responses or cost anomalies, or naturally on-demand content. The 6KB mark is a weaker-model/short-context heuristic, not an automatic trigger.

Keep the feedback instruction as one unnumbered footer. Move it to a numbered step only when your own real ledger shows a benefit; otherwise use footer/auto. P1 did not reproduce a step-only advantage, but it did not prove position universally irrelevant.

## Files

- Failure ledger: `~/.skill-forge/ledger.jsonl` (append-only; schema in `../schema/ledger.md`)
- Skill search paths: `$SKILL_FORGE_DIRS` (os.pathsep-separated) takes priority, then the current directory, `~/.hermes/skills`, `~/.claude/skills`, `~/.config/hermes/skills`

## Evaluation evidence

See [Evidence](../README.md#evidence) for the existing experiment assets and their limits. Feedback-placement research belongs in the existing P0/P1 evaluation harness and its per-run ledgers; this server does not add a production execution-logging pipeline.

## Verify

```sh
python3 smoke_test.py
```

89 assertions against a live server instance under a temporary HOME — protocol face, both forge stages, core defaults and legacy forms, footer placement, size heuristics, routing lanes, stakes detection, ledger redaction, all seven health checks, idle-ledger warnings, and the maintenance nudge. Your real ledger is never touched.
