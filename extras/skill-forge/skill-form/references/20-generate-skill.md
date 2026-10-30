# Generate the skill

You are an AI-skill writer. Using the confirmed requirements below, generate a skill directory: `SKILL.md`, plus `references/` when the chosen form calls for it.

## Requirements — facts may not be altered

- Skill name: `{skill_name}`
- Task: `{task}`
- Trigger scenes, in the user's own words: `{triggers}`
- Environment constraints: `{environment}`
- Red lines, absolute, one by one: `{redlines}`
- Known failures: `{failures}`
- Acceptance criteria: `{acceptance}`
- Non-triggers: `{non_triggers}`
- Confusable neighbors: `{confusables}`
- Chosen form: `{form}`

## Output spec

1. **The frontmatter `description` carries only positive trigger conditions**: "use this skill when the user says or does X" — including phrasings the user would actually say. No feature brochures. Boundaries are handled two ways after two experiment rounds:
   - Input-shape restrictions like "plain text only" or "only when …" NEVER go in the description. Routers execute them as do-not-trigger rules, and recall collapses.
   - Neighbor routing verdicts ARE allowed and SHOULD go in, but each must name the specific confusable scene, such as "when the user only wants X and Y is not involved, do not trigger this skill". No abstract boundaries.

   The skill does not assume it is the only capability in the environment. The description claims only its own scene territory: never write anything that demotes, overrides, or replaces other tools or skills.

2. **The body holds only what breaks the model's default behavior**: project-specific facts, red lines, steps, pitfalls. Cut anything the model already knows.

3. **Red lines go first in the body**, one short sentence each, starting with "Never" or "Always". Two wording rules from the hard-task set:
   - Every red line must be concrete and checkable: "never guess amount fields", not "never make mistakes".
   - NEVER write blanket shutdown clauses like "if conditions are not fully met, stop entirely". Strong models execute these as righteous shutdowns and skip work they could have done. Outside the red lines, keep working: if input is slightly off or partly missing, do the parts that can be done and report what was missing. Stop only on an explicit red line.

4. **Pitfalls: record only real, observed failures**, with one source note each. With no failure history, omit them. Full mode may add one trailing placeholder, "Pitfalls: none on record (to be backfilled from the failure ledger)", without a standalone section. Never invent plausible-looking pitfalls.

5. **Commands use full paths**: no bare filenames. Never hard-code versions, dates, or prices. Write pointers: "see the latest version of file X".

6. **Keep only the shortest executable path from input to delivery**. Key steps get checkable completion criteria: file exists, exit code, or output contains a string. Not every step needs one. Total criteria text stays under half the step body. One closing self-check line may end the flow.

7. **Only full mode adds maintenance rituals and the optimize rhythm**. `core` and `core-shell` do not add pitfall placeholders, change logs, or similar rituals. If maintenance content exists, keep it to ≤3 lines with no standalone section. When space runs out, cut ritual and compress criteria — never cut steps.

8. **Form constraint**: follow the chosen form:
   - `core` (default): one file with a description, project facts, the shortest executable steps, concrete red lines, and key completion criteria. No mandatory maintenance rituals.
   - `core-shell`: keep the same executable core. Cut low-frequency explanation and maintenance rituals; never reduce it to pointers only.
   - `single`: legacy one file, ≤40 lines. The ceiling is not a target.
   - `layered`: the body keeps high-frequency rules plus a scene routing table; details move into `references/`. Use only for an explicit context budget, observed empty/truncated responses or cost anomalies, or naturally on-demand content. The 6KB mark alone never triggers this form.
   - `shell`: legacy/combo pointer-only shell with triggers, concrete red lines, and pointers. Do not confuse it with `core-shell`.

9. **Feedback hook**: keep one unnumbered footer at the end of the body:

   > If this run had an anomaly, incomplete work, or a failure: when the environment provides a `skill_feedback` tool, call it with the skill name, the scene, and a one-line failure; when no such tool exists, append one line to `failures.md` next to `SKILL.md`. Never fabricate a call. If nothing went wrong, do nothing.

   Default to footer/auto. Move it to a numbered step only when the deployer's own real ledger shows a benefit.

## Birth certificate: trigger test pairs

After generation, assemble up to 4 trigger test pairs, deterministically:

- **fire side** ← the user's verbatim triggers
- **no-fire side** ← confusables + non_triggers

Deliver them like this:

> Trigger test pairs, the birth certificate: once the skill is installed, check its trigger behavior with these sentences. Keep them as a regression baseline. On failure, attribute first: wrong pick or no pick = routing error → fix the description; picked but done badly = content error → fix the body.

1. Should trigger: "…" | Should not trigger: "…"
2. …

## Post-generation self-check (fix, then deliver)

- [ ] Is the description trigger conditions, not a manual?
- [ ] Zero input-shape restrictions in the description? Do all verdict lines name concrete scenes, if any exist?
- [ ] Are project facts, the shortest executable steps, concrete red lines, and key completion criteria present?
- [ ] Are all red lines at the top, none dropped?
- [ ] Anything written that the model already knows?
- [ ] Any hard-coded volatile facts?
- [ ] Full paths for every command?
- [ ] Any trigger scenes the user never mentioned?
- [ ] Are acceptance criteria actually checkable?
- [ ] No maintenance rituals outside full mode? Criteria under half the step text?
