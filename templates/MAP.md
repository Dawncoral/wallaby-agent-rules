<!-- wallaby-agent-rules 1.4.0 -->
# MAP.md — the system map

> Optional. INDEX.md maps files; MAP.md maps the parts of the system and what a change may affect.
> Add a component only when changing it makes you ask: "What else needs updating?"
> Keep one component per line. Put operating details in the linked file, not here.

## Memory and instructions

| Component | Job | Change keywords | Details |
|---|---|---|---|
| `MEMORY.md` | Long-term facts and rules | memory, facts, rules | `MEMORY.md` |
| `NOW.md` | Current work and recent state | status, current work | `NOW.md` |
| `INDEX.md` | File lookup | files, documents | `INDEX.md` |

## Product and operations

| Component | Job | Change keywords | Details |
|---|---|---|---|
| `<component>` | `<one sentence>` | `<words that should lead here>` | `<path>` |

## Maintenance

- Keep it current. Update this map in the same change as the component itself, so the next session can see which linked surfaces need review.
- Link one authoritative file per component; do not copy its contents here.
- Remove a component when its change no longer affects another surface.
<!-- The file names above are examples. Replace them with your own system parts. -->
