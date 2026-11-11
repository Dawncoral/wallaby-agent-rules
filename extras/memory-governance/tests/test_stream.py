#!/usr/bin/env python3
"""Tests for the 1.4.3 write path: write, events, id, route --record with verify, the audit baseline, and upgrades.

Every test builds a synthetic project in a temporary directory; nothing touches a real project.
Run: python3 -m unittest tests.test_stream   (from extras/memory-governance/)
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE.parents[0] / "memory_governance.py"
REPO = HERE.parents[2]
TEMPLATES = REPO / "templates"
OLD_CLI_PATH = "extras/memory-governance/memory_governance.py"
PUBLISHED = {"1.4.0": "168335a", "1.4.2": "cc08db9", "1.4.3": "7e13bca", "1.4.4": "bfbc366"}   # the commits those releases were cut from
DAY = "2026-11-10"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="memory-stream-test-")
        self.root = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("WALLABY_MEMORY_")}

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, ok=True, env=None, cli=CLI):
        r = subprocess.run([sys.executable, str(cli), "--target", str(self.root), *args], text=True, capture_output=True,
                           env=dict(self.env, **(env or {})))
        if ok is True:
            self.assertEqual(r.returncode, 0, f"{args}\n{r.stdout}\n{r.stderr}")
        elif ok is not None:
            self.assertEqual(r.returncode, ok, f"{args}\n{r.stdout}\n{r.stderr}")
        return r

    def js(self, *args, ok=True, env=None):
        return json.loads(self.cli(*args, "--json", ok=ok, env=env).stdout)

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return p

    def read(self, rel):
        with open(self.root / rel, encoding="utf-8", newline="") as f:
            return f.read()

    def events(self):
        p = self.root / ".memory" / "events.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []

    def receipts(self):
        return [json.loads(x) for x in self.read(".memory/receipts.jsonl").splitlines() if x.strip()]

    def project(self, init=True):
        """The shipped templates, as a fresh install leaves them."""
        for name in ("NOW.md", "INDEX.md", "LOG.md", "MAP.md", "CAPABILITIES.md", "FAILURES.md"):
            self.write(name, (TEMPLATES / name).read_text(encoding="utf-8"))
        self.write("MEMORY.md", (REPO / "MEMORY.md").read_text(encoding="utf-8"))
        self.write("README.md", "# Demo\n\nWeekly check: `scripts/health_check.py`.\n")
        self.write("scripts/health_check.py", "print('ok')\n")
        if init:
            self.cli("init")
        return self.root

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}


class EventTests(Base):
    def test_write_without_memory_dir_changes_one_file_and_creates_nothing_else(self):
        self.project(init=False)
        before = set(self.snapshot())
        out = self.js("write", "log", "Shipped the pricing page", "--date", DAY)
        self.assertEqual(out["events"], [])
        self.assertIn("event log off", out["note"])
        self.assertIn(f"- [{DAY}] Shipped the pricing page", self.read("LOG.md"))
        self.assertEqual(set(self.snapshot()), before)

    def test_each_write_is_one_event_with_actor_hash_and_chain(self):
        self.project()
        self.cli("write", "log", "first", "--date", DAY, "--actor", "claude-code")
        self.cli("write", "log", "second", "--date", DAY, env={"WALLABY_MEMORY_ACTOR": "kimi; rm -rf"})
        self.cli("write", "log", "third", "--date", DAY)
        rows = self.events()
        self.assertEqual([r["seq"] for r in rows], [1, 2, 3])
        self.assertEqual([r["actor"] for r in rows], ["claude-code", "kimirm-rf", "cli"])
        self.assertEqual(rows[2]["sha256"], sha(self.root / "LOG.md"))
        self.assertEqual(rows[0]["prev"], "")
        lines = (self.root / ".memory/events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[1]["prev"], hashlib.sha256(lines[0].encode("utf-8")).hexdigest()[:16])
        self.assertEqual(self.cli("events", "verify").stdout.strip().splitlines()[-1], "EVENTS OK")

    def test_since_is_a_cursor(self):
        self.project()
        for word in ("one", "two", "three"):
            self.cli("write", "log", word, "--date", DAY)
        out = self.js("events", "list", "--since", "1")
        self.assertEqual([e["seq"] for e in out["events"]], [2, 3])
        self.assertNotIn("_raw", out["events"][0])
        self.assertEqual(self.js("events", "list", "--since", "3")["events"], [])

    def test_hand_edit_is_reported_then_adopted_and_never_fails_doctor(self):
        self.project()
        self.cli("write", "log", "one", "--date", DAY)
        with open(self.root / "LOG.md", "a", encoding="utf-8") as f:
            f.write("- [2026-11-10] typed by hand\n")
        st = self.js("events", "verify")
        self.assertEqual([(o["file"], o["state"]) for o in st["outside"]], [("LOG.md", "changed")])
        doctor = self.cli("doctor")
        self.assertIn("1 logged file(s) changed outside the write command: LOG.md", doctor.stdout)
        self.cli("events", "adopt", "--actor", "owner", "--note", "edited in the editor")
        self.assertEqual(self.js("events", "verify")["outside"], [])
        self.assertEqual((self.events()[-1]["event"], self.events()[-1]["actor"]), ("adopt", "owner"))
        self.assertIn("Nothing to adopt", self.cli("events", "adopt").stdout)

    def test_edited_or_removed_event_line_breaks_the_chain(self):
        self.project()
        for word in ("one", "two", "three"):
            self.cli("write", "log", word, "--date", DAY)
        path = self.root / ".memory/events.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
        r = self.cli("events", "verify", ok=1)
        self.assertIn("EVENTS BROKEN", r.stdout)
        self.assertIn("broken:", self.cli("doctor", ok=1).stdout)
        self.assertIn("broken", self.cli("events", "adopt", ok=2).stderr)

    def test_splits_and_map_sync_are_logged_so_they_do_not_look_like_hand_edits(self):
        self.project()
        log = "# LOG.md\n\n## 2026-11\n\n- [2026-11-02] nov\n\n## 2026-10\n\n- [2026-10-02] oct\n"
        self.write("LOG.md", log)
        self.cli("write", "log", "tracked", "--date", DAY)
        self.cli("map", "sync")
        self.cli("write", "map", "billing", "--keywords", "price, invoice", "--area", "Product and operations")
        tx = self.js("split", "volume", "auto", "--today", DAY, "--threshold", "10")[0]["tx"]
        self.assertEqual(self.js("events", "verify")["outside"], [])
        self.cli("split", "volume", "rollback", "--tx", tx)
        self.assertEqual(self.js("events", "verify")["outside"], [])
        kinds = {r["event"] for r in self.events()}
        self.assertTrue({"write.log", "map.sync", "split.volume", "split.volume.rollback"} <= kinds, kinds)


class IdTests(Base):
    def test_take_starts_above_every_number_already_written(self):
        self.project()
        self.write("LOG.md", "# LOG.md\n\n## 2026-11\n\n- [2026-11-01] D-007 · keep prices in USD\n")
        self.assertEqual(self.cli("id", "take", "D").stdout.strip(), "D-008")
        self.assertEqual(self.cli("id", "take", "D", "--note", "currency").stdout.strip(), "D-009")
        with open(self.root / "LOG.md", "a", encoding="utf-8") as f:
            f.write("- [2026-11-02] D-040 · written by hand\n")
        self.assertEqual(self.cli("id", "take", "D").stdout.strip(), "D-041")
        taken = [r for r in self.events() if r["event"] == "id.take"]
        self.assertEqual([r["ref"] for r in taken], ["D-008", "D-009", "D-041"])
        self.assertEqual(taken[1]["summary"], "currency")

    def test_examples_inside_comments_and_code_fences_are_not_counted(self):
        self.project()   # templates/FAILURES.md shows `### F-001` inside a code fence
        out = self.js("write", "failure", "--observed", "answered from an old note", "--expected", "read MEMORY.md first", "--date", DAY)
        self.assertEqual(out["id"], "F-001")

    def test_receipts_and_contradictions_share_the_counter(self):
        self.project()
        self.cli("impact", "--event", "document", "--terms", "no-such-term", "--record")
        self.cli("impact", "--event", "document", "--terms", "no-such-term-2", "--record")
        self.cli("contradict", "add", "--old", "a", "--new", "b", "--evidence", "c")
        self.assertEqual([r["receipt"] for r in self.receipts()], ["R-000001", "R-000002"])
        ids = [c["id"] for c in json.loads(self.read(".memory/contradictions.json"))["contradictions"]]
        self.assertEqual(ids, ["C-001", "C-002"])
        series = json.loads(self.read(".memory/ids.json"))["series"]
        self.assertEqual((series["R"]["next"], series["C"]["next"]), (3, 3))

    def test_custom_series_and_series_names(self):
        self.project()
        self.assertEqual(self.cli("id", "take", "TASK").stdout.strip(), "TASK-001")
        self.assertEqual(self.cli("id", "take", "task").stdout.strip(), "TASK-002")
        for bad in ("TOOLONG", "D1", ""):
            self.assertEqual(self.cli("id", "take", bad, ok=2).returncode, 2)
        self.assertIn("TASK  next TASK-003", self.cli("id", "list").stdout)

    def test_parallel_takes_never_collide(self):
        self.project()
        with ThreadPoolExecutor(max_workers=8) as pool:
            got = list(pool.map(lambda _: self.cli("id", "take", "D").stdout.strip(), range(16)))
        self.assertEqual(sorted(got), [f"D-{n:03d}" for n in range(1, 17)])

    def test_a_lock_left_by_a_dead_run_is_removed(self):
        self.project()
        lock = self.root / ".memory" / "ids.lock"
        lock.write_text("", encoding="utf-8")
        old = time.time() - 600
        os.utime(lock, (old, old))
        self.assertEqual(self.cli("id", "take", "D").stdout.strip(), "D-001")
        self.assertFalse(lock.exists())

    def test_audit_reports_an_id_defined_twice(self):
        self.project()
        data = json.loads(self.read(".memory/contradictions.json"))
        data["contradictions"].append(dict(data["contradictions"][0]))
        self.write(".memory/contradictions.json", json.dumps(data))
        r = self.cli("id", "audit", ok=1)
        self.assertIn("DUPLICATE duplicate C-001", r.stdout)
        self.assertIn("IDS duplicate C-001", self.cli("doctor", ok=1).stdout)


class WriteTests(Base):
    def test_log_puts_a_new_month_on_top_and_the_newest_entry_first(self):
        self.project()   # templates/LOG.md holds one month, 2026-09
        self.cli("write", "log", "older", "--date", "2026-11-09")
        self.cli("write", "log", "newer", "--date", DAY, "--source", "docs/a.md")
        text = self.read("LOG.md")
        self.assertLess(text.index("## 2026-11"), text.index("## 2026-09"))
        self.assertLess(text.index("newer — docs/a.md"), text.index("older"))
        self.assertIn("\n## 2026-11\n\n- [2026-11-10] newer", text)

    def test_log_in_an_oldest_first_file_appends(self):
        self.project()
        self.write("LOG.md", "# LOG.md\n\n## 2026-09\n\n- [2026-09-01] a\n\n## 2026-10\n\n- [2026-10-01] b\n")
        self.cli("write", "log", "c", "--date", "2026-10-05")
        self.cli("write", "log", "d", "--date", "2026-11-01")
        text = self.read("LOG.md")
        self.assertLess(text.index("- [2026-10-01] b"), text.index("- [2026-10-05] c"))
        self.assertLess(text.index("## 2026-10"), text.index("## 2026-11"))
        self.assertTrue(text.endswith("- [2026-11-01] d\n"))

    def test_log_is_created_with_its_header_and_refuses_a_closed_volume(self):
        self.project()
        (self.root / "LOG.md").unlink()
        self.cli("write", "log", "first ever", "--date", DAY)
        self.assertTrue(self.read("LOG.md").startswith("# LOG.md — dated log\n"))
        self.write("LOG.md", "# LOG.md\n\n## 2026-11\n\n- [2026-11-02] nov\n\n## 2026-10\n\n- [2026-10-02] oct\n")
        self.cli("split", "volume", "auto", "--today", DAY, "--threshold", "10")
        before = self.read("LOG.md")
        r = self.cli("write", "log", "late entry", "--date", "2026-10-20", ok=2)
        self.assertIn("closed volume", r.stderr)
        self.assertEqual(self.read("LOG.md"), before)

    def test_now_then_close_moves_the_item_in_one_action(self):
        self.project()
        self.cli("write", "now", "Pricing page rewrite", "--pointer", "docs/pricing.md", "--date", "2026-11-08")
        self.cli("write", "now", "Checkout redesign", "--pointer", "docs/checkout.md", "--date", "2026-11-09")
        r = self.cli("write", "close", "x", "--match", "re", ok=2)       # two lines match
        self.assertIn("2 line(s) in flight match", r.stderr)
        r = self.cli("write", "close", "x", "--match", "nothing like this", ok=2)
        self.assertIn("Pricing page rewrite", r.stderr)
        before = self.read("NOW.md")
        out = self.js("write", "close", "Pricing page live", "--match", "pricing page", "--pointer", "docs/pricing.md", "--date", DAY)
        self.assertEqual([f["file"] for f in out["files"]], ["LOG.md", "NOW.md"])
        now = self.read("NOW.md")
        flight = now[now.index("## In flight"):now.index("## Recently touched")]
        self.assertNotIn("Pricing page rewrite", flight)
        self.assertIn("Checkout redesign", flight)
        self.assertIn(f"- [{DAY}] Pricing page live → LOG.md", now[now.index("## Recently touched"):])
        self.assertIn(f"- [{DAY}] Pricing page live — docs/pricing.md", self.read("LOG.md"))
        self.assertEqual(len(out["events"]), 2)
        self.assertNotEqual(now, before)

    def test_now_adds_the_section_when_the_file_has_none(self):
        self.project()
        self.write("NOW.md", "# NOW.md\n\nfree text\n")
        self.cli("write", "now", "Item", "--pointer", "a.md", "--date", DAY)
        self.assertTrue(self.read("NOW.md").endswith(f"\n## In flight\n\n- [{DAY}] Item; details: a.md\n"))
        r = self.cli("write", "now", "Item", "--pointer", "a.md", "--section", "Backlog", ok=2)
        self.assertIn('no heading matches "Backlog"', r.stderr)

    def test_propose_promote_and_reject_empty_the_queue(self):
        self.project()
        self.cli("write", "propose", "Prices are quoted in USD", "--source", "docs/pricing.md", "--origin", "task-42; rm", "--date", DAY)
        self.cli("write", "propose", "Gateway key is sk-abcdefghijklmnop1234 for a@b.com", "--source", "ops/deploy.md", "--date", DAY)
        queue = self.read("PROPOSALS.md")
        self.assertIn("(proposed · from task-42rm)", queue)
        self.assertIn("[REDACTED_KEY]", queue)
        self.assertNotIn("sk-abc", queue)
        self.assertIn("already in PROPOSALS.md", self.js("write", "propose", "prices are quoted in usd", "--source", "x")["skipped"])
        self.assertEqual(self.cli("write", "propose", "no source", ok=2).returncode, 2)
        r = self.cli("write", "promote", "--match", "quoted in usd", ok=2)
        self.assertIn("name one with --section", r.stderr)
        self.assertEqual(self.read("PROPOSALS.md"), queue)
        self.cli("write", "promote", "--match", "quoted in usd", "--section", "Active")
        self.assertIn(f"- [{DAY}] Prices are quoted in USD — source: docs/pricing.md\n", self.read("MEMORY.md"))
        self.assertNotIn("(proposed", self.read("MEMORY.md"))
        self.cli("write", "reject", "--match", "gateway", "--reason", "holds a key", "--date", DAY)
        self.assertNotIn("- [", self.read("PROPOSALS.md"))
        self.assertIn("Rejected proposal: Gateway key is [REDACTED_KEY]", self.read("LOG.md"))
        self.assertIn("already in MEMORY.md", self.js("write", "propose", "Prices are quoted in USD", "--source", "x")["skipped"])

    def test_fact_goes_under_its_section_and_follows_a_topic_split(self):
        self.project()
        self.assertEqual(self.cli("write", "fact", "No source given", "--section", "Active", ok=2).returncode, 2)
        self.cli("write", "fact", "Deploys need a committed tree", "--source", "AGENTS.md", "--section", "Standby", "--date", DAY)
        text = self.read("MEMORY.md")
        standby = text[text.index("## Standby"):text.index("## Dormant")]
        self.assertIn(f"- [{DAY}] Deploys need a committed tree — source: AGENTS.md", standby)
        self.assertIn("already in MEMORY.md", self.js("write", "fact", "deploys need a committed tree", "--source", "x", "--section", "Standby")["skipped"])
        plan = self.js("split", "topic", "propose", "--file", "MEMORY.md", "--section", "Standby", "--today", DAY)[0]
        self.cli("split", "topic", "apply", "--plan-sha", plan["plan_sha"], "--confirm", "--file", "MEMORY.md",
                 "--section", "Standby", "--today", DAY)
        r = self.cli("write", "fact", "Another", "--source", "x", "--section", "Standby", ok=2)
        self.assertIn(f"write there with --file {plan['target']}", r.stderr)
        self.cli("write", "fact", "Another", "--source", "x", "--file", plan["target"], "--date", DAY)
        self.assertIn(f"- [{DAY}] Another — source: x", self.read(plan["target"]))
        self.assertEqual(self.js("split", "stub", "check")["stub"], [])

    def test_index_adds_updates_and_refuses_duplicates(self):
        self.project()
        self.cli("write", "index", "Pricing spec", "--path", "./docs/pricing.md")
        self.assertIn("| `scripts/health_check.py` |", self.read("INDEX.md"))
        self.assertIn("\n| `docs/pricing.md` | Pricing spec |\n", self.read("INDEX.md"))
        r = self.cli("write", "index", "again", "--path", "docs/pricing.md", ok=2)
        self.assertIn("already registered at INDEX.md:", r.stderr)
        self.cli("write", "index", "Pricing spec, second edition", "--path", "docs/pricing.md", "--update")
        text = self.read("INDEX.md")
        self.assertEqual(text.count("docs/pricing.md"), 1)
        self.assertIn("| `docs/pricing.md` | Pricing spec, second edition |", text)
        self.assertEqual(self.cli("write", "index", "a | b", "--path", "x.md", ok=2).returncode, 2)

    def test_index_picks_the_table_of_the_same_directory_and_handles_lists(self):
        self.project()
        self.write("INDEX.md", "# INDEX.md\n\n## docs/\n\n| File | What it is |\n|---|---|\n| `docs/a.md` | A |\n\n"
                               "## ops/\n\n| File | What it is |\n|---|---|\n| `ops/b.md` | B |\n")
        self.cli("write", "index", "C", "--path", "ops/c.md")
        text = self.read("INDEX.md")
        self.assertLess(text.index("ops/b.md"), text.index("ops/c.md"))
        self.assertLess(text.index("docs/a.md"), text.index("## ops/"))
        self.cli("write", "index", "D", "--path", "new/d.md", "--section", "docs")
        self.assertLess(self.read("INDEX.md").index("new/d.md"), self.read("INDEX.md").index("## ops/"))
        self.write("INDEX.md", "# INDEX.md\n\n- `README.md` | Overview\n")
        self.cli("write", "index", "Notes", "--path", "docs/notes.md")
        self.assertTrue(self.read("INDEX.md").endswith("- `README.md` | Overview\n- `docs/notes.md` | Notes\n"))

    def test_capability_and_map_rows_go_above_the_placeholder(self):
        self.project()
        self.write("scripts/backup.py", "print('b')\n")
        self.cli("write", "capability", "backup.py", "--entry", "scripts/backup.py", "--form", "Script",
                 "--triggers", "backup, snapshot", "--call", "`python3 scripts/backup.py`")
        caps = self.read("CAPABILITIES.md")
        row = "| `backup.py` | Script | `scripts/backup.py` | backup, snapshot | incubating | `python3 scripts/backup.py` |"
        self.assertIn(row, caps)
        self.assertLess(caps.index(row), caps.index("| `<capability>`"))
        self.assertIn("already registered", self.cli("write", "capability", "backup.py", "--entry", "x.py", ok=2).stderr)
        self.assertEqual(self.js("audit")["missing"], [])
        r = self.cli("write", "map", "billing", "--keywords", "price, invoice", ok=2)
        self.assertIn('name one with --area: "Memory and instructions", "Product and operations"', r.stderr)
        self.cli("write", "map", "billing", "--keywords", "price, invoice", "--job", "Charges customers",
                 "--details", "docs/pricing.md", "--area", "Product and operations")
        text = self.read("MAP.md")
        row = "| `billing` | Charges customers | price, invoice | `docs/pricing.md` |"
        self.assertLess(text.index(row), text.index("| `<component>`"))
        self.assertEqual(self.js("lookup", "--registry", "map", "--query", "invoice")["rows"][0]["component"], "billing")

    def test_failure_entries_take_ids_and_stay_newest_first(self):
        self.project()
        for n, kind in enumerate(("stale", "invented"), 1):
            out = self.js("write", "failure", "--kind", kind, "--trigger", "asked for the live version",
                          "--observed", f"wrong answer {n}", "--expected", "read MEMORY.md first", "--date", DAY)
            self.assertEqual(out["id"], f"F-00{n}")
        text = self.read("FAILURES.md")
        self.assertLess(text.index("### F-002 · 2026-11-10 · invented"), text.index("### F-001 · 2026-11-10 · stale"))
        self.assertLess(text.index("### F-001"), text.index("<!-- Add new entries above this line."))
        self.assertIn("- **Observed**: wrong answer 2\n- **Expected**: read MEMORY.md first\n- **Status**: open\n", text)
        self.assertNotIn("**Fix**", text[text.index("### F-002"):text.index("### F-001")])
        self.assertEqual(self.cli("write", "failure", "--observed", "only one side", ok=2).returncode, 2)

    def test_existing_bytes_survive_crlf_files_and_missing_final_newlines(self):
        self.project()
        log = "# LOG.md\r\n\r\n## 2026-11\r\n\r\n- [2026-11-01] one\r\n\r\n## 2026-10\r\n\r\n- [2026-10-01] zero"
        self.write("LOG.md", log)
        self.cli("write", "log", "two", "--date", DAY)
        text = self.read("LOG.md")
        self.assertIn("- [2026-11-10] two\r\n- [2026-11-01] one\r\n", text)
        self.assertEqual(text.replace("- [2026-11-10] two\r\n", ""), log)
        self.cli("write", "log", "minus one", "--date", "2026-09-01")   # appended after a line with no newline
        self.assertTrue(self.read("LOG.md").endswith("- [2026-10-01] zero\r\n\r\n## 2026-09\r\n\r\n- [2026-09-01] minus one\r\n"))

    def test_dry_run_writes_nothing_and_takes_no_id(self):
        self.project()
        before = self.snapshot()
        out = self.js("write", "log", "maybe", "--take", "D", "--dry-run", "--date", DAY)
        self.assertEqual((out["id"], out["dry_run"], out["events"]), ("D-?", True, []))
        self.assertEqual(out["files"][0]["added"][0]["text"], f"- [{DAY}] D-? · maybe")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.js("write", "log", "now for real", "--take", "D", "--date", DAY)["id"], "D-001")

    def test_a_refused_write_takes_no_id(self):
        self.project()
        self.cli("write", "now", "Item", "--pointer", "a.md", "--take", "D", "--section", "No such heading", ok=2)
        self.assertEqual(self.js("write", "log", "x", "--take", "D", "--date", DAY)["id"], "D-001")

    def test_text_that_starts_with_a_dash_and_batches(self):
        self.project()
        self.cli("write", "log", "--text=-5% conversion after the change", "--date", DAY)
        self.assertIn(f"- [{DAY}] -5% conversion after the change", self.read("LOG.md"))
        batch = self.write("ops.jsonl", "\n".join([
            json.dumps({"face": "log", "text": "batched one", "date": DAY}),
            json.dumps({"face": "index", "text": "Pricing spec", "path": "docs/pricing.md"}),
            json.dumps({"face": "now", "text": "no pointer"}),
            json.dumps({"face": "log", "text": "never reached", "date": DAY})]) + "\n")
        r = self.cli("write", "batch", "--file", str(batch), ok=2)
        self.assertIn("batch line 3 (now)", r.stderr)
        self.assertIn("2 entry(ies) before it were written", r.stderr)
        self.assertIn("batched one", self.read("LOG.md"))
        self.assertIn("docs/pricing.md", self.read("INDEX.md"))
        self.assertNotIn("never reached", self.read("LOG.md"))


class LoopTests(Base):
    def premises(self, level):
        return {"version": 1, "premises": [
            {"id": "P-001", "level": level, "assertion": "Pricing names one plan.", "detection": "text check",
             "failure_signal": {"type": "text_contains", "path": "docs/pricing.md", "value": "starter"},
             "status": "active", "depends_on": ["docs/pricing.md"]},
            {"id": "P-002", "level": "P1", "assertion": "An unrelated file exists.", "detection": "file check",
             "failure_signal": {"type": "file_missing", "path": "never-there.md"}, "status": "active",
             "depends_on": ["unrelated/**"]}]}

    def test_a_rename_takes_two_commands(self):
        self.project()
        self.write("docs/pricing.md", "# Pricing\n\nThe old-plan name appears here.\n")
        self.write("scripts/restore.py", "print('r')\n")
        self.write(".memory/premises.json", json.dumps(self.premises("P1")))
        card = self.js("route", "rename old-plan to starter and add a restore script", "--paths", "scripts/restore.py",
                       "docs/pricing.md", "--terms", "old-plan", "--actor", "claude-code")
        rid = card["receipt"]["id"]
        self.assertEqual((rid, card["receipt"]["matches"], card["tier"]), ("R-000001", 1, "heavy"))
        self.assertTrue(any(f"verify --receipt {rid}" in n for n in card["next"]))
        self.assertNotIn("_full", card)
        receipt = self.receipts()[0]
        self.assertEqual((receipt["source"], receipt["register"], receipt["paths"]),
                         ("route", ["scripts/restore.py"], ["scripts/restore.py", "docs/pricing.md"]))
        self.assertEqual(receipt["premises"], [{"id": "P-001", "scope": "matched"}])

        r = self.cli("verify", ok=1)
        self.assertIn(f"NOT VERIFIED {rid}: 1 unresolved and 0 unread file(s), 2 other finding(s)", r.stdout)
        self.assertIn("PREMISE P-001 P1 FAILING", r.stdout)
        self.assertIn("REGISTER scripts/restore.py is not in CAPABILITIES.md", r.stdout)

        self.write("docs/pricing.md", "# Pricing\n\nThe starter name appears here.\n")
        self.cli("write", "capability", "restore.py", "--entry", "scripts/restore.py", "--triggers", "restore, recover")
        out = self.cli("verify", "--actor", "claude-code").stdout
        self.assertIn(f"VERIFIED {rid}: zero unresolved matches", out)
        self.assertIn("REVIEW unchanged since the receipt was opened: MAP.md, INDEX.md", out)
        self.assertEqual(self.receipts()[-1]["status"], "verified")
        self.assertIn("already verified", self.cli("verify", "--receipt", rid).stdout)
        self.assertEqual(self.cli("verify").stdout.strip(), "No pending receipts.")
        kinds = [(e["event"], e.get("ref"), e["actor"]) for e in self.events() if e["event"].startswith("receipt")]
        self.assertEqual(kinds, [("receipt.open", rid, "claude-code"), ("receipt.verify", rid, "claude-code")])
        doctor = self.cli("doctor", ok=1).stdout       # red only for P-002, which this change never touched
        self.assertIn("RECEIPTS pending=0", doctor)
        self.assertIn("P-002 P1 FAILING", doctor)

    def test_a_p2_premise_warns_and_an_unmatched_one_is_left_alone(self):
        self.project()
        self.write("docs/pricing.md", "# Pricing\n\nNo plan name here.\n")
        self.write(".memory/premises.json", json.dumps(self.premises("P2")))
        self.cli("route", "change the pricing rules", "--paths", "docs/pricing.md", "--record")
        out = self.cli("verify").stdout
        self.assertIn("PREMISE P-001 P2 FAILING", out)
        self.assertNotIn("P-002", out)
        self.assertIn("VERIFIED R-000001: no old terms to scan", out)

    def test_a_light_change_opens_no_receipt(self):
        self.project()
        card = self.js("route", "fix a typo in the handbook", "--paths", "README.md", "--record")
        self.assertEqual((card["tier"], card["receipt"]), ("light", None))
        self.assertIn("not needed", card["receipt_note"])
        self.assertEqual(self.receipts(), [])
        self.assertIn("RECEIPT not needed: the tier is light", self.cli("route", "fix a typo in the handbook", "--paths", "README.md", "--record").stdout)

    def test_verify_asks_which_receipt_when_several_are_pending(self):
        self.project()
        self.cli("route", "add a billing feature", "--record")
        self.cli("route", "add a refund feature", "--record")
        r = self.cli("verify", ok=2)
        self.assertIn("2 receipts are pending; name one with --receipt", r.stderr)
        self.assertIn("R-000002 add a refund feature", r.stdout)
        self.cli("verify", "--receipt", "R-000002")
        self.cli("verify")

    def test_record_needs_the_governance_files_and_impact_receipts_work_as_before(self):
        self.write("README.md", "# x\n")
        r = self.cli("route", "add a billing feature", "--record", ok=2)
        self.assertIn("run init first", r.stderr)
        self.project()
        self.write("docs/a.md", "the old-name is here\n")
        self.cli("impact", "--event", "file_move", "--terms", "old-name", "--record")
        self.assertEqual(self.cli("verify", "--receipt", "R-000001", ok=1).returncode, 1)
        self.write("docs/a.md", "the new-name is here\n")
        self.assertIn("VERIFIED R-000001: zero unresolved matches", self.cli("verify", "--receipt", "R-000001").stdout)


class AuditBaselineTests(Base):
    def test_files_that_predate_the_pack_are_a_baseline_and_new_ones_are_findings(self):
        self.project(init=False)
        for n in range(5):
            self.write(f"scripts/legacy_{n}.py", "pass\n")
        out = self.cli("init").stdout
        self.assertIn("AUDIT baseline: 5 script, skill or workflow file(s) are not in CAPABILITIES.md yet", out)
        doctor = self.cli("doctor").stdout
        self.assertIn("AUDIT missing=0", doctor)
        self.assertIn("AUDIT baseline: 5 file(s) were unregistered before the first audit", doctor)
        self.assertIn("DOCTOR OK", doctor)
        self.write("scripts/fresh.py", "pass\n")
        rep = self.js("audit", ok=1)
        self.assertEqual([f["item"] for f in rep["missing"]], ["scripts/fresh.py"])
        self.assertEqual(len(rep["baselined"]), 5)
        self.cli("write", "capability", "legacy_0.py", "--entry", "scripts/legacy_0.py")
        (self.root / "scripts/legacy_1.py").unlink()
        self.assertEqual(len(self.js("audit", ok=1)["baselined"]), 3)
        self.assertIn("AUDIT baseline reset: 4 unregistered file(s)", self.cli("audit", "--rebaseline").stdout)
        self.assertEqual(self.js("audit")["total"], 0)

    def test_the_baseline_waits_for_capabilities_md(self):
        self.write("README.md", "# x\n")
        self.write("scripts/tool.py", "pass\n")
        self.cli("init")
        self.assertFalse((self.root / ".memory/audit_baseline.json").exists())
        self.cli("doctor", ok=None)
        self.assertFalse((self.root / ".memory/audit_baseline.json").exists())
        self.write("CAPABILITIES.md", (TEMPLATES / "CAPABILITIES.md").read_text(encoding="utf-8").replace(
            "| `health_check.py` | Script | `scripts/health_check.py` | tidy up, stale files, index drift | active "
            "| `python3 scripts/health_check.py`; findings with exit code 1 |\n", ""))
        rep = self.js("audit")
        self.assertEqual((rep["missing"], rep["baselined"]), ([], ["scripts/tool.py"]))
        self.assertEqual(self.cli("audit", "--rebaseline").returncode, 0)


class UpgradeTests(Base):
    """A project built by a published CLI must come through an upgrade with every byte it had."""

    def old_cli(self, version):
        r = subprocess.run(["git", "-C", str(REPO), "show", f"{PUBLISHED[version]}:{OLD_CLI_PATH}"], capture_output=True)
        if r.returncode != 0 or f'VERSION = "{version}"'.encode() not in r.stdout:
            self.skipTest(f"the {version} CLI is not in this checkout's git history")
        path = Path(self.tmp.name).parent / f"mg-{version}-{os.getpid()}.py"
        path.write_bytes(r.stdout)
        self.addCleanup(lambda: path.exists() and path.unlink())
        return path

    def build_with(self, old):
        self.project(init=False)
        self.write("docs/a.md", "old-name lives here\n")
        self.cli("init", cli=old)
        installed = self.root / "scripts" / "memory_governance.py"
        self.cli("impact", "--event", "file_move", "--terms", "old-name", "--record", cli=installed)
        self.cli("impact", "--event", "document", "--terms", "another-term", "--record", cli=installed)
        self.cli("contradict", "add", "--old", "INDEX.md is optional", "--new", "INDEX.md is updated on every add",
                 "--evidence", "DECISION-42", cli=installed)
        return installed

    def check_upgrade(self, version):
        installed = self.build_with(self.old_cli(version))
        before = self.snapshot()
        old_receipts = [r["receipt"] for r in self.receipts()]
        self.assertEqual(old_receipts, ["R-000001", "R-000001"])   # 1.4.0 to 1.4.2 repeated the first ID

        out = self.cli("upgrade", "--source", str(CLI)).stdout     # the dry run changes nothing
        self.assertIn("DRY RUN", out)
        self.assertEqual(self.snapshot(), before)
        self.cli("upgrade", "--source", str(CLI), "--apply")
        after = self.snapshot()
        changed = sorted(k for k in after if after[k] != before.get(k))
        self.assertEqual(changed, [f".memory/backups/memory_governance_{version}.py", "scripts/memory_governance.py"])
        self.assertEqual(after[f".memory/backups/memory_governance_{version}.py"], before["scripts/memory_governance.py"])
        self.assertEqual(sorted(set(before) - set(after)), [])

        # the new commands work on the old data and only ever add to it
        self.assertIn("DOCTOR", self.cli("doctor", ok=None, cli=installed).stdout)
        self.cli("impact", "--event", "document", "--terms", "third-term", "--record", cli=installed)
        self.cli("contradict", "add", "--old", "x", "--new", "y", "--evidence", "z", cli=installed)
        self.cli("write", "log", "Upgraded the governance CLI", "--date", DAY, cli=installed)
        self.assertEqual(self.cli("id", "take", "D", cli=installed).stdout.strip(), "D-001")
        self.assertIn("EVENTS OK", self.cli("events", "verify", cli=installed).stdout)
        note = self.cli("id", "audit", cli=installed).stdout
        self.assertIn("1 receipt ID(s) were issued more than once by 1.4.0 to 1.4.2 and stay as they are: R-000001", note)

        final = self.snapshot()
        self.assertTrue(final[".memory/receipts.jsonl"].startswith(before[".memory/receipts.jsonl"]))
        self.assertEqual([r["receipt"] for r in self.receipts()], ["R-000001", "R-000001", "R-000002"])
        old_c = json.loads(before[".memory/contradictions.json"])["contradictions"]
        new_c = json.loads(final[".memory/contradictions.json"])["contradictions"]
        self.assertEqual(new_c[:len(old_c)], old_c)
        self.assertEqual([c["id"] for c in new_c], ["C-001", "C-002", "C-003"])
        untouched = [k for k in before if k not in (".memory/receipts.jsonl", ".memory/contradictions.json", "LOG.md",
                                                    "scripts/memory_governance.py")]
        self.assertEqual([k for k in untouched if final[k] != before[k]], [])
        self.assertIn(before["LOG.md"].decode("utf-8").split("## 2026-09")[1], final["LOG.md"].decode("utf-8"))
        added = sorted(set(final) - set(before))
        self.assertEqual(added, [".memory/audit_baseline.json", f".memory/backups/memory_governance_{version}.py",
                                 ".memory/events.jsonl", ".memory/ids.json", ".memory/rules_baseline.json"])

    def test_upgrade_from_published_1_4_2(self):
        self.check_upgrade("1.4.2")

    def test_upgrade_from_published_1_4_0(self):
        self.check_upgrade("1.4.0")

    def test_upgrade_from_published_1_4_3(self):
        self.check_recent_upgrade("1.4.3")

    def test_upgrade_from_published_1_4_4(self):
        self.check_recent_upgrade("1.4.4")

    def check_recent_upgrade(self, version):
        old = self.old_cli(version)
        self.project(init=False)
        self.cli("init", cli=old)
        installed = self.root / "scripts" / "memory_governance.py"
        self.cli("write", "log", "Built with 1.4.3", "--source", "test", "--date", DAY, cli=installed)
        self.cli("route", "rename old-name to new-name", "--paths", "NOW.md", "--terms", "old-name", "--record", cli=installed)
        self.assertEqual(self.cli("id", "take", "D", cli=installed).stdout.strip(), "D-001")
        before = self.snapshot()
        self.assertIn("DRY RUN", self.cli("upgrade", "--source", str(CLI)).stdout)
        self.assertEqual(self.snapshot(), before)
        self.cli("upgrade", "--source", str(CLI), "--apply")
        after = self.snapshot()
        changed = sorted(k for k in after if after[k] != before.get(k))
        self.assertEqual(changed, [f".memory/backups/memory_governance_{version}.py", "scripts/memory_governance.py"])
        self.assertEqual(after[f".memory/backups/memory_governance_{version}.py"], before["scripts/memory_governance.py"])
        # the current commands work on the older data, and the old records stay as they were
        self.assertIn("DOCTOR", self.cli("doctor", ok=None, cli=installed).stdout)
        self.assertIn("no PROFILE.md", self.cli("profile", "check", cli=installed).stdout)
        self.assertIn("no goals", json.loads(self.cli("lookup", "--registry", "goal", "--json", cli=installed).stdout)["note"])
        self.assertEqual(self.cli("id", "take", "D", cli=installed).stdout.strip(), "D-002")
        self.assertIn("EVENTS OK", self.cli("events", "verify", cli=installed).stdout)

    def test_upgrade_keeps_the_doctor_result_for_files_that_are_not_ours(self):
        old = self.old_cli("1.4.3")
        self.project(init=False)
        self.write("PROFILE.md", "# My profile\n\nI like tea.\n")                    # a file of the user's own
        self.write("LOG.md", self.read("LOG.md") + "- [2026-11-01] Hit the Q4 goal: G2 milestone\n")
        self.cli("init", cli=old)
        installed = self.root / "scripts" / "memory_governance.py"
        before = self.cli("doctor", ok=None, cli=installed).returncode
        self.cli("upgrade", "--source", str(CLI), "--apply")
        self.assertEqual(self.cli("doctor", ok=None, cli=installed).returncode, before)

    def test_old_data_shapes_are_read_as_they_are(self):
        """The same check without git: the files below are what 1.4.0 to 1.4.2 left on disk."""
        self.project(init=False)
        self.write(".memory/impact.json", json.dumps({"version": 1, "events": {
            "document": {"surfaces": ["INDEX.md"], "premise_review": False, "contradiction_review": False}}}))
        self.write(".memory/premises.json", json.dumps({"version": 1, "premises": [
            {"id": "P-001", "level": "P2", "assertion": "README exists.", "detection": "check",
             "failure_signal": {"type": "file_missing", "path": "README.md"}, "status": "active"}]}))
        self.write(".memory/contradictions.json", json.dumps({"version": 1, "contradictions": [
            {"id": "C-001", "old": "a", "new": "b", "evidence": "c", "status": "resolved", "history": []},
            {"id": "C-007", "old": "d", "new": "e", "evidence": "f", "status": "resolved", "history": []}]}))
        old_rows = ('{"type": "impact", "receipt": "R-000001", "event": "document", "terms": ["x-term"], "matches": [], '
                    '"truncated": false, "skipped": [], "surfaces": ["INDEX.md"], "status": "pending", "ts": "2026-10-30T00:00:00+00:00"}\n'
                    '{"type": "verification", "receipt": "R-000001", "status": "verified", "evidence": "zero unresolved matches", '
                    '"ts": "2026-10-30T00:01:00+00:00"}\n'
                    '{"type": "impact", "receipt": "R-000001", "event": "document", "terms": ["y-term"], "matches": [], '
                    '"truncated": false, "skipped": [], "surfaces": ["INDEX.md"], "status": "pending", "ts": "2026-10-31T00:00:00+00:00"}\n')
        self.write(".memory/receipts.jsonl", old_rows)
        before = self.snapshot()
        self.assertIn("DOCTOR OK", self.cli("doctor").stdout)
        self.cli("contradict", "add", "--old", "g", "--new", "h", "--evidence", "i")
        self.cli("impact", "--event", "document", "--terms", "z-term", "--record")
        ids = [c["id"] for c in json.loads(self.read(".memory/contradictions.json"))["contradictions"]]
        self.assertEqual(ids, ["C-001", "C-007", "C-008"])
        self.assertTrue(self.read(".memory/receipts.jsonl").startswith(old_rows))
        self.assertEqual(self.receipts()[-1]["receipt"], "R-000002")
        after = self.snapshot()
        same = [k for k in before if k not in (".memory/contradictions.json", ".memory/receipts.jsonl")]
        self.assertEqual([k for k in same if after[k] != before[k]], [])


if __name__ == "__main__":
    unittest.main()
