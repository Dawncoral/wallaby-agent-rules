<!-- wallaby-agent-rules 1.4.5 -->
# Clients: the memory MCP entry

The memory files are the integration: an agent that reads `AGENTS.md` (or
`CLAUDE.md`, `GEMINI.md`, `.cursorrules`) needs no MCP server. The optional
`wallaby-memory` MCP server is for clients that cannot load an entry file, or
that want the read, locate, and propose tools in their tool list.

## Generate the entry

```bash
python3 extras/memory-governance/quickstart.py --target /path/to/project mcp-config --print
```

The command prints one JSON object on stdout and writes nothing:

```json
{
  "mcpServers": {
    "wallaby-memory": {
      "command": "/usr/bin/python3",
      "args": [
        "/path/to/wallaby-agent-rules/extras/memory-mcp/wallaby_memory_mcp.py",
        "--root",
        "/path/to/project"
      ]
    }
  }
}
```

`command` is the absolute path of the Python that ran quickstart. `args` holds
the absolute path of the Memory MCP server, `--root`, and the absolute target
path. Paths with spaces or non-ASCII characters need no escaping inside JSON.

## Merge, do not replace

Open the client's configuration and add the `wallaby-memory` key to the
existing `mcpServers` object. Keep every other server entry as it is. Replacing
the whole file would drop the other servers.

| Client | Where the `mcpServers` object usually lives |
|---|---|
| Claude Code | The project or user MCP configuration for the client |
| Claude Desktop | `claude_desktop_config.json` |
| Cursor | `.cursor/mcp.json` (project) or the user MCP file |
| Gemini CLI | The client's MCP settings file |
| Codex and other CLI agents | The client's own MCP configuration |

These locations change between client releases. The command that matters is
the one above; it prints the entry, and a person merges it. `quickstart` does
not scan, discover, or edit any client file, and has no `--write` mode.

## Verify

1. Restart the client so it starts the new server.
2. Ask the agent to call `memory_read`. It should return `MEMORY.md`, `NOW.md`,
   and a short status block.
3. If the tool is missing, check the client's log for the process failing to
   start, then run `command args...` by hand. `python3
   extras/memory-mcp/wallaby_memory_mcp.py --root /path/to/project --version`
   should print one line and exit 0.

## Notes

- The server reads only the project memory files. It does not need a network
  connection, an API key, or a model.
- The three write tools (`memory_propose`, `memory_note`, `memory_now`) go
  through the governance CLI when the project has `.memory/`, so each write is
  checked and recorded. Proposals still wait for a person in `PROPOSALS.md`.
- `--tools memory_locate` limits the tool list, for a workbench that should
  only look things up.
- The server's version and the installed memory files' version are reported
  separately by `memory_status`. Update the server by replacing
  `wallaby_memory_mcp.py`; the tool names do not change.
- Never put a credential in `MEMORY.md`, `NOW.md`, `LOG.md`, or a client
  configuration. `.credentials/` is skipped by quickstart and by the weekly
  checks; that is a convention, not a place to store a token in a client file.
