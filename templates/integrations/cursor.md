<!-- wallaby-agent-rules v4 -->
# Cursor

- **Entry file**: `AGENTS.md` — Cursor reads it natively. (Older setups used `.cursorrules` or `.cursor/rules/`; the L1 interview covers those too, but prefer the single `AGENTS.md`.)
- **Install**: paste either prompt from [PROMPT.md](../../PROMPT.md) into Cursor's agent chat at your project root.
- **Weekly checks**: `python3 scripts/health_check.py` and `python3 scripts/reconcile.py` — plain shell commands, no extension needed.
- **Closeout**: say "wrap up" (or your ritual words) before you close the chat.
- **Gotcha**: don't split memory across `.cursor/rules/*` files — rules files are for behavior, memory belongs in one dated, sourced place. One entry file, one memory.
- **30-second self-check**: open a new chat and ask "what do you remember about this project?" If it quotes `MEMORY.md` and `NOW.md`, you're wired.
