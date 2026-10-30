# Skill Forge prompt pack

The forge, without the server. These files are the same protocol the MCP server runs, packaged as plain Markdown you paste into any agent conversation. No install, no dependencies.

## The workflow

1. **Route**: not sure whether the thing should be a skill or an SOP? Paste `00-route.md`. If the user already named the form, skip it.
2. **Interview**: paste `10-forge-interview.md` (skill) or `11-sop-interview.md` (SOP). The agent derives the requirements from the description, asks only what it can't derive, and hands you a structured answers object. The default skill form is `core`; `core-shell` keeps the same executable steps with less surrounding material.
3. **Generate**: paste `20-generate-skill.md` or `21-generate-sop.md` with the answers filled in. You get the skill directory (or SOP document), one unnumbered feedback footer, and a birth certificate of trigger test pairs.
4. **Optimize**: a week later, paste `30-optimize.md` with the skill text and any failure records. You get a substance-test rewrite and a manual health check.

## What you give up without the server (be honest with yourself)

The MCP version (`../mcp/`) automates five things this pack cannot:

1. **High-stakes scanning**: the server runs deterministic rules over the description and names what must be confirmed with the user. Here, you check the static list in `10-forge-interview.md` yourself.
2. **Ledger writes with redaction**: the server appends to `~/.skill-forge/ledger.jsonl` and redacts keys, tokens, emails, IPs on write (see `../schema/ledger.md`). Here, you append by hand and redact by hand.
3. **Idle warnings**: the server flags a ledger that has gone quiet for 14 days. Here, the rule is written down in `30-optimize.md`; run it yourself.
4. **Byte-exact size metering**: the server measures the skill body. Here: `wc -c`, and 6KB = 6,144 bytes. The tiers are weaker-model/short-context heuristics, not automatic `layered` triggers.
5. **Machine health checks**: the server emits a seven-item report with waivers. Here, the same seven items are a manual checklist in `30-optimize.md`.

If you want those five automated, install the server. The protocol is identical either way.

## Full-flow mode

Full flow adds the maintenance and optimize rhythm. A week in, run the optimize pass. The rhythm card: log failures as they happen / weekly threshold check / degrade to observational capture when the ledger idles / regression-test after big rewrites. The feedback instruction stays a footer unless the deployer's own real ledger shows that a numbered step works better.
