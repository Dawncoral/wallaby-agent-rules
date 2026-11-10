#!/usr/bin/env python3
"""1.4.3 rules census: the instructions agents load, a baseline, near-verbatim repeats. Report only, never blocks.

Run: python3 -m unittest tests.test_rules   (from extras/memory-governance/)
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "memory_governance.py"
SPEC = importlib.util.spec_from_file_location("memory_governance_rules", CLI)
mg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mg)

AGENTS = """# Project rules

- Never read `.env` files or print secrets.
- Always run the full test suite before committing any change to the repository.
- Do not push directly to main.

## Closeout
- Always update NOW.md when tracked work closes.
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rules-test-")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def cli(self, *args, ok=0):
        r = subprocess.run([sys.executable, str(CLI), "--target", str(self.root), *args], text=True,
                           capture_output=True, stdin=subprocess.DEVNULL)
        if ok is not None:
            self.assertEqual(r.returncode, ok, f"{args}\n{r.stdout}\n{r.stderr}")
        return r

    def rules_lines(self, text):
        return [ln for ln in text.splitlines() if ln.startswith("RULES") or ln.startswith("  ") and "replace it with" in ln]


class DiscoveryTests(Base):
    def test_resident_and_on_demand_split(self):
        self.write("AGENTS.md", AGENTS)
        self.write(".github/copilot-instructions.md", "- Always answer in English.\n")
        self.write("api/AGENTS.md", "- Never edit generated clients.\n")
        self.write(".claude/skills/deploy/SKILL.md", "---\nname: deploy\n---\n- Always dry-run first.\n")
        self.write(".github/skills/triage/SKILL.md", "- Never close an issue without a reply.\n")
        self.write(".cursor/rules/style.mdc", "- Always use tabs.\n")
        self.write(".claude/rules/db.md", "- Never run migrations by hand.\n")
        self.write(".github/instructions/py.instructions.md", "- Always type-annotate.\n")
        self.write("extensions/copilot/assets/skills/demo/SKILL.md", "- Always do product things.\n")  # product-bundled skill
        self.write("docs/notes/SKILL.md", "- Never count this.\n")
        resident, on_demand = mg.rule_files(self.root)
        self.assertEqual(resident, ["AGENTS.md", ".github/copilot-instructions.md"])
        self.assertEqual(sorted(on_demand), sorted([
            "api/AGENTS.md", ".claude/skills/deploy/SKILL.md", ".github/skills/triage/SKILL.md",
            ".cursor/rules/style.mdc", ".claude/rules/db.md", ".github/instructions/py.instructions.md"]))

    def test_symlinked_entry_file_counts_once(self):
        self.write(".ai/AGENTS.md", AGENTS)
        os.symlink(".ai/AGENTS.md", self.root / "AGENTS.md")
        os.symlink(".ai/AGENTS.md", self.root / "CLAUDE.md")
        resident, on_demand = mg.rule_files(self.root)
        self.assertEqual(resident, ["AGENTS.md"])
        self.assertEqual(on_demand, [])
        census = mg.rules_census(self.root)
        self.assertEqual(census["resident"]["rules"], 4)
        self.assertEqual(census["pairs"], [])

    def test_governance_data_is_skipped(self):
        self.write("AGENTS.md", AGENTS)
        self.write(".memory/splits/backup/x/AGENTS.md", AGENTS)
        self.assertEqual(mg.rule_files(self.root)[1], [])


class ExtractionTests(unittest.TestCase):
    def test_wrapped_paragraph_is_one_rule(self):
        text = "Intro.\n\nYou must keep every change small and\nreviewable, and you must never merge\nyour own pull request.\n"
        rules = mg.extract_rules(text)
        self.assertEqual(len(rules), 1)
        self.assertIn("never merge your own pull request", rules[0][1])

    def test_fences_front_matter_headings_and_tables_are_skipped(self):
        text = ("---\ndescription: you must not count this\n---\n# Never a rule\n\n```\nnever run this\n```\n\n"
                "| Rule | Why |\n|---|---|\n| Always lint | style |\n\n- 必须先跑测试；禁止直接推送\n")
        texts = [t for _, t in mg.extract_rules(text)]
        self.assertIn("Always lint", texts)
        self.assertIn("必须先跑测试", texts)
        self.assertIn("禁止直接推送", texts)
        self.assertFalse(any("count this" in t or "never run this" in t or "Never a rule" in t for t in texts))

    def test_symlink_text_ghost_is_ignored(self):
        self.assertEqual(mg.extract_rules(".ai/AGENTS.md"), [])


class BaselineTests(Base):
    def test_first_run_records_silently_and_growth_is_reported_not_blocked(self):
        self.write("README.md", "# x\n")
        self.write("AGENTS.md", AGENTS)
        r = self.cli("audit")
        self.assertEqual(self.rules_lines(r.stdout), [])
        base = json.loads((self.root / ".memory" / mg.RULES_BASELINE).read_text(encoding="utf-8"))
        self.assertEqual((base["rules"], base["files"]), (4, ["AGENTS.md"]))
        self.write("AGENTS.md", AGENTS + "- Never commit generated files.\n")
        r = self.cli("audit")
        self.assertTrue(any("over baseline" in ln and "5 rules" in ln and "baseline 4" in ln for ln in r.stdout.splitlines()))
        self.cli("init")
        r = self.cli("doctor")
        self.assertIn("RULES over baseline", r.stdout)
        self.assertIn("DOCTOR OK", r.stdout)
        self.cli("audit", "--rebaseline-rules")
        self.assertEqual(self.rules_lines(self.cli("audit").stdout), [])

    def test_small_wording_edits_stay_quiet_but_big_growth_reports(self):
        self.write("AGENTS.md", AGENTS)
        self.cli("audit")
        self.write("AGENTS.md", AGENTS.replace("secrets.", "secrets or tokens."))
        self.assertEqual(self.rules_lines(self.cli("audit").stdout), [])
        self.write("AGENTS.md", AGENTS + "\nBackground that has no rule words in it at all. " * 20 + "\n")
        self.assertIn("over baseline", self.cli("audit").stdout)

    def test_project_without_instruction_files_is_silent(self):
        self.write("README.md", "# x\n")
        self.cli("init")
        self.assertEqual(self.rules_lines(self.cli("doctor").stdout), [])
        self.assertEqual(self.rules_lines(self.cli("audit").stdout), [])


class DuplicateTests(Base):
    def test_near_verbatim_rule_across_files_gets_a_paste_ready_fix(self):
        self.write("AGENTS.md", AGENTS)
        self.write(".claude/skills/ship/SKILL.md",
                   "- Always run the full test suite before committing any change to the repository.\n")
        r = self.cli("audit")
        lines = r.stdout.splitlines()
        self.assertTrue(any(ln.startswith("RULES duplicates: 1 rule") for ln in lines), r.stdout)
        fix = next(ln for ln in lines if "replace it with" in ln)
        self.assertIn("keep this rule once in AGENTS.md", fix)
        self.assertIn(".claude/skills/ship/SKILL.md:1", fix)
        self.assertIn('See AGENTS.md: "Always run the full test suite', fix)

    def test_same_file_short_and_merely_similar_rules_are_not_flagged(self):
        self.write("AGENTS.md", AGENTS + "- Always run the full test suite before committing any change to the repository.\n")
        self.write("CLAUDE.md", "- Don't read .env files.\n- Do not push to main.\n")
        self.assertEqual(mg.rules_census(self.root)["pairs"], [])

    def test_skills_only_duplicates_point_at_a_shared_file(self):
        rule = "- Never install unfamiliar remote packages while reproducing an issue from an untrusted report.\n"
        self.write("skills/a/SKILL.md", rule)
        self.write("skills/b/SKILL.md", rule)
        noms = mg.rules_nominations(mg.rules_census(self.root))
        self.assertEqual(len(noms), 1)
        self.assertEqual(noms[0]["keep_in"], "docs/shared-rules.md")
        self.assertEqual(len(noms[0]["places"]), 2)


class InterfaceTests(Base):
    def test_rules_json_answer_once_and_bad_answer(self):
        self.write("AGENTS.md", AGENTS)
        data = json.loads(self.cli("audit", "--rules").stdout)
        for key in ("resident", "on_demand", "baseline", "over_baseline", "duplicate_pairs", "nominations", "guardrails", "rules"):
            self.assertIn(key, data)
        self.assertIsNone(data["guardrails"])
        self.assertEqual(data["rules"][0], {"f": "AGENTS.md", "l": 3, "k": "r", "t": "Never read `.env` files or print secrets."})
        self.cli("audit", "--rules-answer", "guardrails=no")
        self.assertEqual(json.loads(self.cli("audit", "--rules").stdout)["guardrails"]["answer"], "no")
        self.cli("audit", "--rebaseline-rules")
        self.assertEqual(json.loads(self.cli("audit", "--rules").stdout)["guardrails"]["answer"], "no")
        self.assertIn("guardrails=yes", self.cli("audit", "--rules-answer", "maybe", ok=2).stderr)

    def test_install_adds_exactly_one_line_and_asks_nothing(self):
        self.write("AGENTS.md", AGENTS)
        out = self.cli("init").stdout.splitlines()
        rules = [ln for ln in out if ln.startswith("RULES")]
        self.assertEqual(len(rules), 1)
        self.assertIn("4 always-loaded rule(s) in 1 instruction file(s)", rules[0])

    def test_audit_json_carries_a_rules_summary(self):
        self.write("AGENTS.md", AGENTS)
        data = json.loads(self.cli("audit", "--json").stdout)
        self.assertEqual(data["rules"]["resident"]["rules"], 4)
        self.assertIn("duplicate_pairs", data["rules"])


if __name__ == "__main__":
    unittest.main()
