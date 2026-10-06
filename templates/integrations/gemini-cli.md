<!-- wallaby-agent-rules 1.0.1 -->
# Gemini CLI

- **Entry file**: `GEMINI.md` — Gemini CLI's native context file. Answer "Gemini CLI" in the L1 interview and the system anchors there. (`AGENTS.md` with a one-line pointer from `GEMINI.md` also works if you share the repo with other tools.)
- **Install**: paste either prompt from [PROMPT.md](../../PROMPT.md) into a Gemini CLI session at your project root.
- **Weekly checks**: `python3 scripts/health_check.py` and `python3 scripts/reconcile.py` — plain shell commands, zero dependencies.
- **Closeout**: say "wrap up" (or your ritual words) before ending the session.
- **Gotcha**: multi-tool repo? Keep one memory, one protocol — point `GEMINI.md` at `AGENTS.md` rather than maintaining two copies.
- **30-second self-check**: open a fresh session and ask "what do you remember about this project?" If it quotes `MEMORY.md` and `NOW.md`, you're wired.
