#!/bin/sh
# sync_skill_form.sh — regenerate skill-form/references/ from the single
# source of truth (prompt-pack/ + schema/). Never edit references/ by hand;
# edit the source and re-run this script.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HERE/skill-form/references"
for f in 00-route 10-forge-interview 11-sop-interview 20-generate-skill 21-generate-sop 30-optimize; do
  cp "$HERE/prompt-pack/$f.md" "$HERE/skill-form/references/$f.md"
done
cp "$HERE/schema/ledger.md" "$HERE/skill-form/references/schema-ledger.md"
echo "skill-form/references synced from prompt-pack/ + schema/"
