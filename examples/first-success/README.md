<!-- wallaby-agent-rules 1.0.1 -->
# First success - a fictional project

This tree is a small, entirely fictional project that already has the memory
files and two documents. `quickstart.py demo` copies it into a system temporary
directory, runs the real `init` on the copy, and walks the first success:

1. `memory_locate` finds the export-format decision through `INDEX.md`.
2. The demo reads the decision from `docs/export-decision.md`.
3. `LOG.md` says the field runbook is done while `NOW.md` still lists it in
   flight. `reconcile.py` exits 1, which is the contradiction the demo shows.
4. The demo removes that one line from the temporary `NOW.md`. `reconcile.py`,
   `health_check.py`, and the governance `doctor` then exit 0.
5. The last line is `Doctor: PASS`.

The two dates in this tree are placeholders: `2026-01-05` becomes yesterday and
`2026-01-06` becomes today in the temporary copy, so the example does not go
stale. The tree in the repository is never modified.

Every name, decision, path, and ticket here is invented. Do not use it as a
template for a real project; use `quickstart.py init` for that.

## Run it

From a full clone of `wallaby-agent-rules`:

```bash
python3 extras/memory-governance/quickstart.py demo
```

No model, API key, network, or git repository is needed. The expected output is
in [`expected/demo.txt`](expected/demo.txt).
