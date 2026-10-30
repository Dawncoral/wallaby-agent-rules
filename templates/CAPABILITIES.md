<!-- wallaby-agent-rules 1.4.0 -->
# CAPABILITIES.md — reusable capabilities

> Optional. Register a script, skill, template, scheduled job, or other reusable capability here.
> Before building something, search this file for the words you would naturally use.
> Search before building. A new entry starts as `incubating`; promote it after repeated use, and retire it when another capability replaces it or the entry no longer has a consumer.

## Entry rules

- Record a capability when it is reused, or when its use is already recurring.
- Keep one authoritative entry point. Link instructions instead of copying them.
- Each row answers three questions: when to use it, where to start, and whether it is current.

## Capabilities

| Capability | Form | Entry point | Trigger words | State | Call / output |
|---|---|---|---|---|---|
| `health_check.py` | Script | `scripts/health_check.py` | tidy up, stale files, index drift | active | `python3 scripts/health_check.py`; findings with exit code 1 |
| `<capability>` | `<script / skill / template / job>` | `<path>` | `<natural words>` | `<incubating / active / retired>` | `<shortest call and default result>` |

## Lifecycle

- **Incubating**: built once; still needs evidence of reuse.
- **Active**: the authoritative implementation for this job.
- **Retired**: keep for history, but do not use for new work.
