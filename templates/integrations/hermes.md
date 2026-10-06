<!-- wallaby-agent-rules 1.2.0 -->
# Hermes Agent

- **Entry file**: `AGENTS.md`. At session start Hermes scans `.hermes.md` → `AGENTS.md` → `CLAUDE.md` → `.cursorrules` and loads the first match. Inside a git repository it chains `AGENTS.md` files from the git root down to your working directory, so a repo-root file and a package-level file stack instead of competing.
- **Install**: paste either prompt from [PROMPT.md](../../PROMPT.md) into a Hermes session at your project root. Or install the skill and ask Hermes to set the system up: `hermes skills install Dawncoral/wallaby-agent-rules/skills/agent-memory-rules`.
- **Weekly checks**: `python3 scripts/health_check.py` and `python3 scripts/reconcile.py` run as plain shell commands, zero dependencies.
- **Closeout**: say "wrap up" before ending the session; the ritual triages the session's output into memory, the dated log, or the bin.
- **Gotcha 1**: Hermes injects the entry file, not `MEMORY.md` — the memory-protocol rule in the entry file is what pulls memory into each session. Verified on Hermes v0.21.5: with both files present, only `AGENTS.md` was loaded automatically.
- **Gotcha 2**: every context file passes a prompt-injection scan before loading. Content that reads like injected instructions ("ignore all previous instructions", credential exfiltration) is replaced by a `[BLOCKED: ...]` marker and never reaches the model — keep the entry file plain and it sails through.
- **Gotcha 3**: oversized context files are truncated head/tail with a marker. The cap scales with the model's context window (6% of the window, 20K chars floor, `context_file_max_chars` in config.yaml overrides). Keep the entry file lean and this never fires.
- **30-second self-check**: start a new session and ask "what do you remember about this project?" If the answer quotes `MEMORY.md` and `NOW.md`, the entry file is wired.
