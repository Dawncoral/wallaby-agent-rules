#!/usr/bin/env python3
"""1.4.5 shared rules: one source block, generated copies, drift in doctor, copies not counted as duplicates.

Run: python3 -m unittest tests.test_shared_rules   (from extras/memory-governance/)
"""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "memory_governance.py"
SPEC = importlib.util.spec_from_file_location("memory_governance_shared", CLI)
mg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mg)

RULE = "- Never push directly to main; always open a pull request and wait for review before merging anything.\n"
SOURCE = ("# Writing rules\n\n<!-- shared-rules:writes BEGIN source -->\n" + RULE
          + "- Always run the full test suite before you commit.\n<!-- shared-rules:writes END -->\n")


def copy_of(body):
    return ("<!-- shared-rules:writes BEGIN copy of docs/rules.md; edit the source, then run rules sync -->\n"
            + body + "<!-- shared-rules:writes END -->\n")


def run(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = mg.main(list(argv))
    return code, out.getvalue()


class SharedRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()
        (self.root / "docs/rules.md").write_text(SOURCE, encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# Agents\n\nKeep this line.\n\n" + copy_of(RULE) + "\nTail stays.\n", encoding="utf-8")
        (self.root / "CLAUDE.md").write_text("# Claude\n\n" + copy_of(""), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_reports_drift_and_writes_nothing(self):
        before = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        code, out = run("--target", str(self.root), "rules", "sync", "--check")
        self.assertEqual(code, 1)
        self.assertIn("drift=2", out)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), before)

    def test_sync_copies_the_source_and_keeps_the_rest(self):
        code, out = run("--target", str(self.root), "rules", "sync")
        self.assertEqual(code, 0, out)
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Keep this line.", agents)
        self.assertIn("Tail stays.", agents)
        self.assertIn("Always run the full test suite", agents)
        self.assertIn("Always run the full test suite", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))
        code, out = run("--target", str(self.root), "rules", "sync", "--check")
        self.assertEqual(code, 0, out)
        self.assertIn("drift=0", out)
        code, out = run("--target", str(self.root), "rules", "sync")
        self.assertNotIn("UPDATED", out)

    def test_two_sources_and_open_marker_are_problems(self):
        (self.root / "GEMINI.md").write_text("<!-- shared-rules:writes BEGIN source -->\nx\n<!-- shared-rules:writes END -->\n"
                                             "<!-- shared-rules:other BEGIN copy -->\n", encoding="utf-8")
        res = mg.shared_sync(self.root, check=True)
        joined = " ".join(res["problems"])
        self.assertIn("two sources", joined)
        self.assertIn("BEGIN without END", joined)

    def test_markers_in_code_fences_are_examples(self):
        (self.root / "README.md").write_text("```\n<!-- shared-rules:demo BEGIN copy -->\n```\n", encoding="utf-8")
        names, problems = mg.shared_scan(self.root)
        self.assertNotIn("demo", names)
        self.assertEqual(problems, [])

    def test_crlf_copy_keeps_its_line_endings(self):
        (self.root / "GEMINI.md").write_bytes(copy_of("old\n").replace("\n", "\r\n").encode())
        run("--target", str(self.root), "rules", "sync")
        raw = (self.root / "GEMINI.md").read_bytes()
        self.assertIn(b"Never push directly", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))

    def test_copies_are_not_reported_as_duplicates(self):
        run("--target", str(self.root), "rules", "sync")
        census = mg.rules_census(self.root)
        self.assertEqual(census["pairs"], [])
        self.assertTrue(any(r.get("shared") == "copy" for r in census["rules"]))
        (self.root / "GEMINI.md").write_text(RULE, encoding="utf-8")   # a hand-pasted repeat still shows
        self.assertTrue(mg.rules_census(self.root)["pairs"])

    def test_source_in_an_entry_file_is_not_a_duplicate_of_its_copy(self):
        (self.root / "docs/rules.md").unlink()
        (self.root / "GEMINI.md").write_text(SOURCE.replace("# Writing rules", "# Gemini").replace("docs/rules.md", "GEMINI.md"),
                                             encoding="utf-8")
        run("--target", str(self.root), "rules", "sync")
        self.assertEqual(mg.rules_census(self.root)["pairs"], [])

    def test_doctor_is_silent_without_blocks(self):
        empty = tempfile.TemporaryDirectory()
        try:
            self.assertEqual(mg.shared_lines(mg.shared_sync(Path(empty.name), check=True)), [])
        finally:
            empty.cleanup()

    def test_doctor_shows_drift_and_clears_after_sync(self):
        run("--target", str(self.root), "init")
        code, out = run("--target", str(self.root), "doctor")
        self.assertIn("SHARED blocks=1 copies=2 drift=2", out)
        self.assertNotEqual(code, 0)
        run("--target", str(self.root), "rules", "sync", "--actor", "test")
        code, out = run("--target", str(self.root), "doctor")
        self.assertIn("SHARED blocks=1 copies=2 drift=0", out)
        events = (self.root / ".memory").glob("events*.jsonl")
        self.assertTrue(any("rules.sync" in p.read_text(encoding="utf-8") for p in events))

    def test_json(self):
        code, out = run("--target", str(self.root), "rules", "sync", "--check", "--json")
        data = json.loads(out)
        self.assertEqual((data["blocks"], data["copies"], len(data["drift"])), (1, 2, 2))


if __name__ == "__main__":
    unittest.main()
