<!-- wallaby-agent-rules 1.0.1 -->
# GitHub Copilot

- **Entry file**: `AGENTS.md` — Copilot reads repository-level `AGENTS.md` natively. If your repo already has `.github/copilot-instructions.md`, that file is honored too; keep memory in one place and let the other file point to it.
- **Install**: paste either prompt from [PROMPT.md](../../PROMPT.md) into Copilot Chat at your project root (agent mode works best, since it writes files).
- **Weekly checks**: `python3 scripts/health_check.py` and `python3 scripts/reconcile.py` — plain shell commands.
- **Closeout**: say "wrap up" (or your ritual words) before ending the session.
- **Gotcha**: organization-level custom instructions (set in GitHub settings) also load — if your org has them, make sure they don't contradict the memory protocol.
- **30-second self-check**: open a fresh Copilot Chat and ask "what do you remember about this project?" If it quotes `MEMORY.md` and `NOW.md`, you're wired.
