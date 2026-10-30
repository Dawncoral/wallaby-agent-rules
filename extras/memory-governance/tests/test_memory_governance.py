#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "memory_governance.py"


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="memory-governance-test-")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), "--target", str(self.root), *args],
            text=True, capture_output=True,
        )

    def init(self):
        result = self.run_cli("init")
        self.assertEqual(result.returncode, 0, result.stderr)

    def write_config(self, name, data):
        path = self.root / ".memory" / name
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_init_and_doctor_green(self):
        self.init()
        self.assertTrue((self.root / "scripts/memory_governance.py").is_file())
        result = self.run_cli("doctor")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DOCTOR OK", result.stdout)

    def test_init_never_overwrites_user_config(self):
        self.init()
        path = self.root / ".memory/premises.json"
        path.write_text('{"version": 1, "premises": [], "user": "kept"}', encoding="utf-8")
        self.init()
        self.assertIn('"user": "kept"', path.read_text(encoding="utf-8"))

    def test_impact_record_verify_and_allow_history(self):
        self.init()
        (self.root / "README.md").write_text("old-component\n", encoding="utf-8")
        result = self.run_cli("impact", "--event", "file_move", "--terms", "old-component", "--record")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("R-000001", result.stdout)
        self.assertEqual(self.run_cli("doctor").returncode, 1)
        self.assertEqual(self.run_cli("verify", "--receipt", "R-000001").returncode, 1)
        allowed = self.run_cli("verify", "--receipt", "R-000001", "--allow", "README.md")
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        self.assertEqual(self.run_cli("doctor").returncode, 0)

    def test_premise_p0_p1_p2_exit_codes(self):
        self.init()
        for level, expected in [("P0", 2), ("P1", 1), ("P2", 0)]:
            self.write_config("premises.json", {"version": 1, "premises": [{
                "id": "P-001", "level": level, "assertion": "required file exists",
                "failure_signal": {"type": "file_missing", "path": "missing.txt"},
                "detection": "test", "status": "active", "source": "test",
            }]})
            self.assertEqual(self.run_cli("premise", "check").returncode, expected)

    def test_premise_recovers_after_file_is_created(self):
        self.init()
        self.assertEqual(self.run_cli("premise", "check").returncode, 0)  # sample is P2: visible warning, not a release blocker
        self.write_config("premises.json", {"version": 1, "premises": [{
            "id": "P-001", "level": "P1", "assertion": "README exists",
            "failure_signal": {"type": "file_missing", "path": "README.md"},
            "detection": "test", "status": "active", "source": "test",
        }]})
        self.assertEqual(self.run_cli("premise", "check").returncode, 1)
        (self.root / "README.md").write_text("ready", encoding="utf-8")
        self.assertEqual(self.run_cli("premise", "check").returncode, 0)

    def test_json_equals_premise(self):
        self.init()
        (self.root / "state.json").write_text('{"status": "old"}', encoding="utf-8")
        self.write_config("premises.json", {"version": 1, "premises": [{
            "id": "P-001", "level": "P1", "assertion": "state is new",
            "failure_signal": {"type": "json_equals", "path": "state.json", "key": "status", "expected": "new"},
            "detection": "test", "status": "active", "source": "test",
        }]})
        self.assertEqual(self.run_cli("premise", "check").returncode, 1)
        (self.root / "state.json").write_text('{"status": "new"}', encoding="utf-8")
        self.assertEqual(self.run_cli("premise", "check").returncode, 0)

    def test_manual_p0_signal_cannot_be_silently_green(self):
        self.init()
        self.write_config("premises.json", {"version": 1, "premises": [{
            "id": "P-001", "level": "P0", "assertion": "manual proof required",
            "failure_signal": {"type": "manual"}, "detection": "human review",
            "status": "active", "source": "test",
        }]})
        result = self.run_cli("premise", "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("UNVERIFIED", result.stdout)

    def test_contradiction_add_and_resolve_preserves_history(self):
        self.init()
        added = self.run_cli("contradict", "add", "--old", "A", "--new", "B", "--evidence", "decision-1")
        self.assertEqual(added.returncode, 0, added.stdout + added.stderr)
        self.assertEqual(self.run_cli("contradict", "check").returncode, 1)
        resolved = self.run_cli("contradict", "resolve", "--id", "C-002", "--evidence", "decision-2")
        self.assertEqual(resolved.returncode, 0, resolved.stdout + resolved.stderr)
        self.assertEqual(self.run_cli("contradict", "check").returncode, 0)
        rows = json.loads((self.root / ".memory/contradictions.json").read_text(encoding="utf-8"))["contradictions"]
        current = next(r for r in rows if r["id"] == "C-002")
        self.assertEqual(len(current["history"]), 2)

    def test_bad_json_fails_loudly(self):
        self.init()
        (self.root / ".memory/impact.json").write_text("not-json", encoding="utf-8")
        result = self.run_cli("impact", "--event", "file_move", "--terms", "old")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read", result.stderr)

    def test_scan_skips_credentials_and_git(self):
        self.init()
        for directory in [".credentials", ".git"]:
            (self.root / directory).mkdir()
            (self.root / directory / "secret.md").write_text("old-component", encoding="utf-8")
        result = self.run_cli("impact", "--event", "file_move", "--terms", "old-component")
        self.assertEqual(result.returncode, 0)
        self.assertIn("MATCHES 0", result.stdout)

    def test_all_nine_conduction_events_are_available(self):
        self.init()
        events = json.loads((self.root / ".memory/impact.json").read_text(encoding="utf-8"))["events"]
        self.assertEqual(set(events), {
            "feature", "mechanism", "document", "external_copy", "automation",
            "decision", "skill", "file_move", "closure",
        })

    def test_match_limit_is_explicit_not_silent(self):
        spec = importlib.util.spec_from_file_location("mg", CLI)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.MAX_MATCHES = 1
        (self.root / "a.md").write_text("old", encoding="utf-8")
        (self.root / "b.md").write_text("old", encoding="utf-8")
        matches, truncated, skipped = module.scan(self.root, ["old"])
        self.assertEqual(len(matches), 1)
        self.assertTrue(truncated)
        self.assertEqual(skipped, [])

    def test_oversized_file_cannot_produce_false_verification(self):
        self.init()
        (self.root / "big.md").write_text("old-component" + "x" * (512 * 1024), encoding="utf-8")
        result = self.run_cli("impact", "--event", "file_move", "--terms", "old-component", "--record")
        self.assertEqual(result.returncode, 0)
        self.assertIn("WARNING skipped", result.stderr)
        self.assertEqual(self.run_cli("verify", "--receipt", "R-000001").returncode, 1)

    def test_examples_match_install_defaults(self):
        spec = importlib.util.spec_from_file_location("mg_defaults", CLI)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        examples = CLI.parent / "examples"
        for name, default in [
            ("impact.json", module.DEFAULT_IMPACT),
            ("premises.json", module.DEFAULT_PREMISES),
            ("contradictions.json", module.DEFAULT_CONTRADICTIONS),
        ]:
            self.assertEqual(json.loads((examples / name).read_text(encoding="utf-8")), default)


if __name__ == "__main__":
    unittest.main()
