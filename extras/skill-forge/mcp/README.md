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
| `skill_forge` | "make this a skill" | routes skill/SOP/combo → derives requirements (asks only what's open and critical) → returns the assembled generation prompt for your AI to execute. `mode="full"` also seeds the failure ledger and embeds a feedback hook in the generated skill. |
| `skill_optimize` | "optimize this skill" | locates the skill → seven machine health checks → failure-ledger history → optimization prompt. Never edits files itself. |
| `skill_feedback` | (called by the agent) | appends one failure record to the ledger, redacted on write. |

## Files

- Failure ledger: `~/.skill-forge/ledger.jsonl` (append-only; schema in `../schema/ledger.md`)
- Skill search paths: `$SKILL_FORGE_DIRS` (os.pathsep-separated) takes priority, then the current directory, `~/.hermes/skills`, `~/.claude/skills`, `~/.config/hermes/skills`

## Verify

```sh
python3 smoke_test.py
```

78 assertions against a live server instance under a temporary HOME — protocol face, both forge stages, the routing lanes, stakes detection, ledger redaction, all seven health checks, idle-ledger warnings, and the maintenance nudge. Your real ledger is never touched.
