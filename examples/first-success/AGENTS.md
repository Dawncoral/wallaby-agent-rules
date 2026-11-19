<!-- wallaby-agent-rules 1.0.1 -->
# Harbor Exports - how to work in this project

> This is a fictional project. It exists so `quickstart.py demo` can show the
> first success without a model, an API key, or a network connection.

## Start here

1. Read `MEMORY.md` and `NOW.md` before taking work. `MEMORY.md` holds permanent
   facts and rules; `NOW.md` holds what is in flight right now.
2. Look in `INDEX.md` before searching. Register every new file there the moment
   it is created.
3. Append one dated line to `LOG.md` when something ships, changes, or is decided.

Conflict order: what these files say > what you remember > what you infer.
On a conflict, follow the file and tell the user.

## Closeout

- Take finished work out of `NOW.md`'s In flight section, and write the dated
  `LOG.md` line in the same action.
- Run `python3 scripts/reconcile.py` and `python3 scripts/health_check.py`.

## Verify

- One canonical check: `python3 scripts/health_check.py`.
