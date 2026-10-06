<!-- wallaby-agent-rules 1.0.1 -->
# Claude Code

- **Entry file**: `CLAUDE.md`. Answer "Claude Code" in the L1 interview and everything anchors there — the file Claude Code reads at every session start. `/memory` opens it for quick edits.
- **Install**: paste either prompt from [PROMPT.md](../../PROMPT.md) into a Claude Code session at your project root. With web access on, Claude Code can also fetch the prompt URL itself.
- **Weekly checks**: `python3 scripts/health_check.py` and `python3 scripts/reconcile.py` run as plain shell commands. No MCP server, no plugin, nothing to install.
- **Closeout**: say "wrap up" (or your own ritual words) before closing a session, and Claude Code triages what the session produced into memory, the dated log, or the bin.
- **Gotcha**: if your project already has a `CLAUDE.md`, the install merges into it — your existing content is never overwritten.
- **30-second self-check**: start a new session and ask "what do you remember about this project?" If the answer quotes `MEMORY.md` and `NOW.md`, the entry file is wired.
