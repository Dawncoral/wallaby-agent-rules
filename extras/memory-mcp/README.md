<!-- wallaby-agent-rules 1.4.3 -->
# Memory MCP

**A second door to the same files.** Your memory stays in `MEMORY.md`, `NOW.md`, `INDEX.md`, and `LOG.md`, read through the entry file. This optional server opens those files to agents that never load the entry file, such as an agent started by a workbench or a remote runner. It keeps no store, cache, or index of its own.

One Python file, standard library only, MCP over stdio. Server version 0.2.0.

## Install

```json
{
  "mcpServers": {
    "wallaby-memory": {
      "command": "python3",
      "args": ["/absolute/path/to/extras/memory-mcp/wallaby_memory_mcp.py", "--root", "/path/to/your-project"]
    }
  }
}
```

Claude Code: `claude mcp add wallaby-memory -- python3 /abs/path/wallaby_memory_mcp.py --root /path/to/your-project`. Other clients that launch stdio servers take the same command and arguments.

| Option | Effect |
|---|---|
| `--root PATH` | Project folder with the memory files. Falls back to `$WALLABY_MEMORY_ROOT`, then the current directory. |
| `--tools a,b` | Expose only these tools. A workbench that writes its own log can run `--tools memory_read,memory_locate,memory_propose`. |
| `--origin ID` | Tag every proposal with the work that made it, for example a task id. Falls back to `$WALLABY_MEMORY_ORIGIN`. |

## Tools

| Tool | Protocol step | What it does |
|---|---|---|
| `memory_read` | session start | Returns `MEMORY.md` and `NOW.md`, the file version, and the conflict rule: files beat memory, memory beats inference. |
| `memory_locate` | check INDEX.md first | Returns the `INDEX.md` rows that match. It never guesses a path. |
| `memory_propose` | trust-building | Queues a dated fact in `PROPOSALS.md`. A source is required. It never writes `MEMORY.md`; a person promotes it. |
| `memory_note` | "note this" | Adds one dated line at the top of this month in `LOG.md`. |
| `memory_now` | tracked work moved | Adds one dated line under `## In flight` in `NOW.md`. A pointer is required. |
| `memory_check` | weekly checks | Runs `scripts/health_check.py` and `scripts/reconcile.py` when they exist. |
| `memory_status` | upgrades | Reports the file version, counts, and the memory budget, and says when an upgrade is due. |

Every write is redacted first: API keys, bearer tokens, `token=` and `password=` values, emails, IPv4 addresses, and home-directory user names.

## Versions

Each core file carries a first-line marker such as `<!-- wallaby-agent-rules 1.0.1 -->`, and the marker changes only when that file changes. In 1.4.3 the newest core-file marker is still 1.0.1. `memory_status` compares your files against that format, not against the release number. A current install gets no upgrade hint. An install with a pre-1.0 marker (`v1` to `v4.1`) is sent to the L2 upgrade check in [PROMPT.md](../../PROMPT.md), which never overwrites your content.

Agents bind to the seven tool names, not to the file layout. If the files change shape in a later release, you update this server and leave agent configs alone.

## Verify

```sh
python3 smoke_test.py   # 24 checks against a live server on a temporary project
```
