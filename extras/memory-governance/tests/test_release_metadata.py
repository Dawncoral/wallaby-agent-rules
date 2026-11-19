#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class ReleaseMetadataTests(unittest.TestCase):
    def test_quickstart_and_health_check_markers(self):
        for rel in (
            "extras/memory-governance/quickstart.py",
            "templates/health_check.py",
            "skills/agent-memory-rules/scripts/health_check.py",
        ):
            with self.subTest(path=rel):
                self.assertIn("# wallaby-agent-rules 1.4.5", (ROOT / rel).read_text(encoding="utf-8").splitlines()[:3])

    def test_mcp_version_matches_its_readme(self):
        code = (ROOT / "extras/memory-mcp/wallaby_memory_mcp.py").read_text(encoding="utf-8")
        readme = (ROOT / "extras/memory-mcp/README.md").read_text(encoding="utf-8")
        self.assertIn('SERVER_VERSION = "0.5.2"', code)
        self.assertIn("Server version 0.5.2", readme)

    def test_readme_badges(self):
        for rel in ("README.md", "README.zh-CN.md"):
            with self.subTest(path=rel):
                self.assertIn("version-1.4.5-blue.svg", (ROOT / rel).read_text(encoding="utf-8"))

    def test_changelog_has_one_unreleased_145_section(self):
        top = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("## 1.4.4", 1)[0]
        self.assertIn("## 1.4.5 — unreleased", top)
        self.assertNotIn("## 1.4.5 — 2026-11-12", top)
        self.assertNotIn("Fewer words in `memory_locate`", top)

    def test_prompt_markers(self):
        for rel in ("PROMPT.md", "PROMPT.zh-CN.md"):
            with self.subTest(path=rel):
                self.assertTrue((ROOT / rel).read_text(encoding="utf-8").startswith("<!-- wallaby-agent-rules 1.4.5 -->"))


if __name__ == "__main__":
    unittest.main()
