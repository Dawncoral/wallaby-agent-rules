<!-- wallaby-agent-rules 1.4.0 -->
# Memory governance: from a change to a verified update

One Python CLI connects four jobs that are often skipped: impact mapping, premise checks, contradiction history, and verification receipts. It has no dependencies and does not call a model.

The core memory install is still small. Add this pack only when your project needs to keep its documents consistent as they change.

## Install in about a minute

From the wallaby-agent-rules repository:

```bash
python3 extras/memory-governance/memory_governance.py --target /path/to/your-project init
cd /path/to/your-project
python3 scripts/memory_governance.py doctor
```

A fresh install ends with:

```text
CONTRADICTIONS open=0
RECEIPTS pending=0
DOCTOR OK
```

`init` creates `.memory/` and copies the CLI to `scripts/memory_governance.py`. It never overwrites an existing config or script. The sample premise passes when `README.md` exists; the sample contradiction is already resolved.

## Your first change

Tell the CLI what changed and which old name, path, or claim should no longer appear:

```bash
python3 scripts/memory_governance.py impact \
  --event file_move \
  --terms "old-component" \
  --record
```

The output lists the surfaces to review, the files containing the old term, and a receipt ID such as `R-000001`. Update those files, then run:

```bash
python3 scripts/memory_governance.py verify --receipt R-000001
python3 scripts/memory_governance.py doctor
```

`verify` passes only when no unresolved references remain. To keep an intentional historical mention, allow its path explicitly:

```bash
python3 scripts/memory_governance.py verify \
  --receipt R-000001 \
  --allow "archive/**"
```

The receipt stays append-only: the impact scan and the later verification are separate records.

## Conduction events

The default `.memory/impact.json` covers nine event types:

| Event | Use it for |
|---|---|
| `feature` | A new user-facing capability |
| `mechanism` | A rule, parameter, or behavior change |
| `document` | A new core document |
| `external_copy` | Public wording changes |
| `automation` | A new scheduled or recurring component |
| `decision` | An approved decision with dependent state |
| `skill` | A skill or reusable procedure change |
| `file_move` | A rename, move, or path retirement |
| `closure` | Completion and current-state updates |

Each event maps to required surfaces and says whether premise and contradiction reviews are needed. Edit this JSON to fit your project; `doctor` rejects malformed rules instead of silently ignoring them.

## Premise levels and checks

A premise records a relationship your design depends on, the signal that would disprove it, and where to check that signal.

| Level | Meaning when the failure signal fires | Exit behavior |
|---|---|---|
| `P0` | The current action must stop | Exit 2 |
| `P1` | A human must review before relying on the result | Exit 1 |
| `P2` | Show a warning without blocking routine work | Exit 0 with a visible warning |

Four deterministic signal types need no shell execution:

- `file_missing`: fails when a required path is absent.
- `file_exists`: fails when a forbidden path is present.
- `text_contains`: fails when required text is absent from a file.
- `json_equals`: fails when a nested JSON value differs from the expected value.

`manual` marks a signal that needs human evidence. It cannot produce a silent green result for P0 or P1.

```bash
python3 scripts/memory_governance.py premise check
```

## Contradiction history

Record the old statement, the replacement, and the evidence. Resolving an item appends to its history instead of deleting the earlier claim.

```bash
python3 scripts/memory_governance.py contradict add \
  --old "INDEX.md is optional" \
  --new "INDEX.md is updated whenever a file is added" \
  --evidence "DECISION-42"

python3 scripts/memory_governance.py contradict check
python3 scripts/memory_governance.py contradict resolve \
  --id C-002 \
  --evidence "DECISION-42"
```

`contradict check` and `doctor` return nonzero while any item remains open.

## What the scanner does and does not do

- It reads text files and reports paths and match counts, not file contents.
- It skips `.git`, `.credentials`, `.memory`, dependency directories, and build output.
- It stops after 5,000 scanned files or 200 matching files with an explicit warning.
- Oversized or unreadable files are reported and block verification.
- It never edits project documents. You decide what to change and which historical mentions to allow.

## Files

| File | Job |
|---|---|
| `.memory/impact.json` | Event-to-surface mapping |
| `.memory/premises.json` | Premise levels, assertions, signals, and status |
| `.memory/contradictions.json` | Old and new statements with append-only history |
| `.memory/receipts.jsonl` | Pending impact scans and later verifications |
| `scripts/memory_governance.py` | The installed CLI |

Run the complete check after any change:

```bash
python3 scripts/memory_governance.py doctor
```

For implementation tests, run `python3 -m unittest discover -s extras/memory-governance/tests -v` from the repository root.
