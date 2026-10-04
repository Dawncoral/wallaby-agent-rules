<!-- wallaby-agent-rules 1.0.0 -->
# OpenHands

- **Entry file**: `AGENTS.md` — OpenHands's system prompt natively instructs the agent to read and maintain the repository-root `AGENTS.md`. This system is the closest fit of any tool here: the slot is official.
- **Install**: paste either prompt from [PROMPT.md](../../PROMPT.md) into an OpenHands session with your project mounted as the workspace.
- **Weekly checks**: `python3 scripts/health_check.py` and `python3 scripts/reconcile.py` — plain shell commands, zero dependencies.
- **Closeout**: say "wrap up" (or your ritual words) before ending the session; the closeout ritual also works well as a scheduled automation task.
- **Gotcha**: if you run OpenHands with a remote backend, make sure the workspace it mounts is the same project directory that holds your memory files — memory lives with the project, not with the frontend.
- **30-second self-check**: start a new session and ask "what do you remember about this project?" If it quotes `MEMORY.md` and `NOW.md`, you're wired.
