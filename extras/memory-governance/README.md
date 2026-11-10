<!-- wallaby-agent-rules 1.4.3 -->
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
AUDIT missing=0 ghost=0 orphan=0 stub=0 volume=0 (skipped: no CAPABILITIES.md: missing and orphan checks off; no MAP.md: map path checks off)
MAP skipped
DOCTOR OK
```

`init` creates `.memory/` and copies the CLI to `scripts/memory_governance.py`. It never overwrites an existing config or script. The sample premise passes when `README.md` exists; the sample contradiction is already resolved.

## Lossless upgrades

Preview an upgrade without changing any file:

```bash
python3 scripts/memory_governance.py upgrade \
  --source /path/to/newer/memory_governance.py
```

The preview shows the current and available versions and the backup path. If you approve it, run the same command with `--apply`. Only the CLI is replaced, after a backup is written to `.memory/backups/`. The new CLI must start and report the expected version, or the original is restored automatically. `MEMORY.md`, `NOW.md`, `.memory/` configs, receipts, and all other project files stay untouched. Downgrades are refused.

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

## Route, audit, map, and split (1.4.3)

These commands connect the governance pack to `MAP.md`, `CAPABILITIES.md`, and the memory files. None of them calls a model, and each one skips the checks for files your project does not have.

### Route a change before you make it

```bash
python3 scripts/memory_governance.py route "add a restore step to the backup flow" --paths scripts/restore.py
```

`route` prints one card of about 2 KB:

- capabilities to reuse, matched by trigger word, name, or entry path; a retired row shows its replacement note;
- scripts, skills, and workflows on the changed paths that CAPABILITIES.md does not list yet;
- the MAP.md components and areas the change touches;
- event types, with the word or path that matched, and their surfaces;
- the tier, with reasons;
- the premises to review.

The tier is `light` only when two things hold. First, every event is light, which by default means `document` and `closure`, or you pass both `--reversible` and `--single-area`. Second, the components sit in one map area. Any of these makes it `heavy`: a risk word such as delete, migrate, deploy, credential, or payment; an `external_copy` event; or no matching event.

A premise with `depends_on` globs appears only when a changed path matches them. A premise without `depends_on` appears every time, so nothing drops out unnoticed. `--detail` lifts the 2 KB budget; `--json` prints the card for tools.

Each event in `.memory/impact.json` can take three optional keys: `match`, `light`, and `always_heavy`. A `match` block lists words and paths, for example `{"words": ["handbook"], "paths": ["docs/"]}`. A top-level `risk` block replaces the default risk words and paths. Without these keys, the built-in defaults apply. Path patterns work like `.gitignore`: no slash matches a file name anywhere, a trailing slash matches a directory, and `**` matches any depth.

### Look a row up

```bash
python3 scripts/memory_governance.py lookup --registry capability --query backup --status active
python3 scripts/memory_governance.py lookup --registry map --query restore
```

### Audit the registries

```bash
python3 scripts/memory_governance.py audit
```

| Finding | Meaning |
|---|---|
| `missing` | A file under `scripts/`, `bin/`, `skills/*/SKILL.md`, or `.github/workflows/` that CAPABILITIES.md does not list. The governance scripts themselves are exempt. |
| `ghost` | An entry point, a MAP.md path, or a pointer stub that leads to a missing file. |
| `orphan` | An active capability that nothing outside CAPABILITIES.md, MAP.md, and INDEX.md mentions. |
| `stub` | A pointer stub that holds more than its pointer line. |
| `volume` | A month volume that no longer matches its checksum in the volume list. |

`doctor` runs the audit and fails while any finding remains. An optional `audit` block in `impact.json`, with `capability_globs` and `exempt` lists, replaces the default file patterns.

### Keep MAP.md current

```bash
python3 scripts/memory_governance.py map sync
python3 scripts/memory_governance.py map sync --check
```

`map sync` writes a generated block between `<!-- map:auto:begin -->` and `<!-- map:auto:end -->`, with one row per top-level directory: files, INDEX rows, registered capabilities, unregistered files, and split files. Rows you wrote outside the block stay as they are. It also prints paste-ready rows: new CAPABILITIES.md entries marked `incubating`, CAPABILITIES.md retirements, and new MAP.md components. It never writes them for you. `--check` exits 1 when the block is out of date; `doctor` runs the check.

### Split memory files that grew too large

Month volumes are automatic:

```bash
python3 scripts/memory_governance.py split volume auto
```

When LOG.md passes 128 KiB and holds finished months, each finished `## YYYY-MM` section moves to `LOG/YYYY-MM.md`. The current month stays in LOG.md, and a volume list at its top records each volume's section count and SHA-256. Newest-first and oldest-first logs both work; a log with months out of order is left alone. To split another append-only file, run `split volume plan --file <path>`, review the plan, and apply it with `--plan-sha`; after that, `auto` includes the file.

Topic splits need a person:

```bash
python3 scripts/memory_governance.py split topic propose
python3 scripts/memory_governance.py split topic apply --plan-sha <sha> --confirm
```

When MEMORY.md passes its soft wall (150 lines or about 8k tokens), `propose` nominates sections, `Dormant` and `Standby` first and never `Active`. When INDEX.md passes 300 rows or 32 KiB, it nominates `##` sections or long runs of rows under one top-level directory. A section moves intact to `MEMORY/<topic>.md` or `INDEX/<part>.md`. Its old place keeps the heading and one dated pointer line, and nothing else. A moved MEMORY.md topic gets a row in INDEX.md.

Every split, in either mode:

- checks that the merged text equals the original, byte for byte, in memory before writing and on disk after;
- restores the original files if either check fails;
- writes a manifest and a backup under `.memory/splits/` and a receipt in `receipts.jsonl`;
- refreshes the MAP.md block when one exists;
- can be undone with `split volume rollback --tx <id>` or `split topic rollback --tx <id>`. A rollback keeps lines written to a topic file after the split.

`split volume verify` and `split stub check` run on their own, and `audit` runs both.

`reconcile.py` and `health_check.py` 1.4.3 read the volumes and INDEX parts. Update both scripts before your first split.

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
| `.memory/receipts.jsonl` | Pending impact scans, later verifications, and split receipts |
| `.memory/splits/` | One manifest per split, plus backups of every file a split changed |
| `scripts/memory_governance.py` | The installed CLI |

Run the complete check after any change:

```bash
python3 scripts/memory_governance.py doctor
```

For implementation tests, run `python3 -m unittest discover -s extras/memory-governance/tests -v` from the repository root.

To build a recurring review around these checks, read [Weekly reconciliation: a creation guide](WEEKLY_RECONCILE.md). It covers the weekly sequence, report template, finding ownership, and the limits of a green result.
