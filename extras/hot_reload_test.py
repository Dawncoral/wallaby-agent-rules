#!/usr/bin/env python3
"""hot_reload_test.py — the two MCP servers pick up a code change without a reconnect.

Each server is copied to a temporary directory and started there with real pipes. The test edits the copy and
checks that the next call is answered by the new code, that requests sent together are all answered, and that
code which does not start is left alone and reported. POSIX only; never touches the real files or a real project.

Usage: python3 extras/hot_reload_test.py
"""
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SERVERS = [
    ("memory-mcp", os.path.join(HERE, "memory-mcp", "wallaby_memory_mcp.py"), "WALLABY_MEMORY_MCP"),
    ("skill-forge", os.path.join(HERE, "skill-forge", "mcp", "wallaby_skill_forge_mcp.py"), "SKILL_FORGE_MCP"),
]
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
    def __init__(self, path, cwd, env=None):
        self.proc = subprocess.Popen([sys.executable, path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, cwd=cwd, env=dict(os.environ, **(env or {})))
        self.rid, self.buf, self.notifications = 0, b"", []

    def frame(self, method, params=None):
        self.rid += 1
        return self.rid, (json.dumps({"jsonrpc": "2.0", "id": self.rid, "method": method, "params": params or {}}) + "\n").encode()

    def read(self, rid, timeout=30):
        end = time.time() + timeout
        while True:
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                if line.strip():
                    msg = json.loads(line)
                    if msg.get("id") == rid:
                        return msg
                    self.notifications.append(msg)
            left = end - time.time()
            if left <= 0 or not select.select([self.proc.stdout], [], [], left)[0]:
                raise TimeoutError(f"no reply to request {rid}")
            chunk = os.read(self.proc.stdout.fileno(), 65536)
            if not chunk:
                raise EOFError("server closed its pipe")
            self.buf += chunk

    def rpc(self, method, params=None):
        rid, data = self.frame(method, params)
        self.proc.stdin.write(data)
        self.proc.stdin.flush()
        return self.read(rid)

    def call(self, tool):
        """Call a tool with no arguments; returns the text blocks after the first one (the hot-reload note, if any)."""
        res = self.rpc("tools/call", {"name": tool, "arguments": {}})["result"]
        return " ".join(c["text"] for c in res["content"][1:])

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc.stdout.close()


def edit(path, old, new, settled=True):
    text = open(path, encoding="utf-8").read()
    assert old in text, old
    open(path, "w", encoding="utf-8").write(text.replace(old, new))
    if settled:                                  # as if the file had been written a while ago
        t = time.time() - 10
        os.utime(path, (t, t))


def version_line(path):
    return next(line for line in open(path, encoding="utf-8") if line.startswith("SERVER_VERSION = ")).rstrip("\n")


def run(label, source, prefix):
    print(f"\n{label}")
    tmp = tempfile.mkdtemp(prefix="hot_reload_")
    try:
        code = os.path.join(tmp, os.path.basename(source))
        shutil.copy(source, code)
        os.utime(code, (time.time() - 60, time.time() - 60))
        old = version_line(code)
        v0 = old.split('"')[1]
        srv = Server(code, tmp)
        srv.rpc("initialize", {"protocolVersion": "2024-11-05", "clientInfo": {"name": "hot-reload-test"}})
        tool = srv.rpc("tools/list")["result"]["tools"][0]["name"]
        check("no note while the code is unchanged", srv.call(tool) == "")
        edit(code, old, 'SERVER_VERSION = "9.9.9"')
        note = srv.call(tool)
        check("the next call runs the new code and says so", f"v{v0} -> v9.9.9" in note, note)
        check("the note is given once", srv.call(tool) == "")
        check("same process, same pipes", srv.proc.poll() is None)
        info = srv.rpc("initialize", {"protocolVersion": "2024-11-05"})["result"]["serverInfo"]
        check("the server reports the new version", info["version"] == "9.9.9", str(info))

        edit(code, 'SERVER_VERSION = "9.9.9"', 'SERVER_VERSION = "9.9.10"')
        a, da = srv.frame("tools/call", {"name": tool, "arguments": {}})
        b, db = srv.frame("tools/call", {"name": tool, "arguments": {}})
        srv.proc.stdin.write(da + db)            # two requests in one write: the first one triggers the switch
        srv.proc.stdin.flush()
        got = [srv.read(a), srv.read(b)]
        check("requests sent together are all answered", all("result" in g for g in got))

        edit(code, 'SERVER_VERSION = "9.9.10"', 'SERVER_VERSION = "9.9.11" (')      # a syntax error
        note = srv.call(tool)
        check("code that does not start is left alone and reported", "does not start" in note and "v9.9.10" in note, note)
        edit(code, 'SERVER_VERSION = "9.9.11" (', 'SERVER_VERSION = "9.9.11"')
        check("the fixed code is loaded by itself", "-> v9.9.11" in srv.call(tool))

        edit(code, 'SERVER_VERSION = "9.9.11"', 'SERVER_VERSION = "9.9.12"', settled=False)
        check("a file written a moment ago is not loaded yet", srv.call(tool) == "")
        srv.close()

        os.utime(code, (time.time() - 60, time.time() - 60))
        off = Server(code, tmp, {prefix + "_HOT_RELOAD": "0"})
        off.rpc("initialize", {"protocolVersion": "2024-11-05"})
        off.call(tool)
        edit(code, 'SERVER_VERSION = "9.9.12"', 'SERVER_VERSION = "9.9.13"')
        note = off.call(tool)
        check("switched off, it only asks for a reconnect", "reconnect to load it" in note and "v9.9.12" in note, note)
        off.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if os.name != "posix":
        print("skipped: the in-place restart is POSIX only")
        sys.exit(0)
    for label, source, prefix in SERVERS:
        run(label, source, prefix)
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
