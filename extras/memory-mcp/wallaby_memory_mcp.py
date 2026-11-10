#!/usr/bin/env python3
"""wallaby_memory_mcp.py — the file memory as an MCP server (0.4.0, ships with wallaby-agent-rules 1.4.3).

The memory stays what it is: MEMORY.md, NOW.md, INDEX.md, LOG.md (and PROPOSALS.md for the trust-
building queue) as plain Markdown in the project. This server is an optional second door to the same
files, for agents that do not read the entry file or that run somewhere the entry file is not loaded.
It adds no store of its own: the files are the single source; nothing here is cached or indexed.

The tools follow the protocol, not a free search:
  memory_read     — the session-start read: MEMORY.md + NOW.md, with versions and the conflict rule
  memory_locate   — "look it up, don't search": rows of INDEX.md (and the INDEX/ parts it points to)
                    whose path or note match
  memory_propose  — a new durable fact goes to PROPOSALS.md, dated and sourced, never into MEMORY.md;
                    a person (or an approving tool) promotes it
  memory_note     — "note this": one dated line on top of this month in LOG.md
  memory_now      — tracked work moved: one dated line under "In flight" in NOW.md
  memory_check    — run scripts/health_check.py and scripts/reconcile.py when they are installed
  memory_status   — installed version vs this server's, counts, budget, upgrade hint
  memory_lookup   — rows of CAPABILITIES.md (registry=capability) or MAP.md (registry=map): search
                    before building; same name and arguments as the central lookup tool it mirrors
  memory_route    — the reflex card for a change: what to reuse, which map components, event types and
                    surfaces, the tier, and only the premises the changed paths touch (about 2 KB)

memory_lookup and memory_route hold no logic of their own: they run the governance CLI
(scripts/memory_governance.py, 1.4.3 or newer; else the copy beside this server in the repo) with
--json and return its output. Both are read-only.

The three write tools (memory_propose, memory_note, memory_now) go through the CLI's `write` command
when the project has a .memory/ directory, so each write is checked, lands in the right place, and
is recorded in .memory/events.jsonl under the MCP client's name. In a project without .memory/ they
write the files themselves, as before, and nothing new is created.

`--tools` limits what a client sees (a workbench may expose only read/locate/propose). Every write is
redacted (keys, tokens, emails, IPs, home-dir user names) before it touches a file.

Root: --root PATH, else $WALLABY_MEMORY_ROOT, else the current directory.
Origin: --origin ID (or $WALLABY_MEMORY_ORIGIN) names the piece of work this session is doing, such as a task id;
every proposal carries it, so whoever approves can tell where it came from and whether that work was checked.
Versions: the core files (MEMORY.md, NOW.md, INDEX.md, LOG.md) carry their own first-line marker, which only
changes when that file changes. memory_status compares the newest marker against CORE_FORMAT (the newest core-file
marker in this release), not against the release number, so an install that is current is not told to upgrade.
Protocol: MCP over stdio, JSON-RPC 2.0, newline-delimited frames. Standard library only.
Source: this is the canonical copy (extras/memory-mcp/ in wallaby-agent-rules, included from 1.4.3).
"""
import datetime
import json
import os
import re
import subprocess
import sys

SERVER_NAME = "wallaby-memory-mcp"
SERVER_VERSION = "0.4.0"
ORIGIN = ""  # --origin: the work this session does (for example a task id); added to every proposal
CLIENT = ""  # the MCP client's name from `initialize`; the event log records it as the actor of each write
RULES_VERSION = "1.4.3"  # the wallaby-agent-rules release this server ships with
CORE_FORMAT = "1.0.1"    # newest first-line marker on MEMORY.md / NOW.md / INDEX.md / LOG.md in that release
PROTOCOL = "2024-11-05"

FILES = {"MEMORY": "MEMORY.md", "NOW": "NOW.md", "INDEX": "INDEX.md", "LOG": "LOG.md", "PROPOSALS": "PROPOSALS.md"}
PROPOSALS_HEADER = """# PROPOSALS.md — trust-building queue

> New durable facts wait here until a human (or an approving tool) moves them
> into MEMORY.md. One dated, sourced line per proposal.

"""
LOG_HEADER = """# LOG.md — dated log

> Append-only. Newest entry on top. One line per thing that happened.

"""
CONFLICT_RULE = ("Conflict order: what these files say > what you remember > what you infer. "
                 "On a conflict, follow the file and tell the user.")

REDACT_RULES = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "[REDACTED_KEY]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{10,}"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(token|apikey|api_key|secret|password)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[REDACTED_IP]"),
    (re.compile(r"/Users/[A-Za-z0-9_\-]+/"), "~/"),
]
MARKER_RE = re.compile(r"wallaby-agent-rules\s+(v?)(\d+(?:\.\d+){0,2})\b")
LINE_RE = re.compile(r"^- \[(\d{4}-\d{2}-\d{2})\]\s+(.*)$")


def redact(text):
    text = str(text)
    for rx, repl in REDACT_RULES:
        text = rx.sub(repl, text)
    return text


def one_line(text, limit=500):
    return " ".join(str(text or "").split())[:limit]


def today():
    tz = os.environ.get("WALLABY_MEMORY_TZ_OFFSET")
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=float(tz)))) if tz \
        else datetime.datetime.now()
    return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")


class Memory:
    def __init__(self, root):
        self.root = os.path.abspath(os.path.expanduser(root))

    def path(self, key):
        return os.path.join(self.root, FILES[key])

    def read(self, key):
        try:
            with open(self.path(key), encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def write(self, key, text):
        tmp = self.path(key) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, self.path(key))  # atomic: a reader never sees half a file

    def insert_after(self, key, heading, line, header=""):
        text = self.read(key) or header
        if heading not in text:
            text = text.rstrip("\n") + f"\n\n{heading}\n"
        head, rest = text.split(heading, 1)
        self.write(key, head + heading + "\n" + line + "\n" + rest.lstrip("\n"))

    def insert_log(self, month, line):
        """One line on top of its month. A month that is not in the file yet goes above the older months of a
        newest-first log (the default) and below them in an oldest-first one, so the months stay in order."""
        text = self.read("LOG") or LOG_HEADER
        heading = f"## {month}"
        if heading in text:
            return self.insert_after("LOG", heading, line, header=LOG_HEADER)
        months = [(m.start(), m.group(1)) for m in re.finditer(r"(?m)^## (\d{4}-\d{2})(?![0-9])", text)]
        keys = [k for _, k in months]
        oldest_first = len(set(keys)) > 1 and keys == sorted(keys)
        at = next((pos for pos, k in months if (k > month if oldest_first else k < month)), None)
        block = f"{heading}\n{line}\n"
        if at is None:
            self.write("LOG", text.rstrip("\n") + "\n\n" + block)
        else:
            self.write("LOG", text[:at] + block + "\n" + text[at:])

    # ---- facts
    def lines(self, key):
        out, section = [], ""
        for ln in self.read(key).splitlines():
            if ln.startswith("## "):
                section = ln[3:].strip()
            m = LINE_RE.match(ln.strip())
            if m:
                out.append({"date": m.group(1), "text": m.group(2), "section": section})
        return out

    def installed_version(self):
        found = []
        for key in ("MEMORY", "NOW", "INDEX", "LOG"):
            head = self.read(key)[:400]
            m = MARKER_RE.search(head)
            if m:
                found.append(m.group(1) + m.group(2))
        return max(found, key=_vkey) if found else None


def _vkey(v):
    """Semantic markers (1.0.0 on) compare as numbers; pre-1.0 markers (v1–v4.1) always sort below them."""
    legacy = v.startswith("v")
    nums = tuple(int(x) for x in v.lstrip("v").split("."))
    return (0,) + nums if legacy else (1,) + nums


def est_tokens(text):
    cjk = len(re.findall("[\u3000-\u9fff\uac00-\ud7af]", text))
    return cjk + (len(text) - cjk) // 4


# ---- tools ---------------------------------------------------------------

def t_read(mem, args):
    memory, now = mem.read("MEMORY"), mem.read("NOW")
    if not memory and not now:
        return f"No memory files under {mem.root}. Install wallaby-agent-rules there first (see its README).", True
    pending = len(mem.lines("PROPOSALS"))
    head = [f"[wallaby memory · files {mem.installed_version() or 'unmarked'} · server {SERVER_VERSION}]",
            CONFLICT_RULE]
    if pending:
        head.append(f"{pending} proposed fact(s) are waiting in PROPOSALS.md; they are not facts until approved.")
    return "\n".join(head) + "\n\n=== MEMORY.md ===\n" + memory.strip() + "\n\n=== NOW.md ===\n" + now.strip(), False


INDEX_PART_RE = re.compile(r"`(INDEX/[^`\s]+\.md)`")
GOVERNANCE_BUNDLED = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                                                   "memory-governance", "memory_governance.py"))


def index_text(mem):
    """INDEX.md plus the parts it points to (INDEX/<part>.md after a topic split): one hop, no deeper."""
    main = mem.read("INDEX")
    texts = [main]
    for rel in sorted(set(INDEX_PART_RE.findall(main))):
        part = os.path.join(mem.root, rel)
        if os.path.isfile(part):
            with open(part, encoding="utf-8") as f:
                texts.append(f.read())
    return "\n".join(texts)


def run_governance(mem, argv):
    """Run the project's governance CLI (else the bundled copy) with --target; None when neither has the command."""
    tried = []
    for cli in (os.path.join(mem.root, "scripts", "memory_governance.py"), GOVERNANCE_BUNDLED):
        if not os.path.isfile(cli) or cli in tried:
            continue
        tried.append(cli)
        r = subprocess.run([sys.executable, cli, "--target", mem.root] + argv, capture_output=True, text=True, timeout=60)
        if r.returncode == 2 and "invalid choice" in r.stderr:
            continue  # a CLI older than 1.4.3 has no route/lookup
        return r
    return None


def cli_write(mem, argv):
    """Send a write through the governance CLI when the project has .memory/. Returns (result, error):
    (None, None) means "write the file here, the old way": no .memory/, or no CLI with the write command."""
    if not os.path.isdir(os.path.join(mem.root, ".memory")):
        return None, None
    actor = re.sub(r"[^A-Za-z0-9_.:@/-]", "", CLIENT)[:64] or "mcp"
    r = run_governance(mem, ["write"] + argv + ["--json", "--actor", actor])
    if r is None:
        return None, None
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip()[:2000] or "the governance CLI failed without a message"
    try:
        return json.loads(r.stdout), None
    except ValueError:
        return None, "the governance CLI answered with text that is not JSON"


def written_line(result):
    for f in result.get("files") or []:
        for row in f.get("added") or []:
            return row.get("text", "")
    return ""


NO_GOVERNANCE = ("The governance CLI (1.4.3 or newer) is not installed under this root. Install it with "
                 "`python3 extras/memory-governance/memory_governance.py --target . init` from wallaby-agent-rules "
                 "(or update an older copy with its `upgrade --apply`), or read CAPABILITIES.md and MAP.md directly.")


def t_locate(mem, args):
    q = one_line(args.get("query"), 200).lower()
    if not q:
        return "query is empty: say what you are looking for (a file, a topic, a name).", True
    terms = [t for t in re.split(r"\s+", q) if t]
    rows = []
    for ln in index_text(mem).splitlines():
        s = ln.strip()
        if not (s.startswith("|") or s.startswith("- ")) or set(s) <= set("|-: "):
            continue
        if s.lower().startswith(("| file", "| path", "| \u6587\u4ef6")):  # the last one is a Chinese "file" header
            continue
        if all(t in s.lower() for t in terms):
            rows.append(s)
    if not rows:
        return (f"Nothing in INDEX.md matches \"{q}\". If the file exists, register it in INDEX.md the moment "
                "you find it; do not guess a path."), False
    return "INDEX.md rows (a lookup, not a search):\n" + "\n".join(rows[:30]), False


def t_propose(mem, args):
    fact = redact(one_line(args.get("fact")))
    source = redact(one_line(args.get("source"), 200))
    if not fact:
        return "fact is empty.", True
    if not source:
        return "source is required: where does this fact come from (a file path, a commit, the user's words)?", True
    low = fact.lower()
    for key in ("MEMORY", "PROPOSALS"):
        if any(low == x["text"].split(" — source:")[0].strip().lower() for x in mem.lines(key)):
            return f"Already in {FILES[key]}: nothing added.", False
    origin = re.sub(r"[^A-Za-z0-9_.:-]", "", ORIGIN)[:64]
    res, err = cli_write(mem, ["propose", "--text=" + fact, "--source=" + source] + (["--origin=" + origin] if origin else []))
    if err:
        return err, True
    if res is not None:
        if res.get("skipped"):
            return res["skipped"][:1].upper() + res["skipped"][1:] + ".", False
        return f"Proposed (not a fact until a person approves it):\n{written_line(res)}", False
    d, _ = today()
    line = f"- [{d}] {fact} — source: {source} (proposed" + (f" · from {origin}" if origin else "") + ")"
    text = mem.read("PROPOSALS") or PROPOSALS_HEADER
    mem.write("PROPOSALS", text.rstrip("\n") + "\n" + line + "\n")
    return f"Proposed (not a fact until a person approves it):\n{line}", False


def t_note(mem, args):
    text = redact(one_line(args.get("text")))
    if not text:
        return "text is empty.", True
    who = redact(one_line(args.get("source") or "agent", 80))
    res, err = cli_write(mem, ["log", "--text=" + text, "--source=" + who])
    if err:
        return err, True
    if res is not None:
        return f"Logged in LOG.md:\n{written_line(res)}", False
    d, month = today()
    line = f"- [{d}] {text} — {who}"
    mem.insert_log(month, line)
    return f"Logged in LOG.md:\n{line}", False


def t_now(mem, args):
    item = redact(one_line(args.get("item")))
    pointer = redact(one_line(args.get("pointer"), 200))
    if not item:
        return "item is empty.", True
    if not pointer:
        return "pointer is required: where the detail lives (a path or a link).", True
    res, err = cli_write(mem, ["now", "--text=" + item, "--pointer=" + pointer])
    if err:
        return err, True
    if res is not None:
        return f"NOW.md updated:\n{written_line(res)}", False
    d, _ = today()
    line = f"- [{d}] {item}; details: {pointer}"
    mem.insert_after("NOW", "## In flight", line)
    return f"NOW.md updated:\n{line}", False


def t_check(mem, args):
    out, ran = [], 0
    for script in ("health_check.py", "reconcile.py"):
        p = os.path.join(mem.root, "scripts", script)
        if not os.path.exists(p):
            continue
        ran += 1
        try:
            r = subprocess.run([sys.executable, p], cwd=mem.root, capture_output=True, text=True, timeout=120)
            out.append(f"== {script} (exit {r.returncode}) ==\n{(r.stdout + r.stderr).strip()[:4000]}")
        except subprocess.TimeoutExpired:
            out.append(f"== {script} == timed out after 120 s")
    if not ran:
        return "No scripts/health_check.py or scripts/reconcile.py under this memory root; nothing was run.", False
    return "\n\n".join(out), False


def t_lookup(mem, args):
    registry = one_line(args.get("registry") or "capability", 20).lower()
    if registry not in ("capability", "map"):
        return "registry must be 'capability' (CAPABILITIES.md) or 'map' (MAP.md).", True
    argv = ["lookup", "--json", "--registry", registry, "--query", one_line(args.get("query"), 200)]
    if args.get("status"):
        argv += ["--status", one_line(args.get("status"), 40)]
    try:
        limit = max(1, min(50, int(args.get("limit") or 10)))
    except (TypeError, ValueError):
        return "limit must be a number from 1 to 50.", True
    argv += ["--limit", str(limit)] + (["--detail"] if args.get("detail") else [])
    r = run_governance(mem, argv)
    if r is None:
        return NO_GOVERNANCE, True
    return (r.stdout.strip(), False) if r.returncode == 0 else ((r.stderr or r.stdout).strip()[:2000], True)


def t_route(mem, args):
    intent = one_line(args.get("intent"), 500)
    paths = [one_line(p, 300) for p in (args.get("paths") or []) if str(p).strip()][:50]
    if not intent and not paths:
        return "say what the change is (intent) or list the paths it touches.", True
    argv = ["route", "--json"]
    for e in (args.get("events") or [])[:9]:
        argv += ["--event", one_line(e, 40)]
    if args.get("reversible"):
        argv.append("--reversible")
    if args.get("single_area"):
        argv.append("--single-area")
    if args.get("detail"):
        argv.append("--detail")
    if paths:
        argv += ["--paths"] + paths
    argv += ["--", intent]
    r = run_governance(mem, argv)
    if r is None:
        return NO_GOVERNANCE, True
    return (r.stdout.strip(), False) if r.returncode == 0 else ((r.stderr or r.stdout).strip()[:2000], True)


def t_status(mem, args):
    installed = mem.installed_version()
    memory = mem.read("MEMORY")
    facts = mem.lines("MEMORY")
    st = {"root": mem.root, "files_version": installed, "server_version": SERVER_VERSION,
          "rules_release": RULES_VERSION, "writes_format": CORE_FORMAT, "facts": len(facts),
          "facts_by_section": {s: sum(1 for f in facts if f["section"] == s) for s in sorted({f["section"] for f in facts})},
          "pending_proposals": len(mem.lines("PROPOSALS")),
          "in_flight": sum(1 for x in mem.lines("NOW") if x["section"].lower().startswith("in flight")),
          "index_rows": sum(1 for ln in mem.read("INDEX").splitlines() if ln.strip().startswith(("|", "- "))),
          "memory_tokens_est": est_tokens(memory),
          "memory_soft_wall": "~150 dated lines or ~8k estimated tokens"}
    if installed and _vkey(installed) < _vkey(CORE_FORMAT):
        st["upgrade"] = (f"files are {installed}, this server writes the {CORE_FORMAT} format: run the L2 upgrade "
                         "check from PROMPT.md; your content is never overwritten")
    elif installed and _vkey(installed) > _vkey(RULES_VERSION):
        st["upgrade"] = f"files are newer ({installed}) than this server ({RULES_VERSION}): update the server"
    return json.dumps(st, ensure_ascii=False, indent=2), False


TOOLS = {
    "memory_read": (t_read, "Read the project memory at the start of a session: MEMORY.md and NOW.md, with the conflict rule. Call this before taking work.",
                    {"type": "object", "properties": {}}),
    "memory_locate": (t_locate, "Find a file or topic in INDEX.md (the project map) and the INDEX/ parts it points to. A lookup, not a search: returns the matching index rows.",
                      {"type": "object", "properties": {"query": {"type": "string", "description": "words to look up, e.g. 'pricing spec'"}},
                       "required": ["query"]}),
    "memory_propose": (t_propose, "Propose a new durable fact or rule. It is queued in PROPOSALS.md for a person to approve; it does not become memory by itself.",
                       {"type": "object", "properties": {"fact": {"type": "string", "description": "one line, the fact itself"},
                                                         "source": {"type": "string", "description": "where it comes from: a path, a commit, the user's words"}},
                        "required": ["fact", "source"]}),
    "memory_note": (t_note, "Note something that happened (\"note this\"): one dated line on top of this month in LOG.md.",
                    {"type": "object", "properties": {"text": {"type": "string"}, "source": {"type": "string"}}, "required": ["text"]}),
    "memory_now": (t_now, "Tracked work moved: add one dated line under 'In flight' in NOW.md, with a pointer to the detail.",
                   {"type": "object", "properties": {"item": {"type": "string"}, "pointer": {"type": "string"}}, "required": ["item", "pointer"]}),
    "memory_check": (t_check, "Run the weekly checks (scripts/health_check.py and scripts/reconcile.py) if installed; read-only.",
                     {"type": "object", "properties": {}}),
    "memory_status": (t_status, "Versions, counts and the memory budget; says when an upgrade is due.",
                      {"type": "object", "properties": {}}),
    "memory_lookup": (t_lookup, "Look up rows in CAPABILITIES.md (registry=capability) or MAP.md (registry=map). Search the capabilities before building something new. Read-only; returns JSON.",
                      {"type": "object", "properties": {
                          "registry": {"type": "string", "enum": ["capability", "map"], "description": "capability (default) or map"},
                          "query": {"type": "string", "description": "words that must all appear in a row, e.g. 'backup restore'"},
                          "status": {"type": "string", "description": "capability state filter: active, incubating or retired"},
                          "limit": {"type": "integer", "description": "rows to return, 1-50 (default 10)"},
                          "detail": {"type": "boolean", "description": "every column, untruncated"}}}),
    "memory_route": (t_route, "Before or after a change: one compact card (about 2 KB) with what to reuse, the map components it touches, event types and surfaces to update, the tier (light or heavy), and only the premises the changed paths depend on. Read-only; returns JSON.",
                     {"type": "object", "properties": {
                         "intent": {"type": "string", "description": "the change in plain words"},
                         "paths": {"type": "array", "items": {"type": "string"}, "description": "paths the change touches"},
                         "events": {"type": "array", "items": {"type": "string"}, "description": "event types to include, e.g. feature"},
                         "reversible": {"type": "boolean", "description": "the change can be undone inside the project"},
                         "single_area": {"type": "boolean", "description": "the change stays inside one map area"},
                         "detail": {"type": "boolean", "description": "lift the 2 KB budget"}}}),
}


def serve(mem, allowed):
    def send(obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        rid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if rid is None:  # notifications (initialized, cancelled) need no answer
            continue
        if method == "initialize":
            global CLIENT
            info = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
            CLIENT = str(info.get("name") or "")
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Project memory in wallaby-agent-rules files. Call memory_read before taking work; "
                                "propose new durable facts with memory_propose instead of asserting them."}})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": rid, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": [
                {"name": n, "description": d, "inputSchema": s} for n, (_, d, s) in TOOLS.items() if n in allowed]}})
        elif method == "tools/call":
            name = params.get("name")
            if name not in allowed:
                send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"unknown tool: {name}"}})
                continue
            try:
                text, is_err = TOOLS[name][0](mem, params.get("arguments") or {})
            except Exception as e:  # noqa: BLE001 — report, never crash the session
                text, is_err = f"{type(e).__name__}: {e}", True
            send({"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": text}], "isError": is_err}})
        else:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}})


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.environ.get("WALLABY_MEMORY_ROOT") or os.getcwd())
    ap.add_argument("--tools", default="all", help="comma-separated tool names, or 'all'")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--origin", default=os.environ.get("WALLABY_MEMORY_ORIGIN") or "",
                    help="the piece of work this session does; written into every proposal")
    a = ap.parse_args(argv)
    global ORIGIN
    ORIGIN = a.origin
    if a.version:
        print(f"{SERVER_NAME} {SERVER_VERSION} (wallaby-agent-rules {RULES_VERSION}, core format {CORE_FORMAT})")
        return 0
    allowed = set(TOOLS) if a.tools == "all" else {t.strip() for t in a.tools.split(",") if t.strip() in TOOLS}
    serve(Memory(a.root), allowed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
