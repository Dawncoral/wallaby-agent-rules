<!-- wallaby-agent-rules 1.4.1 -->
# Weekly reconciliation: a creation guide

A weekly reconciliation compares what your project says happened with the evidence available now. It finds stale state, unsupported completion claims, broken references, failing premises, open contradictions, and checks that cannot see their own blind spots.

Keep it verifiable. The goal is not to prove that everything is true, but to leave a short, inspectable list of what needs correction, who should decide, and when to review it again.

## Design principles

### 1. Read first, change later

Run deterministic checks before any semantic review. The scanner reports candidates; a person or an explicit policy decides what they mean. Do not let the checker rewrite memory, close findings, or mark its own output as verified.

### 2. Separate sources from derived views

A log can be a source of events. A dashboard, summary, or generated status page is usually a view. Reconciliation compares them but does not treat agreement between two derived views as proof.

### 3. Completion needs evidence

A useful completion claim has a path, commit, ticket, link, receipt, or live check. “Done” without evidence is a review candidate, not a verified fact.

### 4. Negative claims need coverage

“Missing”, “gone”, “no references”, and “already resolved” require a search scope: which files, which terms, which date window, and which live sources were checked. An unread file is not an absent file.

### 5. Premises need failure signals

Write the relationship the design depends on, then define how you would notice it failing. Give the signal a level:

- **P0**: stop the action.
- **P1**: require human review.
- **P2**: warn without blocking routine work.

A premise without an observable failure signal is a note for later discussion, not a reliable check.

### 6. Contradictions keep history

Record the old statement, the replacement, and the evidence. Resolve by appending the decision and its source. Do not silently delete the losing side.

### 7. Small reports, explicit owners

A useful weekly report fits on one screen when possible. Every finding needs an owner, a next action, and a review condition. A long list with no owner becomes another source of drift.

### 8. Review the checker too

Ask what the current checks cannot see: large files, renamed concepts, new file types, external systems, or rules added after the scanner was configured. A green result within a limited scope is not a green result everywhere.

## The weekly sequence

### Step 1: Fix the scope

Choose the project, the time window, and the sources you will inspect. A typical window is seven days. Use a longer window only for a specific reason, such as a release or a migration.

Write down the scope before running anything. Changing it midway makes the findings hard to compare.

### Step 2: Run the mechanical checks

For a project using the core memory system and the governance pack:

```bash
python3 scripts/health_check.py
python3 scripts/reconcile.py
python3 scripts/memory_governance.py doctor
```

These cover different failure modes:

- `health_check.py`: file and memory hygiene, index drift, stale entries, budgets, secrets hygiene, and commit silence.
- `reconcile.py`: completion claims that conflict with current state or lack evidence.
- `doctor`: premise failures, open contradictions, and pending impact receipts.

A nonzero exit is a finding to inspect, not a failure to hide. A zero exit is evidence only within the checks' coverage.

### Step 3: Inspect recent changes

Take the changes from the window and ask:

1. Which old names, paths, prices, versions, or claims changed?
2. Which documents or derived views should have moved with them?
3. Which completions need fresh evidence rather than the original log entry?

Run an impact scan for the old terms:

```bash
python3 scripts/memory_governance.py impact \
  --event mechanism \
  --terms "old-name" \
  --record
```

Review the listed surfaces and the matching files. Then verify the receipt or explicitly allow intentional historical mentions.

### Step 4: Review premises and contradictions

Run:

```bash
python3 scripts/memory_governance.py premise check
python3 scripts/memory_governance.py contradict list --open
```

For each active item, ask whether the current signal is real, recent, and attached to the statement being made. If a new change invalidates an old premise, revise the premise or register the contradiction; do not leave both meanings implicit.

### Step 5: Add a small semantic sample

Mechanical checks cannot judge whether a statement is still meaningful. Sample a few recent high-impact changes and read their actual sources. Prefer releases, migrations, permission changes, public commitments, and incidents over routine edits.

For live systems, refresh the evidence at review time. A file fingerprint or an old console snapshot does not prove current production state.

### Step 6: Classify findings

Use four buckets:

- **Fix now**: a clear typo, dead link, missing pointer, or stale state with an obvious correction.
- **Needs a decision**: two sources disagree, the right behavior is a judgment call, or a premise changed.
- **Intentional history**: an old statement is allowed because it is clearly marked as historical.
- **Checker gap**: the current rules cannot answer the question. Record the coverage gap instead of inventing a green result.

### Step 7: Record and schedule the next review

Write the report using the template below. Close only findings with evidence. Keep the rest open with an owner and a review condition.

A weekly cadence is a default, not a law. Run an additional reconciliation after a large migration or before a consequential release.

## Report template

```markdown
# Weekly reconciliation — YYYY-MM-DD

## Scope
- Project:
- Window:
- Sources checked:
- Explicitly out of scope:

## Checks run
- health_check: exit N
- reconcile: exit N
- governance doctor: exit N
- Additional live checks:

## Findings
- [ ] [P0/P1/P2] Finding — evidence — owner — next action — review condition

## Intentional history / allowed items
- Item — reason for allowing it — evidence

## Checker gaps
- What the current checks cannot see:

## Decisions needed
- Question — person who decides — evidence to read

## Completion receipts
- Verified items and their evidence:

## Next review
- Date or trigger:
```

## A small worked example

Suppose a component was renamed, and the log says the migration is complete.

1. `impact --terms "old-component" --record` finds the old name in `README.md` and creates `R-000001` as pending.
2. The first `verify` fails because the reference remains.
3. You update the current documentation. One mention in `archive/old-design.md` is intentionally historical, so you allow that exact path.
4. The second `verify` finds no unallowed references and appends a verification record.
5. `doctor` returns zero because the receipt is verified, no contradiction is open, and no premise is failing.

The useful artifact is not the green line alone. It is the sequence: old reference found, explicit review, intentional exception recorded, final evidence appended.

## What not to build

- Do not auto-rewrite long-term facts because a scanner found a keyword.
- Do not auto-close contradictions or pending receipts without evidence.
- Do not scan every historical document every week by default. Use the current window and expand only when needed.
- Do not treat a fixed schedule as proof of freshness for live systems.
- Do not measure success by the number of checks or findings. Measure whether important mismatches get resolved and whether the same blind spots keep returning.

## Useful weekly measures

Track a few operational signals over time:

- Completion claims without evidence.
- Current-state lines that disagree with the event log.
- Pending receipts and their age.
- Open contradictions and their age.
- Unreadable files and scan-limit warnings.
- Findings that recur after a previous fix.

These measures show whether the reconciliation process is useful. They do not prove that the underlying memory is accurate.
