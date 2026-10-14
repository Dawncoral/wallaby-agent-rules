# Generate the SOP

You are an SOP writer. Using the confirmed requirements below, generate an SOP document, a single Markdown file.

## Requirements (facts may not be altered)

- Name: `{skill_name}`
- Purpose and task: `{task}`
- Activation conditions: `{triggers}`
- Usage scene / roles: `{environment}`
- Red lines, one by one: `{redlines}`
- Known failure points: `{failures}`
- Acceptance criteria: `{acceptance}`
- Non-applicable situations: `{non_triggers}`

## SOP skeleton (six sections, all required)

1. **Purpose and scope**: what it governs, what it doesn't. One paragraph.
2. **Activation conditions**: when this SOP is used.
3. **Roles and responsibilities**: executor / Owner / review cycle.
4. **Operating steps**: numbered, one by one. Key steps carry a completion criterion: file exists, output contains a string, or a named human confirms.
5. **Exceptions and escalation**: common failures + handling + escalation conditions, meaning when to stop and who to call.
6. **Change log**: append-only table with date + what changed + why. First row = this creation.

## SOP discipline (the opposite of a skill: SOPs are for people, so be thorough)

- Background, rationale, and examples are all welcome — human readers carry no size budget. That budget is a skill constraint. Don't mix the two.
- Volatile facts like versions, prices, and specific dates are still written as pointers, never hard-coded: "see the latest version of file X".
- Failure history records only what really happened, one source note per entry. If none, write "none on record". Never invent.
- Sign-off: creation date + Owner + review cycle.

## Post-generation self-check

- [ ] All six sections present?
- [ ] Every red line concrete and checkable, not a slogan?
- [ ] Do the step criteria actually check something?
- [ ] Any volatile facts hard-coded?
- [ ] Failure history all real and sourced?
