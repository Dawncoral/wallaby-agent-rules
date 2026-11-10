#!/usr/bin/env python3
"""Tests for the 1.4.3 closed loop: route, lookup, audit, map sync, split, and the readers that follow splits.

Every test builds a synthetic project in a temporary directory; nothing touches a real project.
Run: python3 -m unittest tests.test_closed_loop   (from extras/memory-governance/)
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE.parents[0] / "memory_governance.py"
REPO = HERE.parents[2]
HEALTH = REPO / "templates" / "health_check.py"
RECONCILE = REPO / "templates" / "reconcile.py"
TODAY = "2026-11-09"

CAPS = """<!-- wallaby-agent-rules 1.4.0 -->
# CAPABILITIES.md — reusable capabilities

## Capabilities

| Capability | Form | Entry point | Trigger words | State | Call / output |
|---|---|---|---|---|---|
| `backup.py` | Script | `scripts/backup.py` | backup, snapshot, 备份 | active | `python3 scripts/backup.py` |
| `old_dump.sh` | Script | `scripts/old_dump.sh` | dump | retired | replaced by `backup.py` |
| `<capability>` | `<form>` | `<path>` | `<words>` | `<state>` | `<call>` |
"""
MAP = """<!-- wallaby-agent-rules 1.4.0 -->
# MAP.md — the system map

## Memory and instructions

| Component | Job | Change keywords | Details |
|---|---|---|---|
| `INDEX.md` | File lookup | files, documents | `INDEX.md` |

## Operations

| Component | Job | Change keywords | Details |
|---|---|---|---|
| `backups` | Nightly backups | backup, restore | `docs/backup.md` |
| `<component>` | `<one sentence>` | `<words>` | `<path>` |
"""
INDEX = """<!-- wallaby-agent-rules 1.0.1 -->
# INDEX.md — the project map

| File | What it is |
|---|---|
| `README.md` | Project overview |
| `docs/backup.md` | How backups run and how to restore |
"""


def log_text(months, per_month=12, newest_first=True, trailing_newline=True):
    lines = ["<!-- wallaby-agent-rules 1.0.1 -->", "# LOG.md — dated log", "",
             "> Append-only. Newest entry on top.", ""]
    for m in (sorted(months, reverse=True) if newest_first else sorted(months)):
        lines += [f"## {m}", ""]
        days = range(per_month, 0, -1)
        lines += [f"- [{m}-{d:02d}] entry {d} of {m} — `docs/backup.md`" for d in days] + [""]
    text = "\n".join(lines)
    return text + "\n" if trailing_newline else text.rstrip("\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="memory-loop-test-")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(CLI), "--target", str(self.root), *args], text=True, capture_output=True)
        if ok is True:
            self.assertEqual(r.returncode, 0, f"{args}\n{r.stdout}\n{r.stderr}")
        elif ok is not None:
            self.assertEqual(r.returncode, ok, f"{args}\n{r.stdout}\n{r.stderr}")
        return r

    def js(self, *args, ok=True):
        return json.loads(self.cli(*args, "--json", ok=ok).stdout)

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def read(self, rel):
        with open(self.root / rel, encoding="utf-8", newline="") as f:
            return f.read()

    def project(self):
        self.write("README.md", "# Demo\n\nNightly backups: `scripts/backup.py`.\n")
        self.write("CAPABILITIES.md", CAPS)
        self.write("MAP.md", MAP)
        self.write("INDEX.md", INDEX)
        self.write("docs/backup.md", "# Backups\n\nRun backup.py nightly.\n")
        self.write("scripts/backup.py", "print('backup')\n")
        self.cli("init")
        return self.root

    def snapshot(self, *rels):
        out = {}
        for rel in rels:
            p = self.root / rel
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file():
                        out[f.relative_to(self.root).as_posix()] = f.read_bytes()
            elif p.is_file():
                out[rel] = p.read_bytes()
        return out


class RouteTests(Base):
    def test_route_reuses_registered_capability_and_finds_component(self):
        self.project()
        card = self.js("route", "change the nightly backup schedule", "--paths", "scripts/backup.py")
        self.assertEqual(card["reuse"][0]["capability"], "backup.py")
        self.assertEqual(card["components"][0]["component"], "backups")
        self.assertEqual(card["components"][0]["area"], "Operations")
        self.assertIn("automation", [e["event"] for e in card["events"]])
        self.assertEqual(card["tier"], "heavy")

    def test_route_names_unregistered_script(self):
        self.project()
        self.write("scripts/restore.py", "print('restore')\n")
        card = self.js("route", "add a restore script", "--paths", "scripts/restore.py")
        self.assertEqual(card["register"], ["scripts/restore.py"])
        self.assertTrue(any("register in CAPABILITIES.md" in n for n in card["next"]))

    def test_retired_capability_points_at_replacement(self):
        self.project()
        card = self.js("route", "run a dump of the database")
        retired = [r for r in card["reuse"] if r["capability"] == "old_dump.sh"]
        self.assertTrue(retired and "replaced by" in retired[0]["call"] and "note" in retired[0])

    def test_light_tier_only_when_every_condition_holds(self):
        self.project()
        card = self.js("route", "fix a typo in the backup docs", "--paths", "docs/backup.md")
        self.assertEqual(card["tier"], "light", card["tier_reasons"])
        card = self.js("route", "fix a typo and delete the old backup docs", "--paths", "docs/backup.md")
        self.assertEqual(card["tier"], "heavy")
        self.assertTrue(any(r.startswith("risk:") for r in card["tier_reasons"]))
        card = self.js("route", "write a blog post about backups")
        self.assertEqual(card["tier"], "heavy")
        self.assertTrue(any("always heavy" in r for r in card["tier_reasons"]))
        card = self.js("route", "something vague")
        self.assertEqual(card["tier"], "heavy")
        self.assertIn("no event type matched; name one with --event", card["tier_reasons"])

    def test_declared_reversible_single_area_unlocks_light(self):
        self.project()
        args = ("route", "change the backup script output", "--paths", "scripts/backup.py")
        self.assertEqual(self.js(*args)["tier"], "heavy")
        self.assertEqual(self.js(*args, "--reversible", "--single-area")["tier"], "light")

    def test_components_in_two_areas_stay_heavy(self):
        self.project()
        card = self.js("route", "fix wording", "--paths", "docs/backup.md", "INDEX.md", "--reversible", "--single-area")
        self.assertEqual(card["tier"], "heavy")
        self.assertTrue(any("map areas" in r for r in card["tier_reasons"]))

    def test_premises_filtered_by_depends_on_and_unscoped_always_listed(self):
        self.project()
        premises = {"version": 1, "premises": [
            {"id": "P-001", "level": "P1", "assertion": "Backups write to docs/backup.md's target.", "detection": "manual",
             "failure_signal": {"type": "file_missing", "path": "scripts/backup.py"}, "status": "active",
             "depends_on": ["scripts/backup.py"]},
            {"id": "P-002", "level": "P2", "assertion": "Pricing lives in one file.", "detection": "manual",
             "failure_signal": {"type": "file_missing", "path": "README.md"}, "status": "active",
             "depends_on": ["pricing/**"]},
            {"id": "P-003", "level": "P2", "assertion": "README is the entry point.", "detection": "manual",
             "failure_signal": {"type": "file_missing", "path": "README.md"}, "status": "active"},
        ]}
        self.write(".memory/premises.json", json.dumps(premises))
        card = self.js("route", "change backup rules", "--paths", "scripts/backup.py")
        got = {p["id"]: p["scope"] for p in card["premises"]}
        self.assertEqual(got, {"P-001": "matched", "P-003": "unscoped"})
        card = self.js("route", "change backup rules")
        self.assertEqual({p["id"] for p in card["premises"]}, {"P-001", "P-002", "P-003"})

    def test_match_rules_in_impact_json_override_defaults(self):
        self.project()
        impact = json.loads(self.read(".memory/impact.json"))
        impact["events"]["document"]["match"] = {"words": ["handbook"], "paths": []}
        self.write(".memory/impact.json", json.dumps(impact))
        events = [e["event"] for e in self.js("route", "update the docs")["events"]]
        self.assertNotIn("document", events)
        events = [e["event"] for e in self.js("route", "update the handbook")["events"]]
        self.assertIn("document", events)

    def test_route_works_without_governance_config(self):
        self.write("README.md", "# x\n")
        card = self.js("route", "fix a typo in the docs", "--paths", "README.md")
        self.assertEqual(card["config"], "built-in defaults")
        self.assertEqual(card["tier"], "light")

    def test_default_card_fits_the_budget(self):
        self.project()
        rows = "".join(f"| `tool{i}.py` | Script | `scripts/tool{i}.py` | backup, tool {i} | active | `python3 scripts/tool{i}.py` |\n"
                       for i in range(40))
        self.write("CAPABILITIES.md", CAPS + rows)
        text = self.cli("route", "change the backup flow", "--paths", "scripts/backup.py").stdout
        self.assertLessEqual(len(text.encode("utf-8")), 2048 + 1)
        self.assertIn("MORE", text)
        detail = self.cli("route", "change the backup flow", "--paths", "scripts/backup.py", "--detail").stdout
        self.assertGreater(len(detail), len(text))


class LookupTests(Base):
    def test_lookup_capability_status_and_map(self):
        self.project()
        out = self.js("lookup", "--registry", "capability", "--query", "snapshot")
        self.assertEqual([r["capability"] for r in out["rows"]], ["backup.py"])
        out = self.js("lookup", "--registry", "capability", "--status", "retired")
        self.assertEqual([r["capability"] for r in out["rows"]], ["old_dump.sh"])
        out = self.js("lookup", "--registry", "map", "--query", "restore", "--detail")
        self.assertEqual(out["rows"][0]["job"], "Nightly backups")

    def test_lookup_without_file_says_so(self):
        out = self.js("lookup", "--registry", "map")
        self.assertEqual(out["rows"], [])
        self.assertIn("no MAP.md", out["note"])


class AuditTests(Base):
    def test_clean_project_audits_green(self):
        self.project()
        self.assertEqual(self.cli("audit").returncode, 0)

    def test_missing_ghost_orphan(self):
        self.project()
        self.write("scripts/restore.py", "print(1)\n")
        self.write("skills/triage/SKILL.md", "---\nname: triage\n---\n")
        caps = CAPS.replace("| `<capability>`",
                            "| `report.py` | Script | `scripts/report.py` | report | active | `python3 scripts/report.py` |\n"
                            "| `lonely.py` | Script | `tools/lonely.py` | lonely | active | `python3 tools/lonely.py` |\n| `<capability>`")
        self.write("CAPABILITIES.md", caps)
        self.write("tools/lonely.py", "pass\n")
        rep = self.js("audit", ok=1)
        self.assertEqual(sorted(f["item"] for f in rep["missing"]), ["scripts/restore.py", "skills/triage/SKILL.md"])
        self.assertTrue(any("scripts/report.py" in f["detail"] for f in rep["ghost"]))
        self.assertTrue(any("lonely.py" in f["item"] for f in rep["orphan"]))
        self.assertFalse(any("backup.py" in f["item"] for f in rep["orphan"]))

    def test_scaffolding_scripts_are_exempt(self):
        self.project()
        rep = self.js("audit")
        self.assertFalse(any("memory_governance.py" in f["item"] for f in rep["missing"]))

    def test_map_ghost_path(self):
        self.project()
        (self.root / "docs" / "backup.md").unlink()
        rep = self.js("audit", ok=1)
        self.assertTrue(any("docs/backup.md" in f["detail"] for f in rep["ghost"]))

    def test_without_registries_checks_are_skipped(self):
        self.write("README.md", "x\n")
        rep = self.js("audit")
        self.assertEqual(len(rep["skipped"]), 2)
        self.assertEqual(rep["total"], 0)

    def test_doctor_reports_audit_and_map(self):
        self.project()
        out = self.cli("doctor").stdout
        self.assertIn("AUDIT missing=0 ghost=0 orphan=0 stub=0 volume=0", out)
        self.assertIn("MAP no_region", out)
        self.write("scripts/restore.py", "print(1)\n")
        r = self.cli("doctor", ok=1)
        self.assertIn("AUDIT missing=1", r.stdout)

    def test_impact_lists_components_and_capabilities_in_receipt(self):
        self.project()
        out = self.cli("impact", "--event", "automation", "--terms", "backup.py", "--record").stdout
        self.assertIn("COMPONENTS backups", out)
        self.assertIn("CAPABILITIES backup.py", out)
        rows = [json.loads(x) for x in self.read(".memory/receipts.jsonl").splitlines() if x.strip()]
        self.assertEqual(rows[-1]["components"], ["backups"])
        self.assertIn("backup.py", rows[-1]["capabilities"])

    def test_receipt_ids_increase(self):
        self.project()
        self.cli("impact", "--event", "document", "--terms", "nothing-matches-this", "--record")
        self.cli("impact", "--event", "document", "--terms", "nothing-matches-either", "--record")
        ids = [json.loads(x)["receipt"] for x in self.read(".memory/receipts.jsonl").splitlines() if x.strip()]
        self.assertEqual(ids, ["R-000001", "R-000002"])


class MapTests(Base):
    def test_sync_writes_block_outside_human_rows_and_check_detects_drift(self):
        self.project()
        before = self.read("MAP.md")
        self.assertEqual(self.js("map", "sync", "--check")["status"], "no_region")
        out = self.cli("map", "sync").stdout
        self.assertIn("MAP updated", out)
        after = self.read("MAP.md")
        self.assertTrue(after.startswith(before.rstrip("\n")))
        self.assertIn("<!-- map:auto:begin", after)
        self.assertIn("| `scripts/` | 2 |", after)
        self.assertEqual(self.cli("map", "sync", "--check").returncode, 0)
        self.assertIn("MAP unchanged", self.cli("map", "sync").stdout)
        self.write("scripts/restore.py", "print(1)\n")
        # a new file only moves the counts: that is not drift, and it does not turn doctor red
        state = self.js("map", "sync", "--check")
        self.assertEqual((state["status"], state["counts_stale"]), ("ok", True))
        # a new top-level directory changes the structure: that is drift
        self.write("api/handler.py", "pass\n")
        self.assertEqual(self.cli("map", "sync", "--check", ok=1).returncode, 1)
        self.assertIn("MAP drift", self.cli("doctor", ok=1).stdout)

    def test_suggestions_are_paste_ready(self):
        self.project()
        self.write("scripts/restore.py", "print(1)\n")
        self.write("api/handler.py", "pass\n")
        sugg = self.js("map", "sync")["suggestions"]
        self.assertIn("| `restore.py` | Script | `scripts/restore.py` | <trigger words> | incubating | `python3 scripts/restore.py` |",
                      sugg["capabilities_add"])
        self.assertIn("| `api/` | <one sentence> | <change keywords> | `api/` |", sugg["map_add"])

    def test_suggest_retire_for_ghost_entry(self):
        self.project()
        (self.root / "scripts" / "backup.py").unlink()
        sugg = self.js("map", "sync")["suggestions"]
        self.assertTrue(any("| retired |" in row and "backup.py" in row for row in sugg["capabilities_retire"]))


class VolumeTests(Base):
    def setUp(self):
        super().setUp()
        self.write("README.md", "# x\n")

    def plan(self, *extra):
        return self.js("split", "volume", "plan", "--today", TODAY, "--threshold", "100", *extra)

    def test_small_or_single_month_logs_are_not_cut(self):
        self.write("LOG.md", log_text(["2026-11"]))
        plan = self.js("split", "volume", "plan", "--today", TODAY)
        self.assertFalse(plan["eligible"])
        self.assertTrue(any("threshold" in r for r in plan["reasons"]))
        self.assertTrue(any("no finished month" in r for r in plan["reasons"]))

    def test_apply_needs_the_current_plan_sha(self):
        self.write("LOG.md", log_text(["2026-10", "2026-11"]))
        plan = self.plan()
        self.write("LOG.md", log_text(["2026-10", "2026-11"], per_month=13))
        r = self.cli("split", "volume", "apply", "--plan-sha", plan["plan_sha"], "--today", TODAY, "--threshold", "100", ok=2)
        self.assertIn("plan changed", r.stderr)

    def test_mixed_order_is_refused(self):
        text = log_text(["2026-09", "2026-10", "2026-11"])
        head, rest = text.split("## 2026-11", 1)
        nov, older = rest.split("## 2026-10", 1)
        self.write("LOG.md", head + "## 2026-10" + older + "## 2026-11" + nov)
        mixed = self.read("LOG.md").replace("## 2026-09", "## 2026-12", 1)
        self.write("LOG.md", mixed)
        plan = self.plan()
        self.assertFalse(plan["eligible"])
        self.assertTrue(any("out of order" in r for r in plan["reasons"]))

    def test_cr_line_endings_are_refused(self):
        self.write("LOG.md", log_text(["2026-10", "2026-11"]).replace("\n", "\r\n"))
        self.assertTrue(any("CR line endings" in r for r in self.plan()["reasons"]))

    def test_tampered_volume_is_reported(self):
        self.write("LOG.md", log_text(["2026-10", "2026-11"]))
        self.js("split", "volume", "auto", "--today", TODAY, "--threshold", "100")
        vol = self.root / "LOG" / "2026-10.md"
        vol.write_text(vol.read_text(encoding="utf-8") + "- [2026-10-31] sneaked in\n", encoding="utf-8")
        r = self.cli("split", "volume", "verify", ok=1)
        self.assertIn("a volume was edited", r.stdout)
        self.cli("init")
        self.assertIn("volume=1", self.cli("doctor", ok=1).stdout)

    def test_next_month_merges_and_keeps_full_view(self):
        self.write("LOG.md", log_text(["2026-09", "2026-10", "2026-11"]))
        view_a = self.read("LOG.md")
        self.js("split", "volume", "auto", "--today", TODAY, "--threshold", "100")
        main = self.read("LOG.md")
        new = main.replace("## 2026-11\n", "## 2026-12\n\n- [2026-12-01] december\n\n## 2026-11\n", 1)
        self.write("LOG.md", new)
        rows = self.js("split", "volume", "auto", "--today", "2026-12-02", "--threshold", "100")
        self.assertEqual(rows[0]["result"], "cut")
        self.assertEqual(rows[0]["months"], ["2026-11"])
        expected = view_a.replace("## 2026-11\n", "## 2026-12\n\n- [2026-12-01] december\n\n## 2026-11\n", 1)
        self.assertEqual(self.full_view(), expected)
        self.assertEqual(sorted(p.name for p in (self.root / "LOG").iterdir()), ["2026-09.md", "2026-10.md", "2026-11.md"])

    def full_view(self):
        sys.path.insert(0, str(CLI.parent))
        import memory_governance as mg
        return mg.full_view(self.root / "LOG.md")

    def test_other_files_need_a_reviewed_plan_first(self):
        self.write("docs/notes.md", log_text(["2026-10", "2026-11"]))
        rows = self.js("split", "volume", "auto", "--today", TODAY, "--threshold", "100")
        self.assertEqual(rows, [])
        plan = self.js("split", "volume", "plan", "--file", "docs/notes.md", "--today", TODAY, "--threshold", "100")
        self.cli("split", "volume", "apply", "--file", "docs/notes.md", "--plan-sha", plan["plan_sha"],
                 "--today", TODAY, "--threshold", "100")
        self.assertTrue((self.root / "docs" / "notes" / "2026-10.md").is_file())
        self.assertIn("`notes/2026-10.md`", self.read("docs/notes.md"))
        self.assertEqual(self.cli("split", "volume", "verify").returncode, 0)


class TopicTests(Base):
    def memory(self, dormant=70):
        lines = ["<!-- wallaby-agent-rules 1.0.1 -->", "# Memory", ""]
        for sec, n in (("Active", 60), ("Standby", 40), ("Dormant", dormant)):
            lines += [f"## {sec}", ""] + [f"- [2026-0{1 + i % 9}-1{i % 10}] {sec} fact {i}" for i in range(n)] + [""]
        self.write("MEMORY.md", "\n".join(lines) + "\n")
        self.write("INDEX.md", INDEX)

    def test_within_budget_nominates_nothing(self):
        self.memory(dormant=5)
        self.assertEqual(self.js("split", "topic", "propose", "--today", TODAY), [])

    def test_apply_needs_confirm_and_rollback_restores_bytes(self):
        self.memory()
        before = self.snapshot("MEMORY.md", "INDEX.md")
        noms = self.js("split", "topic", "propose", "--today", TODAY)
        self.assertEqual([n["section"] for n in noms], ["Dormant"])
        sha = noms[0]["plan_sha"]
        r = self.cli("split", "topic", "apply", "--plan-sha", sha, "--today", TODAY, ok=2)
        self.assertIn("--confirm", r.stderr)
        self.assertEqual(self.snapshot("MEMORY.md", "INDEX.md"), before)
        m = self.js("split", "topic", "apply", "--plan-sha", sha, "--confirm", "--today", TODAY)
        mem = self.read("MEMORY.md")
        self.assertIn("## Dormant\n<!-- pointer-stub -->\n> Moved to `MEMORY/dormant.md` on 2026-11-09.", mem)
        self.assertNotIn("Dormant fact 3", mem)
        self.assertIn("Dormant fact 3", self.read("MEMORY/dormant.md"))
        self.assertIn("| `MEMORY/dormant.md` |", self.read("INDEX.md"))
        self.assertEqual(self.cli("split", "stub", "check").returncode, 0)
        self.cli("split", "topic", "rollback", "--tx", m["tx"])
        self.assertEqual(self.snapshot("MEMORY.md", "INDEX.md"), before)
        self.assertFalse((self.root / "MEMORY").exists())

    def test_rollback_keeps_lines_written_to_the_topic_file(self):
        self.memory()
        sha = self.js("split", "topic", "propose", "--today", TODAY)[0]["plan_sha"]
        m = self.js("split", "topic", "apply", "--plan-sha", sha, "--confirm", "--today", TODAY)
        p = self.root / "MEMORY" / "dormant.md"
        p.write_text(p.read_text(encoding="utf-8") + "- [2026-11-09] written after the split\n", encoding="utf-8")
        self.cli("split", "topic", "rollback", "--tx", m["tx"])
        self.assertIn("written after the split", self.read("MEMORY.md"))

    def test_stub_with_body_text_is_flagged(self):
        self.memory()
        sha = self.js("split", "topic", "propose", "--today", TODAY)[0]["plan_sha"]
        self.js("split", "topic", "apply", "--plan-sha", sha, "--confirm", "--today", TODAY)
        mem = self.read("MEMORY.md").replace("do not write here.\n", "do not write here.\n- [2026-11-09] a new fact\n", 1)
        self.write("MEMORY.md", mem)
        r = self.cli("split", "stub", "check", ok=1)
        self.assertIn("stub carries text besides its pointer", r.stdout)
        self.assertIn("stub=1", self.cli("audit", ok=1).stdout.replace("STUB 1", "stub=1"))

    def test_flat_index_run_split_and_rollback(self):
        rows = "".join(f"| `src/mod{i:03d}.md` | module {i} notes |\n" for i in range(320))
        self.write("INDEX.md", INDEX + rows)
        before = self.snapshot("INDEX.md")
        noms = self.js("split", "topic", "propose", "--today", TODAY)
        self.assertEqual([(n["kind"], n["section"], n["target"]) for n in noms], [("rows", "src/", "INDEX/src.md")])
        m = self.js("split", "topic", "apply", "--plan-sha", noms[0]["plan_sha"], "--confirm", "--today", TODAY)
        idx = self.read("INDEX.md")
        self.assertIn("| `INDEX/src.md` | Index part: 320 rows for `src/`, split on 2026-11-09 |", idx)
        self.assertNotIn("mod007", idx)
        self.assertIn("mod007", self.read("INDEX/src.md"))
        self.cli("split", "topic", "rollback", "--tx", m["tx"])
        self.assertEqual(self.snapshot("INDEX.md"), before)


class ReaderTests(Base):
    def run_script(self, script, *args):
        return subprocess.run([sys.executable, str(script), str(self.root), *args], text=True, capture_output=True)

    def test_reconcile_reads_month_volumes(self):
        self.write("NOW.md", "# NOW\n\n## In flight\n\n- [2026-11-01] gateway migration\n\n## Recently touched\n")
        log = log_text(["2026-10", "2026-11"]).replace("- [2026-10-12] entry 12 of 2026-10 — `docs/backup.md`",
                                                         "- [2026-10-12] gateway migration shipped")
        self.write("LOG.md", log)
        self.js("split", "volume", "auto", "--today", TODAY, "--threshold", "100")
        self.assertNotIn("gateway migration shipped", self.read("LOG.md"))
        r = self.run_script(RECONCILE, "--days", "100000")
        self.assertIn("gateway", r.stdout)

    def test_health_check_counts_volumes_and_index_parts(self):
        self.write("README.md", "# x\n")
        self.write("MEMORY.md", "<!-- wallaby-agent-rules 1.0.1 -->\n# Memory\n\n## Active\n\n- [2026-11-01] x\n")
        self.write("NOW.md", "# NOW\n\n## In flight\n\n## Recently touched\n")
        rows = "".join(f"| `src/mod{i:03d}.md` | module {i} |\n" for i in range(320))
        self.write("INDEX.md", INDEX.replace("| `docs/backup.md` | How backups run and how to restore |\n",
                                             "| `MEMORY.md` | memory |\n| `NOW.md` | now |\n| `LOG.md` | log |\n") + rows)
        for i in range(320):
            self.write(f"src/mod{i:03d}.md", "x\n")
        self.write("LOG.md", log_text(["2026-10", "2026-11"]))
        self.js("split", "volume", "auto", "--today", TODAY, "--threshold", "100")
        sha = self.js("split", "topic", "propose", "--today", TODAY)[0]["plan_sha"]
        self.js("split", "topic", "apply", "--plan-sha", sha, "--confirm", "--today", TODAY)
        out = self.run_script(HEALTH).stdout
        self.assertIn("[3] Every .md file is registered in INDEX.md.", out)
        self.assertIn("[5] Every INDEX.md registration resolves to a real file.", out)


class ClosedLoopTest(Base):
    """The design's loop on one synthetic project, frame by frame."""

    def test_end_to_end_loop(self):
        self.project()
        self.write("LOG.md", log_text(["2026-08", "2026-09", "2026-10", "2026-11"], per_month=20))
        self.write("INDEX.md", INDEX + "| `MAP.md` | System map |\n| `CAPABILITIES.md` | Capabilities |\n")
        self.cli("map", "sync")
        self.assertEqual(self.cli("audit").returncode, 0)

        # 1. a new script: route says "register it" and offers the existing capability
        self.write("scripts/restore.py", "print('restore')\n")
        card = self.js("route", "add a restore step to the backup flow", "--paths", "scripts/restore.py")
        self.assertEqual(card["register"], ["scripts/restore.py"])
        self.assertEqual(card["reuse"][0]["capability"], "backup.py")
        self.assertIn("backups", [c["component"] for c in card["components"]])
        self.assertEqual(self.cli("audit", ok=1).returncode, 1)

        # 2. register it, document it, rename the old term, conduct the change
        caps = self.read("CAPABILITIES.md").replace(
            "| `<capability>`", "| `restore.py` | Script | `scripts/restore.py` | restore, recover | incubating "
                                "| `python3 scripts/restore.py` |\n| `<capability>`")
        self.write("CAPABILITIES.md", caps)
        self.write("docs/backup.md", "# Backups\n\nRun backup.py nightly; restore.py restores the latest nightly-dump.\n")
        out = self.cli("impact", "--event", "automation", "--terms", "nightly-dump", "--record").stdout
        self.assertIn("COMPONENTS backups", out)
        receipt = [ln.split()[1] for ln in out.splitlines() if ln.startswith("RECEIPT")][0]
        self.assertEqual(self.cli("verify", "--receipt", receipt, ok=1).returncode, 1)
        self.write("docs/backup.md", "# Backups\n\nRun backup.py nightly; restore.py restores the latest snapshot.\n")
        self.cli("verify", "--receipt", receipt)

        # 3. audit is clean, the map block's counts catch up, doctor is green
        self.assertTrue(self.js("map", "sync", "--check")["counts_stale"])
        self.cli("map", "sync")
        self.assertEqual(self.js("audit")["total"], 0)
        self.assertIn("DOCTOR OK", self.cli("doctor").stdout)

        # 4. frame A, then split: frame B's full view equals A, the map block counts the volumes
        frame_a = self.read("LOG.md")
        rows = self.js("split", "volume", "auto", "--today", TODAY, "--threshold", "1000")
        self.assertEqual(rows[0]["result"], "cut")
        self.assertEqual(rows[0]["months"], ["2026-08", "2026-09", "2026-10"])
        frame_b = self.snapshot("LOG.md", "LOG")
        sys.path.insert(0, str(CLI.parent))
        import memory_governance as mg
        self.assertEqual(mg.full_view(self.root / "LOG.md"), frame_a)
        self.assertLess(len(self.read("LOG.md")), len(frame_a) / 2)
        self.assertIn("`LOG.md` · 3 volumes", self.read("MAP.md"))
        self.assertIn("DOCTOR OK", self.cli("doctor").stdout)

        # 5. rollback: frame C equals frame A byte for byte, the volume directory is gone
        self.cli("split", "volume", "rollback", "--tx", rows[0]["tx"])
        self.assertEqual(self.read("LOG.md"), frame_a)
        self.assertFalse((self.root / "LOG").exists())
        self.assertIn("DOCTOR OK", self.cli("doctor").stdout)

        # 6. split again: the result equals the first split byte for byte
        self.js("split", "volume", "auto", "--today", TODAY, "--threshold", "1000")
        self.assertEqual(self.snapshot("LOG.md", "LOG"), frame_b)

        # receipts tell the whole story, with distinct ids
        rows = [json.loads(x) for x in self.read(".memory/receipts.jsonl").splitlines() if x.strip()]
        ids = [r["receipt"] for r in rows if r.get("type") != "verification"]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([r["status"] for r in rows if r["type"] == "split"], ["applied", "rolled_back", "applied"])


if __name__ == "__main__":
    unittest.main()
