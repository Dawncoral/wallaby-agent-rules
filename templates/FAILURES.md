<!-- wallaby-agent-rules 1.4.0 -->
# FAILURES.md — memory failure regression log

> Optional. Record a failure when the system forgot, invented, kept stale state, or failed to load what it already knew.
> One failure becomes one regression case. Remove private facts, credentials, customer names, and business terms before sharing an entry.
> See `../examples/FAILURES.example.md` for sanitized composite examples.

## Entry format

```markdown
### F-001 · YYYY-MM-DD · <stale / invented / missing / not-loaded>
- **Trigger**: The request or situation that exposed the failure.
- **Observed**: What actually happened.
- **Expected**: What the memory system should have done.
- **Root cause**: Where the chain failed: not written, not loaded, not retrieved, stale, or overwritten.
- **Fix**: The change that prevents this class of failure, with its scope and execution time.
- **Regression check**: The next similar situation and the observable pass condition.
- **Status**: open / verified on YYYY-MM-DD in <scenario>.
```

## Fix forms

1. **Merge into the action**: make the correct write or check part of the action itself.
2. **Attach to a fixed moment**: put the rule where it is read before installation, deployment, closeout, or another fixed step.
3. **Scan afterward**: use a deterministic check only when the first two forms cannot catch it in time.
4. **Unguarded**: if prevention depends only on remembering, say so. Do not claim it as a verified fix.

## Regression entries

<!-- Add new entries above this line. Keep the newest entry first. -->
