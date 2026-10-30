# Optimize an existing skill

First, ask the user one question:

> Recently, has this skill misfired, felt off, or failed to trigger when it should have?

Append the answer to the failure records below as optimization input. Do not assume the ledger is complete; on-the-spot collection is the fallback. Keep the feedback instruction and default to footer/auto. P1 did not reproduce a numbered-step advantage, but it did not prove position universally irrelevant. Recommend step only when the deployer's own real ledger shows a benefit. Ask first, then start.

## The substance test

Go through the skill section by section, sentence by sentence: **if this sentence were deleted, would behavior change?** Four verdicts:

- **Cut**: deleting it changes nothing: narrative, family history, dead data snapshots.
- **Sink**: low-frequency scene detail moves into `references/`; the body keeps a one-line routing pointer with the trigger condition.
- **Demote**: don't cut or sink; switch to read-on-demand. Allowed only if you can name which scene needs it AND that scene has another fallback. Can't name both → not allowed.
- **Keep**: red lines, high-frequency rules, and the trigger protocol always stay in the body. Before deleting any red line, rewrite it into a shorter red line that stays.

After editing, append one line to the change-log area at the end of the skill: date + what changed + why.

## Failure records (priority input)

Check each one off: confirm the rewrite catches it.

```
{paste your failure-ledger records here}
```

## Skill text

```
{paste the full SKILL.md here}
```

---

## Manual health check (7 items)

The MCP server runs these as machine checks. By hand, walk the same list:

1. **Description**: present, and phrased as trigger conditions like "use when …"? A manual-phrased description is a heuristic warning; behavior tests are the arbiter.
2. **Size**: the 6KB (6,144 bytes) and 9KB tiers are heuristics from weaker-model/short-context samples, not cross-model laws. They never require `layered` by themselves. Layer only for an explicit context budget, observed empty/truncated responses or cost anomalies, or naturally on-demand content. Otherwise test in the target environment; repetition and tangled structure can still be compressed.
3. **Hard-coded volatile facts**: versions, dates, prices, snapshots. Rewrite as pointers.
4. **Bare filenames in commands**? Full paths.
5. **Red lines**: absent while the content touches shell, network, files, or money → high risk, add red lines. Purely conversational or text skills are exempt.
6. **Pitfalls**: keep real, sourced failures when they exist. `core` and `core-shell` do not require a "none on record" placeholder.
7. **Ritual budget**: more than 3 maintenance lines → compress to a single trailing note. Criteria sentences over half the body lines → criteria only for key steps.

**Waivers**: a line `forge-waiver: <n> <reason>` inside the skill exempts check `<n>`. List waived items visibly in your report — never swallow them silently.

## The 14-day idle rule

If the failure ledger has history but nothing new in 14 days, one of two things is true: nothing really failed, or the feedback hook isn't running, i.e. the agent isn't recording. Action: drop to observational capture — after each use of the skill, ask "did anything just fail?" and record by hand. If the ledger stays idle for a full month, re-check whether the trigger conditions and the feedback hook are still in the skill body.
