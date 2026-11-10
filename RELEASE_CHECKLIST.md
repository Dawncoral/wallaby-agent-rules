<!-- wallaby-agent-rules 1.4.3 -->
# Release checklist

Every version ships when every box is ticked, in this order. (This file is ours — it keeps us honest; users only see the results.)

## Version numbers and cadence (v4.1 立，源=10-04 三连版教训)

- **Three tiers**: major (1.0.0→2.0.0) = new capability theme + a distribution event; minor (1.1.0) = module-level additions; patch (1.0.1) = fixes, licensing, copy. **Patches do not get their own Release or announcement by default. Exception: a patch with a user-visible CLI/workflow change may get a patch Release, clearly labeled, with no marketing announcement.**
- **Batch, don't drip**: same-day changes on the same theme accumulate into one version window. Default ceiling: **one public version (major/minor) per week**. If a feature is done Tuesday, it waits for the window — a version number is a promise of attention, and attention is finite.
- **Releases are the marketing event**: majors/minors get a GitHub Release; one Release can bundle many commits. The patch exception above is a maintenance notice, not a marketing event. (10-04: three bumps landed same day — externally there was exactly one Release, 1.0.0.)
- **Hotfix exception**: compliance/safety/licensing fixes ship any time, as a patch number, without the distribution event.
- **Heat-window exception**: when an external window is hot (a platform moment, a live conversation), the owner may break the weekly ceiling by an explicit, dated decision recorded in the project log. Every break is counted and reviewable — urgency should be a decision with a receipt, never a habit. (10-06: two breaks in four days, both owner-approved and logged; this clause exists so the count is visible.)
- Self-check before assigning a number: "would a user care that this number changed?" If no, it's a patch or it waits.

## Ship steps

1. External-copy gate and native-English gate pass on all changed user-facing text; gate record kept with the release.
2. **License/compliance check** — is LICENSE still the intended one? Did anything legal-adjacent change? (v4.0.1 existed because this step was missing at v4.)
3. **Rules census**: `python3 extras/memory-governance/memory_governance.py --target . audit --rules`. This repo's always-loaded instructions stay within their baseline; fix or explain any rule repeated across files.
4. Version markers bumped to the new version on every changed file (unchanged files keep their markers).
5. CHANGELOG: new version section on top, plus a "Migrating from vX" subsection.
6. L2 upgrade prompt: fingerprints updated so it recognizes the previous version, and the "compare against" layout names the new one.
7. Repo description and topics match the current release theme (GitHub settings).
8. Push to main.
9. Create the GitHub Release (tag `vX`; majors/minors, plus the user-visible patch exception), with the migration notes as the body — Releases are how existing users hear about new versions.
10. Internal registration: doc registry + project log.

If a step was skipped, the release isn't done. The fix is always: finish the step, then note it — never "we'll catch it next time."
