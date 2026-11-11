#!/usr/bin/env python3
"""Tests for harvest: the user's own words, gathered from LOG.md and FAILURES.md, reviewed through PROPOSALS.md.

Every test builds a synthetic project in a temporary directory; nothing touches a real project.
Run: python3 -m unittest tests.test_harvest   (from extras/memory-governance/)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_stream import Base  # noqa: E402

LOG_LINES = """
## 2026-11

- [2026-11-07] 改了报错 — source: 用户「报错原文不要直接给客户看，应该做映射」
- [2026-11-06] Reworked onboarding — source: user: "too many steps, people should not need to configure anything", then "it should work right after install"
- [2026-11-06] Agent suggested "freeze all changes for two weeks"; nobody said so
- [2026-11-05] Chose plan B — source: user: "plan B"
- [2026-11-04] Kept the release cap — source: user: "keep the cap as it is for now" (answering "Keep the cap of one release a week, or lift it?")
- [2026-11-03] Started phase two — source: user: "go ahead"
- [2026-11-02] Moved pricing to USD — source: user: "Always quote prices in USD, never mix currencies on one page"
"""
OWN = {"报错原文不要直接给客户看，应该做映射",
       "too many steps, people should not need to configure anything",
       "it should work right after install",
       "Always quote prices in USD, never mix currencies on one page"}


class HarvestTests(Base):
    def setup_records(self):
        self.project()
        log = self.read("LOG.md")
        head, _, rest = log.partition("\n## ")
        self.write("LOG.md", head.rstrip("\n") + "\n" + LOG_LINES + ("\n## " + rest if rest else ""))
        self.write("LOG/2025-10.md", "# LOG.md — 2025-10\n\n- [2025-10-20] Dropped the dashboard — source: "
                                     "user: \"we should never build reports nobody opens\"\n")
        failures = self.read("FAILURES.md").replace(
            "<!-- Add new entries above this line.",
            "### F-001 · 2026-11-08 · stale\n- **Trigger**: user: \"that's wrong, the deadline moved to Friday, always check the calendar first\"\n\n"
            "<!-- Add new entries above this line.")
        self.write("FAILURES.md", failures)

    def quotes(self, *args):
        return {r["quote"]: r for r in self.js("harvest", *args)["candidates"]}

    def test_own_words_listed_and_picks_left_out(self):
        self.setup_records()
        before = self.snapshot()
        res = self.js("harvest")
        got = {r["quote"] for r in res["candidates"]}
        self.assertTrue(OWN <= got, got)
        self.assertIn("we should never build reports nobody opens", got)                 # month volumes are read
        self.assertIn("that's wrong, the deadline moved to Friday, always check the calendar first", got)  # FAILURES.md too
        for pick in ("plan B", "go ahead", "keep the cap as it is for now"):
            self.assertNotIn(pick, got)
        self.assertFalse(any("freeze" in q for q in got))                               # not attributed to the user
        self.assertEqual(res["approvals"], 3)
        self.assertEqual(self.snapshot(), before)                                        # reads only: no file, no event

    def test_approvals_show_what_was_answered(self):
        self.setup_records()
        rows = self.quotes("--include-approvals")
        self.assertTrue(rows["plan B"]["approval"])
        self.assertEqual(rows["keep the cap as it is for now"]["answering"], "Keep the cap of one release a week, or lift it?")
        self.assertFalse(rows["it should work right after install"]["approval"])
        self.assertIn("answering: Keep the cap", self.cli("harvest", "--include-approvals").stdout)

    def test_review_through_the_queue_and_no_second_round(self):
        self.setup_records()
        self.cli("write", "propose", "--text", "Quote prices in one currency, USD",
                 "--source", 'user: "Always quote prices in USD, never mix currencies on one page" (LOG.md 2026-11-02)',
                 "--origin", "harvest", "--date", "2026-11-10")
        self.cli("write", "propose", "--text", "Setup needs no configuration",
                 "--source", 'user: "too many steps, people should not need to configure anything" (LOG.md 2026-11-06)',
                 "--origin", "harvest", "--date", "2026-11-10")
        self.cli("write", "reject", "--match", "no configuration", "--reason", "one-off, not a rule", "--date", "2026-11-10")
        res = self.js("harvest")
        got = {r["quote"] for r in res["candidates"]}
        self.assertNotIn("Always quote prices in USD, never mix currencies on one page", got)   # waiting in PROPOSALS.md
        self.assertNotIn("too many steps, people should not need to configure anything", got)  # rejected stays rejected
        self.assertEqual(res["known"], 2)
        self.cli("write", "promote", "--match", "one currency", "--section", "Active")
        self.assertNotIn("Always quote prices in USD, never mix currencies on one page", self.quotes())  # kept in MEMORY.md

    def test_cursor_and_speakers(self):
        self.setup_records()
        out = self.js("harvest", "--advance", "--today", "2026-11-06")
        self.assertEqual(out["advanced_to"], "2026-11-06")
        later = set(self.quotes())
        self.assertIn("it should work right after install", later)
        self.assertNotIn("Always quote prices in USD, never mix currencies on one page", later)
        self.assertNotIn("we should never build reports nobody opens", later)
        self.assertIn("Always quote prices in USD, never mix currencies on one page", self.quotes("--since", "2026-11-01"))
        self.write("NOTES.md", '- [2026-11-09] Owner said: "every reply should lead with the answer, keep it short"\n')
        self.assertEqual(set(self.quotes("--speaker", "owner", "--source", "NOTES.md", "--since", "2026-01-01")),
                         {"every reply should lead with the answer, keep it short"})


if __name__ == "__main__":
    unittest.main()
