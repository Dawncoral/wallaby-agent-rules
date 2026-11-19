<!-- wallaby-agent-rules 1.4.5 -->
# Troubleshooting the first success

`quickstart.py` reports a failure as four lines: the stage, the file, the
detail, and a next command. It returns 2 for `init` and `mcp-config` failures,
and 1 for a failed `demo`. It never prints a traceback for an expected failure.

## `init` fails at `preflight`

```
quickstart: FAILED
  stage: preflight
  file: .../templates/health_check.py
  detail: missing source health_check; quickstart must run from a full wallaby-agent-rules clone
  next: clone the repository again and run python3 extras/memory-governance/quickstart.py init
```

`quickstart.py` looks for `memory_governance.py` beside itself and for
`templates/health_check.py`, `templates/reconcile.py`, `templates/NOW.md`,
`templates/LOG.md`, and `templates/INDEX.md` in the repository root. A copy of
`quickstart.py` alone cannot initialize a project. Use a full clone.

## `init` fails at `write`, `mkdir`, or `path`

- `write` or `mkdir`: the target is not writable, or a file is in the way of a
  directory. Fix the permission or move the file and run `init` again. New
  files are created exclusively, so a failed run is safe to repeat.
- `path`: a symlink inside the target would lead outside it, or a path would
  escape the target. `quickstart` refuses to follow it. Remove the symlink and
  run again.

## `init` says `KEEP` for a file I expected it to change

That is the contract. `init` never overwrites, merges, or repairs an existing
file. If an existing `INDEX.md` is missing a new file, add the row by hand; if
an existing `LOG.md` has no initialization line, that is fine. The command's job
is to add what is missing, not to rewrite history.

## `demo` fails at a step

The stage tells you where it stopped. The temporary copy is removed after the
run, so reproduce by copying the example yourself:

```bash
cp -R examples/first-success /tmp/first-success
python3 extras/memory-governance/quickstart.py --target /tmp/first-success init
```

| Stage | Usual cause | What to run |
|---|---|---|
| `step 2 locate` | The Memory MCP server is missing or cannot start | `python3 extras/memory-mcp/wallaby_memory_mcp.py --root /tmp/first-success --version` |
| `step 3 decision` | The INDEX row no longer points at `docs/export-decision.md`, or the `Decision:` line is gone | Check `examples/first-success/INDEX.md` and `docs/export-decision.md` |
| `step 4 contradiction` | The runbook lines in the example were edited | Restore `NOW.md` and `LOG.md` from git |
| `step 5 reconcile` | `reconcile.py` did not exit 1 before the fix | Run `python3 /tmp/first-success/scripts/reconcile.py /tmp/first-success` and read its output |
| `step 7 ...` | One of the three checks found a real problem | Run that check by hand; the message names the exit code and its last line |

`demo` requires `Doctor: PASS` on the last line. If a check fails, the last
line is `Doctor: FAIL` and the exit code is 1.

## `doctor` exits 1 or 2 after `init`

Run the two weekly scripts directly; their output names the finding:

```bash
python3 scripts/health_check.py
python3 scripts/reconcile.py
```

- `health_check.py` exits 1 for stray root files, unregistered `.md` files,
  stale `NOW.md` lines, broken `INDEX.md` rows, oversized entry files, undated
  `MEMORY.md` lines, a memory budget overflow, apparent secrets, or a commit
  newer than the newest dated entry.
- `reconcile.py` exits 1 when `LOG.md` claims something is done while `NOW.md`
  still lists it in flight, or when a done entry has no path, ticket, or link.
- `doctor` exits 2 for a failing P0 premise or a governance configuration
  error; P1 findings exit 1. `DOCTOR OK` and exit 0 mean the governance checks
  passed.

`init` creates a minimal `README.md` only when none exists; an existing README
is kept byte for byte. Keep your README. If you later remove it, `P-001 P2
FAILING: missing README.md` reports the missing onboarding entry, so a fresh
session loses its starting point. That premise is P2 and does not change the
doctor exit code. Restore a README to clear the finding.

## Windows

- Run the commands with `python` from the same interpreter you will use later.
  `quickstart` calls subprocesses with `sys.executable`, not a bare `python`.
- Child processes are started with UTF-8 output (`PYTHONIOENCODING=utf-8`), so
  the demo's `Doctor: PASS` is not lost to a console code page.
- Paths with spaces or non-ASCII characters are supported. Put the path in
  quotes in the shell; inside the JSON from `mcp-config --print` it is a single
  string and needs no extra escaping.
- `init` does not create a git repository and does not need git installed.

## The MCP server does not appear in the client

1. Check that you merged only the `wallaby-memory` key; a replaced
   `mcpServers` object drops the other servers.
2. Run the printed `command` and `args` by hand. Add `--version`; it should
   print a line and exit 0.
3. Restart the client. A client that was already running does not pick up a new
   server entry.
4. Make sure `--root` points at the project that holds `MEMORY.md`, `NOW.md`,
   `INDEX.md`, and `LOG.md`.

## A `.credentials/` file appears in `INDEX.md`

It should not: `quickstart` skips `.credentials/`, `.env*`, and `.git/` when it
builds `INDEX.md`, and the weekly checks skip `.credentials/` when they scan.
An existing `INDEX.md` is kept as it is, so a row added by hand stays until a
person removes it. Remove the row by hand; `init` will not edit an existing
index.

## `GEMINI.md` entries

`GEMINI.md` is supported. Both health-check copies include it in their root whitelists and entry-file lists, so a `.gemini/` target can finish `init`, `demo`, and `doctor` without a false stray-root warning.

No special case needed.
