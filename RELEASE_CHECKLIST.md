<!-- wallaby-agent-rules v4 -->
# Release checklist

Every version ships when every box is ticked, in this order. (This file is ours — it keeps us honest; users only see the results.)

1. External-copy gate and native-English gate pass on all changed user-facing text; gate record kept with the release.
2. Version markers bumped to the new version on every changed file (unchanged files keep their markers).
3. CHANGELOG: new version section on top, plus a "Migrating from vX" subsection.
4. L2 upgrade prompt: fingerprints updated so it recognizes the previous version, and the "compare against" layout names the new one.
5. Repo description and topics match the current release theme (GitHub settings).
6. Push to main.
7. Create the GitHub Release (tag `vX`), with the migration notes as the body — Releases are how existing users hear about new versions.
8. Internal registration: doc registry + project log.

If a step was skipped, the release isn't done. The fix is always: finish the step, then note it — never "we'll catch it next time."
