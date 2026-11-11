#!/usr/bin/env python3
"""Help an agent can act on: every command and write form has an example, and every example parses.

Also guards the two copies of the weekly scripts (templates/ and the skill's scripts/) against drifting apart.
Run: python3 -m unittest tests.test_help   (from extras/memory-governance/)
"""
import shlex
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import memory_governance as mg  # noqa: E402

REPO = HERE.parents[2]


def examples(text):
    for part in text.split("   |   "):
        part = part.split("   (prefer:")[0].strip()
        yield shlex.split(part)[2:]          # drop "python3 scripts/memory_governance.py"


class HelpTests(unittest.TestCase):
    def test_every_command_and_form_has_an_example(self):
        p = mg.build_parser()
        sub = next(a for a in p._actions if a.dest == "command")
        write = sub.choices["write"]
        faces = next(a for a in write._actions if a.dest == "face")
        self.assertEqual(set(sub.choices) - set(mg.HELP_EXAMPLES), set())
        self.assertEqual(set(faces.choices) - set(mg.WRITE_EXAMPLES), set())

    def test_every_example_parses(self):
        p = mg.build_parser()
        for text in list(mg.HELP_EXAMPLES.values()) + list(mg.WRITE_EXAMPLES.values()):
            for argv in examples(text):
                with self.subTest(argv=argv):
                    try:
                        p.parse_args(argv)
                    except SystemExit as e:
                        self.fail(f"example does not parse: {argv} (exit {e.code})")

    def test_groups_name_every_command_once(self):
        listed = [w.strip(",") for line in mg.HELP_GROUPS.splitlines()[1:4] for w in line.split()[1:] if w[0].isalpha()]
        listed = [w for w in listed if w not in ("of", "older", "form", "route", "then") or w == "route"]
        sub = next(a for a in mg.build_parser()._actions if a.dest == "command")
        for name in sub.choices:
            self.assertIn(name, mg.HELP_GROUPS, name)


class CopyTests(unittest.TestCase):
    def test_weekly_scripts_have_one_content(self):
        for name in ("health_check.py", "reconcile.py"):
            a = (REPO / "templates" / name).read_bytes()
            b = (REPO / "skills" / "agent-memory-rules" / "scripts" / name).read_bytes()
            self.assertEqual(a, b, f"templates/{name} and skills/agent-memory-rules/scripts/{name} differ: copy one over the other")


if __name__ == "__main__":
    unittest.main()
