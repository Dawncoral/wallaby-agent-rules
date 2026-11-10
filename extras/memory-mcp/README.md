<!-- wallaby-agent-rules 1.4.3 -->
# Memory MCP

**A second door to the same files.** Your memory stays in `MEMORY.md`, `NOW.md`, `INDEX.md`, and `LOG.md`, read through the entry file. This optional server opens those files to agents that never load the entry file, such as an agent started by a workbench or a remote runner. It keeps no store, cache, or index of its own.

One Python file, standard library only, MCP over stdio. Server version 0.4.0.

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
| `memory_locate` | check INDEX.md first | Returns the `INDEX.md` rows that match, including rows in the `INDEX/` parts it points to. It never guesses a path. |
| `memory_propose` | trust-building | Queues a dated fact in `PROPOSALS.md`. A source is required. It never writes `MEMORY.md`; a person promotes it. |
| `memory_note` | "note this" | Adds one dated line at the top of this month in `LOG.md`. |
| `memory_now` | tracked work moved | Adds one dated line under `## In flight` in `NOW.md`. A pointer is required. |
| `memory_check` | weekly checks | Runs `scripts/health_check.py` and `scripts/reconcile.py` when they exist. |
| `memory_status` | upgrades | Reports the file version, counts, and the memory budget, and says when an upgrade is due. |
| `memory_lookup` | search before building | With `registry: capability`, returns rows of `CAPABILITIES.md`; with `registry: map`, rows of `MAP.md`. Every query word must appear in the row. It also takes `status`, `limit`, and `detail`. Read-only. |
| `memory_route` | before and after a change | Returns the route card as JSON: capabilities to reuse, files to register, map components, events and surfaces, the tier, and the premises the changed paths depend on. About 2 KB. Read-only. |

`memory_lookup` and `memory_route` run the governance CLI with `--json` and return its output; they hold no logic of their own. They prefer `scripts/memory_governance.py` 1.4.3 or newer under the root and fall back to the copy in `extras/memory-governance/` beside this server. Without either, they say how to install it.

Every write is redacted first: API keys, bearer tokens, `token=` and `password=` values, emails, IPv4 addresses, and home-directory user names.

In a project with a `.memory/` directory, `memory_propose`, `memory_note`, and `memory_now` go through the governance CLI's `write` command. The CLI checks the line, puts it in the right place, and records the write in `.memory/events.jsonl` under the name your MCP client sends when it connects. In a project without `.memory/`, the three tools write the files themselves and create nothing else.

## Versions

Each core file carries a first-line marker such as `<!-- wallaby-agent-rules 1.0.1 -->`, and the marker changes only when that file changes. In 1.4.3 the newest core-file marker is still 1.0.1. `memory_status` compares your files against that format, not against the release number. A current install gets no upgrade hint. An install with a pre-1.0 marker (`v1` to `v4.1`) is sent to the L2 upgrade check in [PROMPT.md](../../PROMPT.md), which never overwrites your content.

Agents bind to the nine tool names, not to the file layout. If the files change shape in a later release, you update this server and leave agent configs alone.

## Verify

```sh
python3 smoke_test.py   # 38 checks against a live server on a temporary project
```
