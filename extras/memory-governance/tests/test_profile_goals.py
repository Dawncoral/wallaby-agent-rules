#!/usr/bin/env python3
"""Tests for PROFILE.md (format, review age, confirm, export and import) and numbered goals in MEMORY.md.

Every test builds a synthetic project in a temporary directory; nothing touches a real project.
Run: python3 -m unittest tests.test_profile_goals   (from extras/memory-governance/)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_stream import Base, TEMPLATES  # noqa: E402

PROFILE_LINES = {
    "## Always ask me first": "- [2025-01-01] Ask before any deploy — source: user: \"always ask me before you deploy\"",
    "## How I judge work": "- [2026-06-01] Numbers before opinions — source: user: \"show me the data first\"",
    "## Pace and communication": "- [2026-11-01] Lead with the answer — source: user: \"answer first, then why\"",
}


class ProfileTests(Base):
    def setup_profile(self, extra=None):
        self.project()
        text = (TEMPLATES / "PROFILE.md").read_text(encoding="utf-8")
        for head, line in {**PROFILE_LINES, **(extra or {})}.items():
            text = text.replace(head + "\n", head + "\n\n" + line + "\n", 1)
        self.write("PROFILE.md", text)

    def test_template_is_clean(self):
        self.project()
        self.write("PROFILE.md", (TEMPLATES / "PROFILE.md").read_text(encoding="utf-8"))
        res = self.js("profile", "check")
        self.assertEqual((res["entries"], res["errors"], res["due"]), (0, [], []))   # examples in comments do not count

    def test_review_age_by_heading(self):
        self.setup_profile()
        res = self.js("profile", "check", "--today", "2026-11-11")
        self.assertEqual(res["entries"], 3)
        self.assertEqual([d["text"] for d in res["due"]], ["Numbers before opinions"])  # 163 days > 90; ask-first never ages
        self.assertIn("write confirm", self.cli("profile", "check", "--today", "2026-11-11").stdout)

    def test_format_errors_fail(self):
        self.setup_profile({"## Boundaries": "- No date on this one — source: user: \"x\"\n- [2026-11-02] No source here\n"
                                             "- [2026-11-03] Lead with the answer — source: user: \"again\""})
        text = self.read("PROFILE.md").replace("## What drives me", "## Misc")
        self.write("PROFILE.md", text)
        r = self.cli("profile", "check", "--json", ok=1)
        errs = " | ".join(e["error"] for e in __import__("json").loads(r.stdout)["errors"])
        for want in ("not dated", "no source", "same as line", "unknown heading 'Misc'"):
            self.assertIn(want, errs)

    def test_confirm_refreshes_one_line_and_logs_it(self):
        self.setup_profile()
        before = self.read("PROFILE.md")
        out = self.js("write", "confirm", "--match", "numbers before", "--source", 'user: "yes, still"', "--date", "2026-11-11")
        after = self.read("PROFILE.md")
        self.assertIn("- [2026-11-11] Numbers before opinions — source: user: \"show me the data first\"", after)
        self.assertNotIn("[2026-06-01]", after)
        self.assertEqual(len(after.splitlines()), len(before.splitlines()))
        self.assertIn("Confirmed with the user: Numbers before opinions", self.read("LOG.md"))
        self.assertEqual(len(out["files"]), 2)
        self.assertEqual(self.js("profile", "check", "--today", "2026-11-11")["due"], [])
        self.assertIn("already confirmed", self.js("write", "confirm", "--match", "numbers before", "--date", "2026-11-11")["skipped"])
        self.assertEqual(self.cli("write", "confirm", "--match", "nothing like this", ok=2).returncode, 2)

    def test_a_profile_md_of_another_kind_is_left_alone(self):
        self.project()
        self.write("PROFILE.md", "# My profile\n\nI like tea.\n- some note\n")
        res = self.js("profile", "check")
        self.assertEqual((res["recognized"], res["errors"]), (False, []))
        self.assertIn("not checked", self.cli("profile", "check").stdout)
        self.assertNotIn("PROFILE", self.cli("doctor", ok=None).stdout)
        self.assertIn("nothing to export", self.cli("profile", "export", "--path", str(self.root / "pkg"), ok=2).stderr)

    def test_harvest_promotes_into_profile(self):
        self.setup_profile()
        self.cli("write", "propose", "--text", "One currency per page", "--source", 'user: "never mix currencies"',
                 "--origin", "harvest", "--date", "2026-11-10")
        self.cli("write", "promote", "--match", "one currency", "--file", "PROFILE.md", "--section", "How I judge work")
        self.assertIn("One currency per page", self.read("PROFILE.md"))
        self.assertEqual(self.js("profile", "check", "--today", "2026-11-11")["errors"], [])

    def test_export_import_byte_for_byte(self):
        self.setup_profile()
        pkg = self.root / "pkg"
        self.js("profile", "export", "--path", str(pkg))
        original = (self.root / "PROFILE.md").read_bytes()
        self.assertEqual((pkg / "PROFILE.md").read_bytes(), original)
        self.assertEqual(self.cli("profile", "export", "--path", str(pkg), ok=2).returncode, 2)       # not empty
        self.write("PROFILE.md", self.read("PROFILE.md") + "\n- [2026-11-11] local change — source: me\n")
        self.assertIn("--replace", self.cli("profile", "import", "--path", str(pkg), ok=2).stderr)
        res = self.js("profile", "import", "--path", str(pkg), "--replace")
        self.assertTrue(res["imported"])
        self.assertEqual((self.root / "PROFILE.md").read_bytes(), original)
        self.assertTrue((self.root / res["kept"]).is_file())
        self.assertIn("profile.import", [e["event"] for e in self.events()])
        (pkg / "PROFILE.md").write_bytes(original + b"tampered\n")
        self.assertIn("manifest", self.cli("profile", "import", "--path", str(pkg), "--replace", ok=2).stderr)
        self.assertEqual((self.root / "PROFILE.md").read_bytes(), original)


class GoalTests(Base):
    def setup_goals(self):
        self.project()
        self.write("MEMORY.md", self.read("MEMORY.md").rstrip("\n") +
                   "\n\n## Goals\n\n- G1 · Ten paying teams by March\n- V1 · Never store request bodies\n"
                   "<!-- - G9 · an example in a comment -->\n")

    def test_goal_pointer_checked_on_write(self):
        self.setup_goals()
        self.cli("write", "log", "Shipped the team plan", "--goal", "g1", "--date", "2026-11-10")
        self.assertIn("Shipped the team plan · goal: G1", self.read("LOG.md"))
        self.cli("write", "now", "Billing page", "--pointer", "docs/billing.md", "--goal", "G1", "--date", "2026-11-10")
        self.assertIn("Billing page · goal: G1; details: docs/billing.md", self.read("NOW.md"))
        r = self.cli("write", "log", "Something", "--goal", "G9", ok=2)
        self.assertIn("G9 is not under Goals", r.stderr)
        self.assertIn("unrecognized arguments: --goal",
                      self.cli("write", "fact", "x", "--source", "y", "--goal", "G1", ok=2).stderr)   # only log, now, close take it

    def test_lookup_lists_goals_and_audit_flags_a_missing_one(self):
        self.setup_goals()
        self.cli("write", "log", "Shipped the team plan", "--goal", "G1", "--date", "2026-11-10")
        res = self.js("lookup", "--registry", "goal")
        by = {g["goal"]: g for g in res["rows"]}
        self.assertEqual(set(by), {"G1", "V1"})                                       # the commented example does not count
        self.assertEqual((by["G1"]["pointers"], by["V1"]["pointers"], by["V1"]["kind"]), (1, 0, "value"))
        self.assertEqual([g["goal"] for g in self.js("lookup", "--registry", "goal", "--query", "paying")["rows"]], ["G1"])
        self.write("LOG.md", self.read("LOG.md") + "- [2026-11-09] Old work · goal: G7\n")
        ghosts = self.js("audit", ok=1)["ghost"]
        self.assertTrue(any("goal: G7" in g["item"] for g in ghosts), ghosts)
        self.assertIn("ghost=1", self.cli("doctor", ok=1).stdout)                   # doctor counts; audit lists

    def test_goal_text_without_a_goals_section_is_not_a_pointer(self):
        self.project()
        self.write("LOG.md", self.read("LOG.md") + "- [2026-11-01] Hit the Q4 goal: G2 milestone\n")
        self.assertFalse(any("goal:" in g["item"] for g in self.js("audit", ok=None)["ghost"]))

    def test_no_goals_section(self):
        self.project()
        self.assertIn("no goals", self.js("lookup", "--registry", "goal")["note"])
        self.assertIn("add a Goals section", self.cli("write", "log", "x", "--goal", "G1", ok=2).stderr)

if __name__ == "__main__":
    unittest.main()
