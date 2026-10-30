<!-- wallaby-agent-rules 1.4.0 -->
# Sanitized failure examples

These are composite examples, not customer incidents or entries from a private project. They show how to preserve a failure's structure without sharing its business facts. All start open; verify a fix in your own project before marking it verified.

### F-EX-001 · 2026-01-05 · stale
- **Trigger**: A new session asked whether a document had been published.
- **Observed**: The agent repeated a week-old "draft" status even though the linked page was live.
- **Expected**: Check the current source before making a status claim.
- **Root cause**: A static snapshot was treated as current state.
- **Fix**: Before status claims, read the live source and cite it; do this at answer time.
- **Regression check**: Publish a fixture, then ask the same question. The answer must cite the live fixture.
- **Status**: open: composite example.

### F-EX-002 · 2026-01-06 · missing
- **Trigger**: A log entry said "migration complete" with no path, commit, ticket, or link.
- **Observed**: Nobody could verify what had migrated or where to inspect it.
- **Expected**: Every completion claim includes evidence.
- **Root cause**: The log format accepted unsupported completion claims.
- **Fix**: Require an evidence pointer in the closeout template and scan for missing pointers.
- **Regression check**: A completion entry without evidence fails the check; one with a commit passes.
- **Status**: open: composite example.

### F-EX-003 · 2026-01-07 · stale
- **Trigger**: Work was marked done in LOG.md but remained open in NOW.md.
- **Observed**: The next session resumed finished work.
- **Expected**: The event log and current state move together.
- **Root cause**: Two writes were scheduled as separate actions, and the second was skipped.
- **Fix**: Update LOG.md and NOW.md in the same closeout action.
- **Regression check**: After closing a fixture task, both files agree before the next session starts.
- **Status**: open: composite example.

### F-EX-004 · 2026-01-08 · stale
- **Trigger**: A pending item said "update this later."
- **Observed**: The item had no owner-visible state and stayed unchanged across sessions.
- **Expected**: A pending item states its anchor and current condition.
- **Root cause**: Deferral language replaced an explicit state.
- **Fix**: Write `<anchor> — <current status>`; forbid "later" and similar placeholders in pending entries.
- **Regression check**: A new pending entry can be acted on without searching the old conversation.
- **Status**: open: composite example.

### F-EX-005 · 2026-01-09 · not-loaded
- **Trigger**: The agent built a second script for a check that already existed.
- **Observed**: Two implementations drifted after the next change.
- **Expected**: Search CAPABILITIES.md before creating a reusable tool.
- **Root cause**: The capability registry was never consulted.
- **Fix**: Add a registry search to the creation procedure and record new capabilities on creation.
- **Regression check**: A request naming the existing trigger words reaches the registered script.
- **Status**: open: composite example.

### F-EX-006 · 2026-01-10 · not-loaded
- **Trigger**: A deployment skipped a documented preflight check.
- **Observed**: The agent knew the runbook existed but did not open it before acting.
- **Expected**: The runbook is read at the action boundary.
- **Root cause**: Operating knowledge was stored away from the procedure that needed it.
- **Fix**: Link the runbook from the deployment command and make reading it step one.
- **Regression check**: The deployment transcript shows the runbook read before any mutation.
- **Status**: open: composite example.

### F-EX-007 · 2026-01-11 · missing
- **Trigger**: A writer dropped the list marker required by a downstream dashboard.
- **Observed**: The entry existed, but the dashboard ignored it for two days.
- **Expected**: Producer and consumer share a testable format contract.
- **Root cause**: The output shape was implicit and untested.
- **Fix**: Add one fixture covering the producer's output and the consumer's parser.
- **Regression check**: Removing the marker fails the contract test; restoring it passes.
- **Status**: open: composite example.

### F-EX-008 · 2026-01-12 · stale
- **Trigger**: A component was renamed, but two documents kept the old path.
- **Observed**: The next session followed dead links and rebuilt the missing component.
- **Expected**: A rename updates every affected reference.
- **Root cause**: The change checklist omitted documentation surfaces.
- **Fix**: Search for the old name in the same rename action and update MAP.md plus linked references.
- **Regression check**: After renaming a fixture, the old path has no live references.
- **Status**: open: composite example.

### F-EX-009 · 2026-01-13 · not-loaded
- **Trigger**: A long session relied on a table read near its first message.
- **Observed**: Hundreds of messages later, the agent listed six fewer affected surfaces than the table contained.
- **Expected**: Read the authoritative table when building the final checklist.
- **Root cause**: Early context was treated as if it were still available at decision time.
- **Fix**: Re-read the table at the moment the checklist is produced.
- **Regression check**: A long-context fixture produces the same checklist as a fresh session.
- **Status**: open: composite example.

### F-EX-010 · 2026-01-14 · invented
- **Trigger**: The agent claimed that no migration tool existed.
- **Observed**: A search of the capability registry found an existing tool with a different name.
- **Expected**: Negative claims include where and how the search ran.
- **Root cause**: One filename guess was treated as exhaustive coverage.
- **Fix**: Record search locations and trigger words; say "not found" until coverage supports "none exists."
- **Regression check**: The same request returns the registered tool and its entry point.
- **Status**: open: composite example.
