<!-- wallaby-agent-rules 1.0.1 -->
# Codex

- **Entry file**: `AGENTS.md` — Codex's native convention, read at every session start. The default L0 install already targets it.
- **Install**: paste either prompt from [PROMPT.md](../../PROMPT.md) into a Codex session at your project root, or point Codex at the prompt URL and tell it to follow the section you picked.
- **Weekly checks**: `python3 scripts/health_check.py` and `python3 scripts/reconcile.py` run as plain shell commands, zero dependencies.
- **Closeout**: say "wrap up" before ending the session; the ritual triages the session's output into memory, the dated log, or the bin.
- **Gotcha**: `AGENTS.md` is shared by many tools — if several tools work in this repo, one entry file serves all of them. Don't split per tool.
- **30-second self-check**: open a fresh session and ask "what do you remember about this project?" If it quotes `MEMORY.md` and `NOW.md`, you're wired.
