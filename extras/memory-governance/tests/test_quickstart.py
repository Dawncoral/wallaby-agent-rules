#!/usr/bin/env python3
"""quickstart.py tests: offline init, idempotency, the fictional demo, and mcp-config.

Run from the repository root:
  python3 -m unittest discover -s extras/memory-governance/tests -p 'test_quickstart.py' -v

Every subprocess has a timeout. No test needs a model, an API key, a network,
git, fork, signal, chmod, or a POSIX-only path.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import quickstart  # noqa: E402

REPO = HERE.parents[2]
QUICKSTART = HERE.parent / "quickstart.py"
EXAMPLE = REPO / "examples" / "first-success"
EXPECTED = EXAMPLE / "expected" / "demo.txt"


def run(args, timeout=180, cwd=None, env=None):
    return subprocess.run(
        [sys.executable, str(QUICKSTART)] + [str(a) for a in args],
        capture_output=True, text=True, timeout=timeout, cwd=str(cwd) if cwd else None, env=env,
    )


def snapshot(root):
    result = {}
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not os.path.islink(os.path.join(dirpath, d)))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = str(path.relative_to(root)).replace(os.sep, "/")
            result[rel] = (path.read_bytes(), path.stat().st_mtime_ns)
    return result


def text_files(root):
    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in (".git", ".memory", ".credentials") and not d.startswith(".env"))
        for name in sorted(filenames):
            if name.startswith(".env"):
                continue
            path = Path(dirpath) / name
            try:
                yield path, path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue


class QuickstartTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qs-test-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)

    def target(self, name="project"):
        path = self.tmp / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def init(self, target, **kwargs):
        return run(["--target", target, "init"], **kwargs)

    def test_1_first_init_has_every_file_and_checks_pass(self):
        target = self.target("first success 项目")
        result = self.init(target)
        self.assertEqual(result.returncode, 0, result.stderr)
        for rel in (
            "AGENTS.md", "README.md", "MEMORY.md", "NOW.md", "INDEX.md", "LOG.md",
            "scripts/health_check.py", "scripts/reconcile.py",
            "scripts/memory_governance.py",
            ".memory/impact.json", ".memory/premises.json",
            ".memory/contradictions.json", ".memory/receipts.jsonl",
        ):
            self.assertTrue((target / rel).is_file(), rel)
        self.assertIn("AGENTS.md", (target / "README.md").read_text(encoding="utf-8"))
        index = (target / "INDEX.md").read_text(encoding="utf-8")
        for rel in ("AGENTS.md", "README.md", "MEMORY.md", "NOW.md", "INDEX.md", "LOG.md",
                    "scripts/health_check.py", "scripts/reconcile.py"):
            self.assertIn(rel, index)
        self.assertNotIn(".credentials", index)
        self.assertNotIn(".memory/", index)
        doctor = subprocess.run(
            [sys.executable, str(target / "scripts" / "memory_governance.py"),
             "--target", str(target), "doctor"], capture_output=True, text=True, timeout=180)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertIn("P-001 P2 OK", doctor.stdout + doctor.stderr)
        self.assertNotIn("P-001 P2 FAILING", doctor.stdout + doctor.stderr)

        health = subprocess.run([sys.executable, str(target / "scripts" / "health_check.py"),
                                 str(target)], capture_output=True, text=True, timeout=120)
        self.assertEqual(health.returncode, 0, health.stdout + health.stderr)
        reconcile = subprocess.run([sys.executable, str(target / "scripts" / "reconcile.py"),
                                    str(target)], capture_output=True, text=True, timeout=120)
        self.assertEqual(reconcile.returncode, 0, reconcile.stdout + reconcile.stderr)

    def test_2_second_init_keeps_bytes_and_mtime_and_log_is_not_duplicated(self):
        target = self.target()
        self.assertEqual(self.init(target).returncode, 0)
        before = snapshot(target)
        log_before = (target / "LOG.md").read_text(encoding="utf-8")
        second = self.init(target)
        self.assertEqual(second.returncode, 0, second.stderr)
        after = snapshot(target)
        self.assertEqual(sorted(before), sorted(after))
        for rel in before:
            self.assertEqual(before[rel], after[rel], "changed on second init: " + rel)
        self.assertEqual((target / "LOG.md").read_text(encoding="utf-8"), log_before)
        self.assertEqual(log_before.count("Memory system initialized"), 1)
        self.assertIn("KEEP AGENTS.md", second.stdout)
        self.assertIn("PROMPT.md L2 - Upgrade check", second.stdout)

    def test_3_existing_files_keep_their_sentinel_bytes_and_mtime(self):
        target = self.target()
        sentinels = {
            "AGENTS.md": "# sentinel agents\n",
            "README.md": "# sentinel readme\n",
            "MEMORY.md": "# sentinel memory\n",
            "NOW.md": "# sentinel now\n",
            "INDEX.md": "# sentinel index\n",
            "LOG.md": "# sentinel log\n",
            "scripts/health_check.py": "# sentinel health\n",
            "scripts/reconcile.py": "# sentinel reconcile\n",
        }
        for rel, text in sentinels.items():
            path = target / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        before = snapshot(target)
        result = self.init(target)
        self.assertEqual(result.returncode, 0, result.stderr)
        for rel, text in sentinels.items():
            self.assertEqual((target / rel).read_text(encoding="utf-8"), text)
            self.assertEqual((target / rel).stat().st_mtime_ns, before[rel][1], rel)
        self.assertFalse((target / "CLAUDE.md").exists())
        self.assertFalse((target / "GEMINI.md").exists())

    def test_4_credentials_and_env_are_not_indexed_or_read(self):
        target = self.target()
        cred = target / ".credentials" / "api.txt"
        cred.parent.mkdir(parents=True)
        cred.write_text("sk-example-sentinel-value\n", encoding="utf-8")
        env_file = target / ".env.local"
        env_file.write_text("TOKEN=sk-example-env-sentinel\n", encoding="utf-8")
        env_dir = target / ".env"
        env_dir.mkdir()
        (env_dir / "config.md").write_text("sk-example-env-dir-sentinel\n", encoding="utf-8")
        seen = []
        original = quickstart.read_text

        def recorded(path):
            seen.append(str(path))
            return original(path)

        with mock.patch.object(quickstart, "read_text", recorded):
            with contextlib.redirect_stdout(io.StringIO()):
                quickstart.init_project(target)
        self.assertFalse([p for p in seen if ".credentials" in p.replace(os.sep, "/")], seen)
        self.assertFalse([p for p in seen if os.path.basename(p).startswith(".env")], seen)
        index = (target / "INDEX.md").read_text(encoding="utf-8")
        self.assertNotIn(".credentials", index)
        self.assertNotIn(".env", index)
        self.assertNotIn("sk-example", index)
        for _, text in text_files(target):
            self.assertNotIn("sk-example-sentinel-value", text)
            self.assertNotIn("sk-example-env-sentinel", text)
            self.assertNotIn("sk-example-env-dir-sentinel", text)
        self.assertEqual(cred.read_text(encoding="utf-8"), "sk-example-sentinel-value\n")

    def test_5_init_passes_without_a_git_directory(self):
        target = self.target()
        self.assertFalse((target / ".git").exists())
        result = self.init(target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((target / ".git").exists())
        doctor = subprocess.run(
            [sys.executable, str(target / "scripts" / "memory_governance.py"),
             "--target", str(target), "doctor"], capture_output=True, text=True, timeout=180)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        demo = run(["demo"], cwd=self.tmp)
        self.assertEqual(demo.returncode, 0, demo.stderr)
        self.assertEqual(demo.stdout.replace("\r\n", "\n").rstrip("\n").split("\n")[-1], "Doctor: PASS")

    def test_6_demo_hash_unchanged_and_last_line_is_exactly_doctor_pass(self):
        before = quickstart.tree_hash(EXAMPLE)
        result = run(["demo"], cwd=self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(quickstart.tree_hash(EXAMPLE), before)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.replace("\r\n", "\n").rstrip("\n").split("\n")
        self.assertEqual(lines[-1], "Doctor: PASS")
        expected = EXPECTED.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
        self.assertEqual("\n".join(lines), expected)

    def test_7_mcp_config_prints_parseable_json_and_leaves_home_alone(self):
        target = self.target("mcp project 项目")
        home = self.tmp / "home"
        (home / ".cursor").mkdir(parents=True)
        (home / ".config" / "Claude").mkdir(parents=True)
        configs = {
            home / ".claude.json": '{"sentinel": "claude"}\n',
            home / ".cursor" / "mcp.json": '{"sentinel": "cursor"}\n',
            home / ".config" / "Claude" / "claude_desktop_config.json": '{"sentinel": "desktop"}\n',
        }
        for path, text in configs.items():
            path.write_text(text, encoding="utf-8")
        before = snapshot(home)
        env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), XDG_CONFIG_HOME=str(home / ".config"))
        result = run(["--target", target, "mcp-config", "--print"], cwd=self.tmp, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(list(data), ["mcpServers"])
        entry = data["mcpServers"]["wallaby-memory"]
        self.assertEqual(entry["command"], str(Path(sys.executable).resolve()))
        self.assertEqual(entry["args"][0], str((REPO / "extras" / "memory-mcp" / "wallaby_memory_mcp.py").resolve()))
        self.assertEqual(entry["args"][1], "--root")
        self.assertEqual(entry["args"][2], str(target.resolve()))
        self.assertEqual(snapshot(home), before)
        for path, text in configs.items():
            self.assertEqual(path.read_text(encoding="utf-8"), text)

        refused = run(["--target", target, "mcp-config"], cwd=self.tmp, env=env)
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(refused.stdout, "")
        self.assertIn("--print", refused.stderr)

    def test_8_entry_detection_uses_claude_gemini_and_default(self):
        claude_target = self.target("claude")
        (claude_target / ".claude").mkdir()
        self.assertEqual(self.init(claude_target).returncode, 0)
        self.assertTrue((claude_target / "CLAUDE.md").is_file())
        self.assertFalse((claude_target / "AGENTS.md").exists())

        gemini_target = self.target("gemini")
        (gemini_target / ".gemini").mkdir()
        self.assertEqual(self.init(gemini_target).returncode, 0)
        self.assertTrue((gemini_target / "GEMINI.md").is_file())
        self.assertFalse((gemini_target / "AGENTS.md").exists())

        both_target = self.target("both")
        (both_target / ".claude").mkdir()
        (both_target / ".gemini").mkdir()
        self.assertEqual(self.init(both_target).returncode, 0)
        self.assertTrue((both_target / "AGENTS.md").is_file())
        self.assertFalse((both_target / "CLAUDE.md").exists())
        self.assertFalse((both_target / "GEMINI.md").exists())

        existing_target = self.target("existing")
        (existing_target / "CLAUDE.md").write_text("# keep me\n", encoding="utf-8")
        self.assertEqual(self.init(existing_target).returncode, 0)
        self.assertEqual((existing_target / "CLAUDE.md").read_text(encoding="utf-8"), "# keep me\n")
        self.assertFalse((existing_target / "AGENTS.md").exists())

    def test_9_windows_style_path_round_trips_through_json(self):
        name = "C:\\work\\win style project" if os.name != "nt" else "win style project"
        target = self.target(name)
        initialized = self.init(target)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        doctor = subprocess.run(
            [sys.executable, str(target / "scripts" / "memory_governance.py"),
             "--target", str(target), "doctor"], capture_output=True, text=True, timeout=180)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        result = run(["--target", target, "mcp-config", "--print"], cwd=self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["mcpServers"]["wallaby-memory"]["args"][2], str(target.resolve()))

    def test_10_missing_source_fails_with_stage_file_and_next(self):
        fake_repo = self.tmp / "fake repo"
        (fake_repo / "extras" / "memory-governance").mkdir(parents=True)
        (fake_repo / "extras" / "memory-governance" / "memory_governance.py").write_text(
            "VERSION = '1.4.5'\n", encoding="utf-8")
        target = self.tmp / "target"
        with self.assertRaises(quickstart.QuickstartError) as caught:
            quickstart.init_project(target, repo_root=fake_repo)
        error = caught.exception
        self.assertEqual(error.stage, "preflight")
        self.assertIn("health_check", error.path)
        self.assertTrue(error.next_step)
        self.assertFalse(target.exists())


    def test_12_symlinked_directory_is_refused_and_nothing_escapes(self):
        target = self.target()
        outside = self.tmp / "outside"
        outside.mkdir()
        try:
            os.symlink(str(outside), str(target / "scripts"), target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this platform does not allow creating a directory symlink here")
        result = self.init(target)
        self.assertEqual(result.returncode, 2)
        self.assertIn("stage: path", result.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_11_missing_source_cli_returns_2_with_actionable_message(self):
        fake_repo = self.tmp / "fake repo cli"
        (fake_repo / "extras" / "memory-governance").mkdir(parents=True)
        (fake_repo / "extras" / "memory-governance" / "memory_governance.py").write_text(
            "VERSION = '1.4.5'\n", encoding="utf-8")
        target = self.tmp / "cli target"
        stderr = io.StringIO()
        with mock.patch.object(quickstart, "REPO_ROOT", fake_repo):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                code = quickstart.main(["--target", str(target), "init"])
        self.assertEqual(code, 2)
        message = stderr.getvalue()
        self.assertIn("stage: preflight", message)
        self.assertIn("file:", message)
        self.assertIn("next:", message)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
