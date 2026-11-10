#!/usr/bin/env python3
"""smoke_test.py — wallaby_memory_mcp against a live server on a temporary project.

Usage: python3 smoke_test.py   (never touches a real project)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "wallaby_memory_mcp.py")
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


class Server:
    def __init__(self, root, tools="all", extra=()):
        self.p = subprocess.Popen([sys.executable, SERVER, "--root", root, "--tools", tools, *extra],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.n = 0

    def call(self, method, params=None):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def tool(self, name, **args):
        r = self.call("tools/call", {"name": name, "arguments": args})
        if "error" in r:
            return r["error"]["message"], True
        return r["result"]["content"][0]["text"], r["result"]["isError"]

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=5)


def main():
    tmp = tempfile.mkdtemp(prefix="memmcp-")
    try:
        with open(os.path.join(tmp, "MEMORY.md"), "w", encoding="utf-8") as f:
            f.write("<!-- wallaby-agent-rules 1.0.1 -->\n# Memory\n\n## Active\n\n"
                    "- [2026-10-01] Prices are quoted in USD; 10 credits = 1 USD → docs/pricing.md\n\n## Standby\n\n## Dormant\n")
        with open(os.path.join(tmp, "NOW.md"), "w", encoding="utf-8") as f:
            f.write("<!-- wallaby-agent-rules 1.0.1 -->\n# NOW.md\n\n## In flight\n\n## Recently touched\n")
        with open(os.path.join(tmp, "INDEX.md"), "w", encoding="utf-8") as f:
            f.write("# INDEX.md\n\n| File | What it is |\n|---|---|\n| `docs/pricing.md` | Pricing spec and credit rules |\n"
                    "| `ops/deploy.md` | How to deploy the gateway |\n")
        s = Server(tmp)
        r = s.call("initialize", {"protocolVersion": "2024-11-05"})
        check("initialize", r["result"]["serverInfo"]["name"] == "wallaby-memory-mcp")
        names = {t["name"] for t in s.call("tools/list")["result"]["tools"]}
        check("seven tools", names == {"memory_read", "memory_locate", "memory_propose", "memory_note",
                                       "memory_now", "memory_check", "memory_status"}, names)
        text, err = s.tool("memory_read")
        check("read: MEMORY + NOW + conflict rule", not err and "USD" in text and "=== NOW.md ===" in text
              and "Conflict order" in text)
        text, _ = s.tool("memory_locate", query="pricing")
        check("locate: index row", "docs/pricing.md" in text and "deploy" not in text)
        text, _ = s.tool("memory_locate", query="kubernetes")
        check("locate: no guess when absent", "Nothing in INDEX.md" in text)
        text, err = s.tool("memory_propose", fact="Gateway runs on port 8788", source="")
        check("propose: source required", err)
        text, err = s.tool("memory_propose", fact="Gateway key is sk-abcdefghijklmnop1234 for user a@b.com",
                           source="ops/deploy.md")
        props = open(os.path.join(tmp, "PROPOSALS.md"), encoding="utf-8").read()
        check("propose: queued, redacted", not err and "[REDACTED_KEY]" in props and "[REDACTED_EMAIL]" in props
              and "sk-abc" not in props)
        mem = open(os.path.join(tmp, "MEMORY.md"), encoding="utf-8").read()
        check("propose: MEMORY.md untouched", "Gateway" not in mem)
        text, _ = s.tool("memory_propose", fact="Prices are quoted in USD; 10 credits = 1 USD → docs/pricing.md",
                         source="x")
        check("propose: no duplicate of a fact", "Already in MEMORY.md" in text)
        text, _ = s.tool("memory_read")
        check("read: mentions pending proposals", "1 proposed fact" in text)
        s.tool("memory_note", text="Released 1.4.2", source="agent")
        s.tool("memory_note", text="Second note", source="agent")
        log = open(os.path.join(tmp, "LOG.md"), encoding="utf-8").read()
        check("note: newest on top", log.index("Second note") < log.index("Released 1.4.2"))
        text, err = s.tool("memory_now", item="Pricing page rewrite", pointer="")
        check("now: pointer required", err)
        s.tool("memory_now", item="Pricing page rewrite", pointer="docs/pricing.md")
        now = open(os.path.join(tmp, "NOW.md"), encoding="utf-8").read()
        check("now: under In flight", now.index("Pricing page rewrite") < now.index("## Recently touched"))
        text, _ = s.tool("memory_check")
        check("check: says when scripts are missing", "nothing was run" in text)
        st = json.loads(s.tool("memory_status")[0])
        check("status: current install is not told to upgrade", st["files_version"] == "1.0.1"
              and "upgrade" not in st and st["pending_proposals"] == 1 and st["facts"] == 1
              and st["rules_release"] == "1.4.3" and st["writes_format"] == "1.0.1")
        r = s.call("bogus/method")
        check("unknown method is an error", r["error"]["code"] == -32601)
        s.close()
        s2 = Server(tmp, tools="memory_read,memory_locate,memory_propose")
        s2.call("initialize")
        names = {t["name"] for t in s2.call("tools/list")["result"]["tools"]}
        check("--tools limits the surface", names == {"memory_read", "memory_locate", "memory_propose"})
        text, err = s2.tool("memory_note", text="x")
        check("hidden tool cannot be called", err and "unknown tool" in text)
        s2.close()
        empty = tempfile.mkdtemp(prefix="memmcp-empty-")
        s3 = Server(empty)
        s3.call("initialize")
        text, err = s3.tool("memory_read")
        check("read: says when there is no memory", err and "No memory files" in text)
        s3.close()
        shutil.rmtree(empty, ignore_errors=True)

        def status_with(marker):
            proj = tempfile.mkdtemp(prefix="memmcp-ver-")
            with open(os.path.join(proj, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write(f"<!-- wallaby-agent-rules {marker} -->\n# Memory\n")
            sv = Server(proj)
            sv.call("initialize")
            out = json.loads(sv.tool("memory_status")[0])
            sv.close()
            shutil.rmtree(proj, ignore_errors=True)
            return out

        old = status_with("v4.1")
        check("status: pre-1.0 marker gets the upgrade hint", "L2 upgrade" in old.get("upgrade", ""), old)
        new = status_with("9.0.0")
        check("status: newer files ask for a newer server", "update the server" in new.get("upgrade", ""), new)
        work = tempfile.mkdtemp(prefix="memmcp-origin-")
        with open(os.path.join(work, "MEMORY.md"), "w", encoding="utf-8") as f:
            f.write("<!-- wallaby-agent-rules 1.0.1 -->\n# Memory\n\n## Active\n")
        s4 = Server(work, extra=("--origin", "task-42; rm -rf"))
        s4.call("initialize")
        s4.tool("memory_propose", fact="Staging runs on 10.0.0.12 under /Users/alice/app", source="ops/deploy.md")
        s4.close()
        props = open(os.path.join(work, "PROPOSALS.md"), encoding="utf-8").read()
        check("propose: origin recorded, unsafe characters dropped", "· from task-42rm-rf)" in props, props)
        check("propose: IP and home-directory user redacted", "[REDACTED_IP]" in props and "~/app" in props
              and "alice" not in props, props)
        shutil.rmtree(work, ignore_errors=True)
        ver = subprocess.run([sys.executable, SERVER, "--version"], capture_output=True, text=True, timeout=10)
        check("--version names server, release and core format",
              ver.stdout.strip() == "wallaby-memory-mcp 0.2.0 (wallaby-agent-rules 1.4.3, core format 1.0.1)",
              ver.stdout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
