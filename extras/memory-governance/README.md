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

The 1.4.3 commands create their own files under `.memory/` when you first use them, and they never rewrite an existing one. The test suite installs the published 1.4.0 and 1.4.2 CLIs, upgrades each, and compares every file.

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

From 1.4.3, `route --record` and `verify` cover the same ground in two commands. See [Two commands for one change](#two-commands-for-one-change).

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

### Two commands for one change

```bash
python3 scripts/memory_governance.py route "rename old-plan to starter" --paths docs/pricing.md --terms old-plan
# make the change
python3 scripts/memory_governance.py verify
```

`--record` opens a pending receipt when the tier is heavy. `--terms` opens one too and scans for an old name or path. The card then ends with the receipt ID. A light change with no `--terms` gets no receipt.

`verify` closes the receipt after the change. It passes when three things hold:

- no file still contains the old terms; allow a historical mention with `--allow "archive/**"`;
- no P0 or P1 premise that depends on the changed paths is failing;
- every script, skill, or workflow the card listed under `REGISTER` is in CAPABILITIES.md.

`verify` also prints a `REVIEW` line with the surfaces whose content is the same as when the receipt was opened. That line does not block, because a surface may need no change. With one receipt pending, `verify` takes no argument. With several, name one with `--receipt`.

The longer path still works: `impact --record` opens a receipt for one event and a list of terms, and `verify --receipt <id>` closes it.

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

Files that were unregistered when the audit first ran are a baseline. `init` records it in `.memory/audit_baseline.json`; in a project that adds CAPABILITIES.md later, the first `audit` does. `audit` and `doctor` count only files added after the baseline and print one line about the rest, and `map sync` still prints a row for each. An entry leaves the baseline when you register or delete the file. `audit --rebaseline` accepts the files that are unregistered today.

### Keep MAP.md current

```bash
python3 scripts/memory_governance.py map sync
python3 scripts/memory_governance.py map sync --check
```

`map sync` writes a generated block between `<!-- map:auto:begin -->` and `<!-- map:auto:end -->`, with one row per top-level directory: files, INDEX rows, registered capabilities, unregistered files, and split files. Rows you wrote outside the block stay as they are. It also prints paste-ready rows: new CAPABILITIES.md entries marked `incubating`, CAPABILITIES.md retirements, and new MAP.md components. It never writes them for you. `--check` exits 1 when the block lacks a top-level directory or a split file; `doctor` runs the check. A change in the counts alone is not drift: `doctor` stays green, and the next `map sync` refreshes them.

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

### Measure the instructions agents load

```bash
python3 scripts/memory_governance.py audit
python3 scripts/memory_governance.py audit --rules
```

`audit` finds the instruction files with no setup and splits them in two:

- **Always loaded**: root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, and `.github/copilot-instructions.md`. Every session pays for these, so `audit` counts their rules and their size.
- **On demand**: nested entry files, skills under `.claude/skills`, `.agents/skills`, `skills`, and `.github/skills`, and the `.cursor/rules`, `.claude/rules`, and `.github/instructions` folders. `audit` reports how many there are and their size.

A rule is a sentence with a word such as must, never, always, or do not, or a Chinese equivalent; wrapped lines in a paragraph count as one. A symlink or a second path to the same file counts once. Skills bundled elsewhere in the tree, such as inside an extension, are not counted.

The first run records the always-loaded part in `.memory/rules_baseline.json`. You edit nothing. When the rule count rises above the baseline, or the size grows by more than 10%, `audit` and `doctor` print one line suggesting one rule in, one rule out. A rule that appears almost word for word in more than one file gets a paste-ready fix. When there is nothing to report, both stay silent, and neither ever changes an exit code.

`audit --rules` prints JSON for the agent's weekly review: the numbers above, the baseline, every near-verbatim repeat, a compact list of all rules, and the user's recorded answer about guardrails. `audit --rebaseline-rules` accepts the current always-loaded instructions as the new baseline. `audit --rules-answer guardrails=no` or `guardrails=yes` records the user's answer, so the agent asks only once. See [the rules review](WEEKLY_RECONCILE.md#the-rules-review).

## Write, events, and IDs (1.4.3)

Agents can still edit the memory files directly. Use these three commands when you want each write checked and recorded.

### Write one checked line

```bash
python3 scripts/memory_governance.py write log "Shipped the pricing page" --source docs/pricing.md
python3 scripts/memory_governance.py write now "Checkout redesign" --pointer docs/checkout.md
python3 scripts/memory_governance.py write close "Checkout live" --match "checkout" --pointer docs/checkout.md
```

| Form | File | What it does |
|---|---|---|
| `log` | LOG.md | Adds one dated line on top of its month. A month that is not in the file yet goes above the older months of a newest-first log. |
| `now` | NOW.md | Adds one dated line under In flight. `--pointer` is required. |
| `close` | NOW.md, LOG.md | Takes the matching line out of In flight, adds a pointer under Recently touched, and writes the LOG.md entry, in one action. |
| `propose` | PROPOSALS.md | Queues a fact with its source. It skips a fact that is already in MEMORY.md or in the queue. |
| `promote` | PROPOSALS.md, MEMORY.md | Moves one approved proposal into the MEMORY.md section you name. |
| `reject` | PROPOSALS.md, LOG.md | Removes one proposal and logs the reason. |
| `fact` | MEMORY.md | Adds one dated, sourced line under the section you name. |
| `index` | INDEX.md | Registers a file. `--update` changes the note of a file that is already registered. |
| `capability` | CAPABILITIES.md | Adds a row above the template's placeholder row. The state defaults to `incubating`. |
| `map` | MAP.md | Adds a component to the table under `--area`. |
| `failure` | FAILURES.md | Adds an entry in the template's format with the next `F` ID, newest first. |

Every form works the same way:

- It redacts API keys, bearer tokens, `token=` and `password=` values, email addresses, IPv4 addresses, and home-directory user names.
- It finds its place by heading or table header. When it cannot, it stops, lists the headings it found, and writes nothing.
- Before it writes, it checks that every existing line is still there, byte for byte and in order. The only lines that leave are the ones `close`, `promote`, `reject`, and `index --update` are asked to move or replace.
- It keeps the file's line endings.
- `--dry-run` prints the line and where it would go. `--json` prints the result for tools.
- `--take D` puts the next ID of a series in front of the line, as in `- [2026-11-10] D-001 · Keep prices in USD`.

`write batch --file entries.jsonl` writes several entries. Each line is a JSON object with a `"face"` key that names the form, plus that form's options. It stops at the first entry that fails and says how many were written.

In a project without `.memory/`, `write` still edits the file and skips the event log.

### See what was written, and by whom

```bash
python3 scripts/memory_governance.py events
python3 scripts/memory_governance.py events list --since 41
python3 scripts/memory_governance.py events verify
```

`.memory/events.jsonl` gets one line for each write, receipt, contradiction, split, map sync, and ID:

```json
{"seq": 42, "ts": "2026-11-10T13:38:25+00:00", "actor": "claude-code", "event": "write.log", "file": "LOG.md", "sha256": "9d1c…", "summary": "- [2026-11-10] Shipped the pricing page — docs/pricing.md", "prev": "3f6c1d0a9b2e4c57"}
```

- `actor` is `--actor`, else the `WALLABY_MEMORY_ACTOR` environment variable, else `cli`. Set the variable once for each agent. The operating-system user name is never recorded.
- `seq` counts up by one. `events list --since <seq>` shows what happened after a point you noted, oldest first, so an agent can ask what changed while it worked.
- `prev` ties each line to the one before it. `events verify` exits 1 when a line was edited, removed, or merged in from another copy.
- `sha256` is the file's hash after the write. When a logged file changes without the CLI, `events verify` and `doctor` say so in one line and keep their exit codes. `events adopt` records the current state; add `--note` to say why.

The log describes one working copy on one machine. It does not merge across branches or across machines.

### Take an ID

```bash
python3 scripts/memory_governance.py id take D --note "currency for prices"
python3 scripts/memory_governance.py id list
python3 scripts/memory_governance.py id audit
```

A series is one to four capital letters. Five are built in: `R` for receipts, `C` for contradictions, `P` for premises, `F` for failures, and `D` for decisions. Any other name starts a series of your own at 001.

`take` returns the next free ID and records it. The number is above the counter in `.memory/ids.json`. It is also above every number of that series already written in MEMORY.md, NOW.md, LOG.md and its volumes, PROPOSALS.md, FAILURES.md, and the pack's own records. Examples inside comments and code blocks do not count. Two agents that ask at the same moment get different numbers: a lock file makes them take turns, and a lock left by a run that died is removed after two minutes.

`audit` exits 1 when a contradiction, premise, or failure ID is defined twice. It also notes receipt IDs that 1.4.0 to 1.4.2 issued more than once, and IDs taken more than seven days ago that no file mentions.

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
| `.memory/rules_baseline.json` | The always-loaded instructions at first run, plus the user's guardrails answer |
| `.memory/audit_baseline.json` | Files that were unregistered before the first audit |
| `.memory/events.jsonl` | One line for each write, receipt, contradiction, split, map sync, and ID |
| `.memory/ids.json` | The next number of each ID series |
| `scripts/memory_governance.py` | The installed CLI |

Run the complete check after any change:

```bash
python3 scripts/memory_governance.py doctor
```

For implementation tests, run `python3 -m unittest discover -s extras/memory-governance/tests -v` from the repository root.

To build a recurring review around these checks, read [Weekly reconciliation: a creation guide](WEEKLY_RECONCILE.md). It covers the weekly sequence, report template, finding ownership, and the limits of a green result.
