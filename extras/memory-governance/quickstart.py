#!/usr/bin/env python3
# wallaby-agent-rules 1.4.5
"""quickstart.py — the offline first success for wallaby-agent-rules.

One standard-library file, three commands:

  python3 extras/memory-governance/quickstart.py --target /path/to/project init
  python3 extras/memory-governance/quickstart.py demo
  python3 extras/memory-governance/quickstart.py --target /path/to/project mcp-config --print

`init` creates the entry file, a minimal README.md when none exists, MEMORY.md, NOW.md,
INDEX.md, LOG.md, and the two weekly scripts, then calls the existing governance CLI's
`init` for `.memory/` and the installed copy. Existing files are always kept: the command
never overwrites, merges, or repairs one; a kept agent entry points to the L2 upgrade prompt.
`demo` copies the fictional `examples/first-success/` tree to a system temporary directory,
runs the full init there, finds a decision through the real Memory MCP `memory_locate`,
shows a LOG.md/NOW.md contradiction, fixes only the temporary NOW.md, and ends with
`Doctor: PASS` when reconcile, health_check, and the governance doctor all exit 0.
`mcp-config --print` writes nothing: it prints the `mcpServers` entry to merge into a client.

No model, API key, network, or git repository is needed. Subprocesses use `sys.executable`.
Source: this file is part of wallaby-agent-rules and is not copied into the target project.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
GOVERNANCE_REL = Path("extras") / "memory-governance" / "memory_governance.py"
MCP_SERVER_REL = Path("extras") / "memory-mcp" / "wallaby_memory_mcp.py"
EXAMPLE_REL = Path("examples") / "first-success"
TEMPLATES_REL = Path("templates")

ENTRY_CANDIDATES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursorrules")
GOVERNANCE_FILES = (
    Path("scripts") / "memory_governance.py",
    Path(".memory") / "impact.json",
    Path(".memory") / "premises.json",
    Path(".memory") / "contradictions.json",
    Path(".memory") / "receipts.jsonl",
)
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".credentials", ".memory", "node_modules",
    ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "dist", "build", ".next", ".nuxt", "out", "target",
    ".idea", ".vscode",
}
INDEX_EXTS = {
    ".md", ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".sh",
    ".js", ".ts", ".html", ".css", ".sql",
}
KNOWN_DESCRIPTIONS = {
    "AGENTS.md": "AI entry point - standing instructions",
    "CLAUDE.md": "AI entry point for Claude - standing instructions",
    "GEMINI.md": "AI entry point for Gemini - standing instructions",
    "MEMORY.md": "Long-term memory: permanent facts and iron rules",
    "NOW.md": "Current state: work in flight and recently touched",
    "INDEX.md": "This file - one line per file in the project",
    "LOG.md": "Dated append-only log of decisions and events",
    "README.md": "Project overview",
    "scripts/health_check.py": "Weekly tidy-up check",
    "scripts/reconcile.py": "Consistency audit between LOG.md and NOW.md",
    "scripts/memory_governance.py": "Memory governance CLI",
}
EXT_DESCRIPTIONS = {
    ".md": "Markdown document",
    ".py": "Python script",
    ".json": "JSON data",
    ".yaml": "YAML configuration",
    ".yml": "YAML configuration",
    ".toml": "TOML configuration",
    ".txt": "Text file",
    ".sh": "Shell script",
    ".js": "JavaScript file",
    ".ts": "TypeScript file",
    ".html": "HTML page",
    ".css": "Stylesheet",
    ".sql": "SQL script",
}

ENTRY_TEMPLATE = """<!-- wallaby-agent-rules 1.0.1 -->
# {name} - how to work in this project

> The entry file is the integration. Read it at the start of every session;
> no plugin, MCP server, or install is required.

## Start here

1. Read `MEMORY.md` and `NOW.md` before taking work. `MEMORY.md` holds permanent
   facts and rules; `NOW.md` holds what is in flight right now.
2. Look in `INDEX.md` before searching. A lookup beats a search; register every
   new file there the moment it is created.
3. Append one dated line to `LOG.md` when something ships, changes, or is decided.

Conflict order: what these files say > what you remember > what you infer.
On a conflict, follow the file and tell the user.

## Closeout

- Take finished work out of `NOW.md`'s In flight section, and write the dated
  `LOG.md` line in the same action.
- Run `python3 scripts/reconcile.py` and `python3 scripts/health_check.py`.
  Both exit 0 when the log and the state agree.

## Verify

- One canonical check: `python3 scripts/health_check.py`. Run it before
  declaring any task done.
"""

MEMORY_TEMPLATE = """<!-- wallaby-agent-rules 1.0.1 -->
# MEMORY.md - permanent facts and iron rules

> Long-term memory. One dated line per fact or rule; the detail lives in a
> linked file. Read this file and `NOW.md` at the start of every session.
> Anything idle for 30 days moves down to `LOG.md` at the next closeout.

## Facts

- [{day}] This project keeps its memory in plain Markdown: `MEMORY.md`, `NOW.md`,
  `INDEX.md`, and `LOG.md`; governance data lives in `.memory/`. Source: quickstart init.

## Rules

- [{day}] Look in `INDEX.md` before searching, and append to `LOG.md` before calling
  work done. Source: quickstart init.
"""

README_TEMPLATE = """# Project

This project uses wallaby-agent-rules for file-based agent memory.

## Start here

- `{name}` tells the agent how to work in this project.
- `MEMORY.md` holds dated facts and decisions.
- `NOW.md` holds work in flight.
- `INDEX.md` maps project files.
- `LOG.md` is the dated event log.

## Checks

Run `python3 scripts/health_check.py`, `python3 scripts/reconcile.py`, and
`python3 scripts/memory_governance.py --target . doctor`.

Existing files are never overwritten by quickstart. For an incremental upgrade,
see PROMPT.md in the wallaby-agent-rules repository, section "L2 - Upgrade check".
"""


FALLBACK_INDEX_HEADER = """<!-- wallaby-agent-rules 1.0.1 -->
# INDEX.md - the project map

> One line per file: `path | what it is, in a few words`.
> Look here FIRST when searching for anything.
"""


class QuickstartError(Exception):
    """A failure a person can act on: stage, file, detail, and the next command."""

    def __init__(self, stage, path, detail, next_step):
        super().__init__(detail)
        self.stage = stage
        self.path = str(path)
        self.detail = detail
        self.next_step = next_step


def child_env():
    """Children print UTF-8 even on a Windows console whose code page is not UTF-8."""
    return dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def use_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def read_text(path):
    with open(str(path), encoding="utf-8", newline="") as f:
        return f.read()


def read_source(path, stage="read source"):
    try:
        return read_text(path)
    except OSError as e:
        raise QuickstartError(stage, path, str(e),
                              "fix the permission or restore the file, then run the command again")


def write_text_atomic(path, text):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _within(root, path):
    try:
        return os.path.commonpath([str(root), str(path)]) == str(root)
    except ValueError:
        return False


def ensure_dir(root, rel_dir):
    """Create a directory under root one component at a time, refusing a symlink."""
    cur = Path(root)
    for part in Path(rel_dir).parts:
        if part in ("", "."):
            continue
        cur = cur / part
        try:
            st = os.lstat(str(cur))
        except FileNotFoundError:
            try:
                os.mkdir(str(cur))
            except OSError as e:
                raise QuickstartError("mkdir", cur, str(e),
                                      "fix the permission or remove the blocking file, then run init again")
            continue
        if stat.S_ISLNK(st.st_mode):
            raise QuickstartError("path", cur, "refusing to follow a symlink inside the target",
                                  "remove the symlink and run init again")
        if not stat.S_ISDIR(st.st_mode):
            raise QuickstartError("path", cur, "a file is in the way of a directory",
                                  "move that file, then run init again")
    if not _within(Path(root), Path(os.path.realpath(str(cur)))):
        raise QuickstartError("path", cur, "the path escapes the target directory",
                              "use a target whose directories are real directories, then run init again")


def write_new(root, rel, text):
    """Create one file exclusively. Return True when created, False when it already exists."""
    root = Path(root)
    rel = Path(rel)
    target = root / rel
    if not _within(root, target):
        raise QuickstartError("write", target, "the path escapes the target directory",
                              "choose a target inside the project, then run init again")
    ensure_dir(root, rel.parent)
    if target.exists() or target.is_symlink():
        return False
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(target), flags, 0o644)
    except FileExistsError:
        return False
    except OSError as e:
        raise QuickstartError("write", target, str(e),
                              "fix the permission or remove the blocking file, then run init again")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    except Exception:
        try:
            os.unlink(str(target))
        except OSError:
            pass
        raise
    return True


def source_paths(repo_root):
    repo_root = Path(repo_root)
    return {
        "governance": repo_root / GOVERNANCE_REL,
        "health_check": repo_root / TEMPLATES_REL / "health_check.py",
        "reconcile": repo_root / TEMPLATES_REL / "reconcile.py",
        "now": repo_root / TEMPLATES_REL / "NOW.md",
        "log": repo_root / TEMPLATES_REL / "LOG.md",
        "index": repo_root / TEMPLATES_REL / "INDEX.md",
    }


def check_sources(repo_root):
    paths = source_paths(repo_root)
    for label, path in paths.items():
        if not Path(path).is_file():
            raise QuickstartError(
                "preflight", path,
                "missing source %s; quickstart must run from a full wallaby-agent-rules clone" % label,
                "clone the repository again and run python3 extras/memory-governance/quickstart.py init",
            )
    return paths


def choose_entry(root):
    """Return (name, exists). Existing entry files are kept; only a lone .claude/ or .gemini/ is a hint."""
    for name in ENTRY_CANDIDATES:
        path = Path(root) / name
        if path.is_file() or path.is_symlink():
            return name, True
    claude = (Path(root) / ".claude").is_dir()
    gemini = (Path(root) / ".gemini").is_dir()
    if claude and not gemini:
        return "CLAUDE.md", False
    if gemini and not claude:
        return "GEMINI.md", False
    return "AGENTS.md", False


def without_dated_examples(text):
    """Drop dated bullet examples that live inside HTML comments.

    The templates use them to explain the format, but reconcile.py and
    health_check.py read by line and would treat them as real entries.
    """
    out = []
    in_comment = False
    for line in text.splitlines(True):
        stripped = line.strip()
        if "<!--" in stripped:
            in_comment = True
        if in_comment and re.match(r"^\s*[-*]\s*\[\d{4}-\d{2}-\d{2}\]", line):
            continue
        if in_comment and stripped == "Example:":
            continue
        if "-->" in stripped:
            in_comment = False
        out.append(line)
    return "".join(out)


def render_log(template, today):
    """Reuse the LOG.md template, moving its first month heading to this month."""
    month = today[:7]
    text = without_dated_examples(template)
    if re.search(r"(?m)^## \d{4}-\d{2}\s*$", text):
        text = re.sub(r"(?m)^## \d{4}-\d{2}\s*$", "## " + month, text, count=1)
    else:
        text = text.rstrip("\n") + "\n\n## " + month + "\n"
    line = ("- [%s] Memory system initialized by quickstart - `MEMORY.md`, `NOW.md`, "
            "`INDEX.md`, `LOG.md`, `scripts/`. Source: quickstart init." % today)
    text = text.replace("## " + month + "\n", "## " + month + "\n\n" + line + "\n", 1)
    return text


def describe(rel):
    key = rel.replace(os.sep, "/")
    if key in KNOWN_DESCRIPTIONS:
        return KNOWN_DESCRIPTIONS[key]
    return EXT_DESCRIPTIONS.get(Path(key).suffix.lower(), "File")


def collect_index_rows(root):
    """One row per allowed file, from relative paths and suffixes only. No file content is read."""
    rows = []
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".env")
            and not os.path.islink(os.path.join(dirpath, d))
        )
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            if name.startswith(".env"):
                continue
            if Path(name).suffix.lower() not in INDEX_EXTS:
                continue
            rel = os.path.relpath(full, str(root)).replace(os.sep, "/")
            rows.append((rel, describe(rel)))
    rows.sort(key=lambda row: row[0])
    return rows


def render_index(root, template):
    rows = collect_index_rows(root)
    lines = template.splitlines()
    header = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("| file"):
            header = i
            break
    if header is None:
        text = FALLBACK_INDEX_HEADER.rstrip("\n") + "\n\n| File | What it is |\n|---|---|\n"
        suffix = ""
    else:
        end = header + 1
        while end < len(lines) and lines[end].strip().startswith("|"):
            end += 1
        text = "\n".join(lines[:header + 1]) + "\n|---|---|\n"
        suffix = "\n".join(lines[end:])
    for rel, note in rows:
        text += "| `%s` | %s |\n" % (rel, note)
    if suffix:
        text += "\n" + suffix.strip("\n") + "\n"
    return text


def refuse_symlink_path(root, rel):
    """Reject an existing path whose final file or any parent is a symlink."""
    cur = Path(root)
    for part in Path(rel).parts:
        cur = cur / part
        try:
            st = os.lstat(str(cur))
        except FileNotFoundError:
            return
        if stat.S_ISLNK(st.st_mode):
            raise QuickstartError("path", cur, "refusing to follow a symlink inside the target",
                                  "remove the symlink and run init again")


def governance_ready(root):
    return all((Path(root) / rel).is_file() for rel in GOVERNANCE_FILES)


def install_governance(root, repo_root):
    for rel in GOVERNANCE_FILES:
        refuse_symlink_path(root, rel)
    if governance_ready(root):
        print("Governance: already installed (KEEP .memory/ and scripts/memory_governance.py)")
        return
    cli = Path(repo_root) / GOVERNANCE_REL
    try:
        r = subprocess.run(
            [sys.executable, str(cli), "--target", str(root), "init"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, env=child_env(),
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise QuickstartError("governance init", cli, "%s: %s" % (type(e).__name__, e),
                              "run python3 %s --target %s init" % (cli, root))
    output = (r.stdout or "").strip()
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip().splitlines()
        raise QuickstartError("governance init", cli, detail[-1] if detail else "exit code %d" % r.returncode,
                              "run python3 %s --target %s init" % (cli, root))
    print("Governance: installed .memory/ and scripts/memory_governance.py")
    for line in output.splitlines():
        print("  " + line)


def init_project(root, repo_root=REPO_ROOT):
    """Create the missing pieces under root. Existing files are never written."""
    root = Path(root).expanduser().resolve()
    repo_root = Path(repo_root).expanduser().resolve()
    sources = check_sources(repo_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise QuickstartError("target", root, str(e),
                              "fix the permission or choose another --target, then run init again")
    if not root.is_dir():
        raise QuickstartError("target", root, "the target is not a directory",
                              "choose a directory with --target, then run init again")

    print("Quickstart init: %s" % root)
    created, kept = [], []

    name, exists = choose_entry(root)
    if exists:
        kept.append(name)
        print("KEEP %s (content unchanged; see PROMPT.md L2 - Upgrade check)" % name)
    else:
        text = ENTRY_TEMPLATE.replace("{name}", name)
        if write_new(root, name, text):
            created.append(name)
            print("CREATE %s" % name)
        else:
            kept.append(name)
            print("KEEP %s (content unchanged; see PROMPT.md L2 - Upgrade check)" % name)

    readme = README_TEMPLATE.replace("{name}", name)
    if write_new(root, "README.md", readme):
        created.append("README.md")
        print("CREATE README.md")
    else:
        kept.append("README.md")
        print("KEEP README.md")

    today = date.today().isoformat()
    memory = MEMORY_TEMPLATE.replace("{day}", today)
    if write_new(root, "MEMORY.md", memory):
        created.append("MEMORY.md")
        print("CREATE MEMORY.md")
    else:
        kept.append("MEMORY.md")
        print("KEEP MEMORY.md")

    now = without_dated_examples(read_source(sources["now"]))
    if write_new(root, "NOW.md", now):
        created.append("NOW.md")
        print("CREATE NOW.md")
    else:
        kept.append("NOW.md")
        print("KEEP NOW.md")

    log = render_log(read_source(sources["log"]), today)
    if write_new(root, "LOG.md", log):
        created.append("LOG.md")
        print("CREATE LOG.md")
    else:
        kept.append("LOG.md")
        print("KEEP LOG.md")

    # The governance CLI creates both directories; check them first so a symlink cannot lead it outside.
    ensure_dir(root, "scripts")
    ensure_dir(root, ".memory")
    install_governance(root, repo_root)

    for rel, label in (("scripts/health_check.py", "health_check"),
                       ("scripts/reconcile.py", "reconcile")):
        text = read_source(sources[label])
        if write_new(root, rel, text):
            created.append(rel)
            print("CREATE %s" % rel)
        else:
            kept.append(rel)
            print("KEEP %s" % rel)

    index = render_index(root, read_source(sources["index"]))
    if write_new(root, "INDEX.md", index):
        created.append("INDEX.md")
        print("CREATE INDEX.md")
    else:
        kept.append("INDEX.md")
        print("KEEP INDEX.md")

    print("Quickstart init: %d created, %d kept" % (len(created), len(kept)))
    print("Next (run inside the project):")
    print("  python3 scripts/health_check.py")
    print("  python3 scripts/reconcile.py")
    print("  python3 scripts/memory_governance.py doctor")
    return 0


def cmd_init(args):
    return init_project(Path(args.target), REPO_ROOT)


def run_command(argv, timeout, stdin_text=None):
    try:
        return subprocess.run(argv, input=stdin_text, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=child_env())
    except subprocess.TimeoutExpired:
        raise QuickstartError("subprocess", argv[0], "timed out after %d seconds" % timeout,
                              "run the command by hand to see where it waits")
    except OSError as e:
        raise QuickstartError("subprocess", argv[0], "%s: %s" % (type(e).__name__, e),
                              "check that this Python can run the command")


def last_line(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def tree_hash(root):
    digest = hashlib.sha256()
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not os.path.islink(os.path.join(dirpath, d)))
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, str(root)).replace(os.sep, "/")
            digest.update(rel.encode("utf-8") + b"\0")
            with open(full, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    digest.update(chunk)
            digest.update(b"\0")
    return digest.hexdigest()


def map_dates(root, yesterday, today):
    """Map the example's two fictional dates onto yesterday and today, in text files only."""
    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in (".credentials", ".git", ".memory"))
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            path = Path(dirpath) / name
            try:
                text = read_text(path)
            except OSError as e:
                raise QuickstartError("demo copy", path, str(e),
                                      "check that the temporary directory is writable")
            new = text.replace("2026-01-05", yesterday).replace("2026-01-06", today)
            if new != text:
                write_text_atomic(path, new)


def section_items(path, heading):
    items = []
    in_section = False
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped[3:].strip().lower() == heading.lower()
            continue
        if in_section and stripped.startswith(("- ", "* ")):
            items.append(stripped[2:])
    return items


def strip_date(text):
    return re.sub(r"^\[\d{4}-\d{2}-\d{2}\]\s*", "", text.strip())


def locate_decision(root, server):
    """Call the real Memory MCP memory_locate over stdio and return its text."""
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "quickstart-demo"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "memory_locate", "arguments": {"query": "export format decision"}}},
    ]
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in requests) + "\n"
    r = run_command([sys.executable, str(server), "--root", str(root), "--tools", "memory_locate"],
                    timeout=120, stdin_text=payload)
    if r.returncode != 0:
        raise QuickstartError("locate", server,
                              "the Memory MCP exited %d: %s" % (r.returncode, last_line(r.stderr)),
                              "run the Memory MCP by hand with --root %s" % root)
    for line in (r.stdout or "").splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if message.get("id") != 2:
            continue
        if "error" in message:
            raise QuickstartError("locate", server, "memory_locate returned an error: %s" % message["error"],
                                  "run memory_locate by hand against the temporary copy")
        result = message.get("result") or {}
        content = result.get("content") or []
        text = content[0].get("text", "") if content else ""
        if result.get("isError"):
            raise QuickstartError("locate", server, text or "memory_locate reported an error",
                                  "run memory_locate by hand against the temporary copy")
        return text
    raise QuickstartError("locate", server, "no memory_locate answer arrived",
                          "run the Memory MCP by hand with --root %s" % root)


def decision_path_from_locate(located):
    for line in located.splitlines():
        if not line.strip().startswith("|") or "`docs/export-decision.md`" not in line:
            continue
        match = re.search(r"`([^`]+)`", line)
        if match:
            return match.group(1), line.strip()
    return None, None


def cmd_demo(args):
    example = REPO_ROOT / EXAMPLE_REL
    if not example.is_dir():
        raise QuickstartError("demo copy", example, "the fictional example directory is missing",
                              "run demo from a full wallaby-agent-rules clone")
    before = tree_hash(example)
    temp_root = Path(tempfile.mkdtemp(prefix="wallaby-quickstart-demo-"))
    work = temp_root / "project"
    try:
        try:
            shutil.copytree(str(example), str(work))
        except OSError as e:
            raise QuickstartError("demo copy", example, str(e),
                                  "check that the system temporary directory is writable")
        today = date.today()
        map_dates(work, (today - timedelta(days=1)).isoformat(), today.isoformat())
        print("Quickstart demo: a temporary copy of examples/first-success (the repo copy stays unchanged).")

        r = run_command([sys.executable, str(Path(__file__).resolve()), "--target", str(work), "init"],
                        timeout=180)
        if r.returncode != 0:
            raise QuickstartError("step 1 init", work, last_line(r.stderr) or last_line(r.stdout),
                                  "run init by hand on a copy of examples/first-success")
        print("step 1/7 init: governance installed in the temporary copy")

        server = REPO_ROOT / MCP_SERVER_REL
        if not server.is_file():
            raise QuickstartError("step 2 locate", server, "the Memory MCP server is missing",
                                  "run demo from a full wallaby-agent-rules clone")
        located = locate_decision(work, server)
        rel, row = decision_path_from_locate(located)
        if not rel:
            raise QuickstartError("step 2 locate", work, "memory_locate did not return the export-decision row",
                                  "run memory_locate with the query 'export format decision' by hand")
        print("step 2/7 locate: memory_locate returned the INDEX row for `%s`" % rel)
        print("INDEX row: %s" % row)

        doc = (work / rel).resolve()
        if not _within(work.resolve(), doc) or not doc.is_file():
            raise QuickstartError("step 3 decision", doc, "the INDEX row points outside the project or at no file",
                                  "check the INDEX row and the example tree")
        decision = next((line.strip() for line in read_source(doc, "step 3 decision").splitlines()
                         if line.strip().lower().startswith("decision:")), "")
        if not decision:
            raise QuickstartError("step 3 decision", doc, "the decision document has no Decision: line",
                                  "add one Decision: line to docs/export-decision.md")
        print("step 3/7 decision: %s" % decision)

        now_line = next((x for x in section_items(work / "NOW.md", "In flight")
                         if "runbook" in x.lower()), None)
        log_line = next((x for x in section_items(work / "LOG.md", "2026-01") if "runbook" in x.lower()
                         and re.search(r"\bpublished\b", x, re.I)), None)
        if not now_line or not log_line:
            raise QuickstartError("step 4 contradiction", work / "NOW.md",
                                  "the example no longer shows LOG.md done while NOW.md is in flight",
                                  "restore the runbook lines in examples/first-success/")
        print("step 4/7 contradiction: LOG.md says the runbook is done while NOW.md still lists it in flight")
        print("NOW.md: %s" % strip_date(now_line))
        print("LOG.md: %s" % strip_date(log_line))

        r = run_command([sys.executable, str(work / "scripts" / "reconcile.py"), str(work)], timeout=120)
        if r.returncode != 1:
            raise QuickstartError("step 5 reconcile", work / "scripts" / "reconcile.py",
                                  "reconcile exited %d, expected 1 before the fix" % r.returncode,
                                  "run reconcile by hand on the temporary copy")
        print("step 5/7 reconcile before the fix: exit=1 (as expected)")

        now_path = work / "NOW.md"
        kept_lines, removed, in_flight = [], 0, False
        for line in read_text(now_path).splitlines(True):
            if line.strip().startswith("## "):
                in_flight = line.strip()[3:].strip().lower() == "in flight"
            if in_flight and line.strip().startswith(("- ", "* ")) \
                    and "runbook" in line.lower() and removed == 0:
                removed += 1
                continue
            kept_lines.append(line)
        if removed != 1:
            raise QuickstartError("step 6 fix", now_path,
                                  "expected one in-flight runbook line in the temporary NOW.md",
                                  "restore the example NOW.md")
        write_text_atomic(now_path, "".join(kept_lines))
        print("step 6/7 fix: removed the finished item from the temporary NOW.md only")

        r = run_command([sys.executable, str(work / "scripts" / "reconcile.py"), str(work)], timeout=120)
        if r.returncode != 0:
            raise QuickstartError("step 7 reconcile", work / "scripts" / "reconcile.py",
                                  "exit=%d: %s" % (r.returncode, last_line(r.stdout)),
                                  "run reconcile by hand on the temporary copy")
        reconcile_last = last_line(r.stdout)
        r = run_command([sys.executable, str(work / "scripts" / "health_check.py"), str(work)], timeout=120)
        if r.returncode != 0:
            raise QuickstartError("step 7 health_check", work / "scripts" / "health_check.py",
                                  "exit=%d: %s" % (r.returncode, last_line(r.stdout)),
                                  "run health_check by hand on the temporary copy")
        health_last = last_line(r.stdout)
        r = run_command([sys.executable, str(work / "scripts" / "memory_governance.py"),
                         "--target", str(work), "doctor"], timeout=180)
        if r.returncode != 0:
            raise QuickstartError("step 7 doctor", work / "scripts" / "memory_governance.py",
                                  "exit=%d: %s" % (r.returncode, last_line(r.stdout)),
                                  "run the governance doctor by hand on the temporary copy")
        doctor_last = last_line(r.stdout)
        print("step 7/7 checks: reconcile exit=0 (%s); health_check exit=0 (%s); doctor exit=0 (%s)"
              % (reconcile_last, health_last, doctor_last))
        print("Doctor: PASS")
        return 0
    finally:
        shutil.rmtree(str(temp_root), ignore_errors=True)
        after = tree_hash(example)
        if after != before:
            raise QuickstartError("source hash", example, "the example source changed during demo",
                                  "restore examples/first-success/ from git")


def cmd_mcp_config(args):
    if not getattr(args, "print_only", False):
        raise QuickstartError("mcp-config", "-", "--print is required; quickstart never writes client configs",
                              "python3 extras/memory-governance/quickstart.py --target . mcp-config --print")
    target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        raise QuickstartError("mcp-config", target, "the target is not a directory",
                              "pass an existing project directory with --target")
    server = (REPO_ROOT / MCP_SERVER_REL).resolve()
    if not server.is_file():
        raise QuickstartError("mcp-config", server, "the Memory MCP server is missing",
                              "run mcp-config from a full wallaby-agent-rules clone")
    config = {"mcpServers": {"wallaby-memory": {
        "command": str(Path(sys.executable).resolve()),
        "args": [str(server), "--root", str(target)],
    }}}
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return 0


def print_failure(error, final=None):
    print("quickstart: FAILED", file=sys.stderr)
    print("  stage: %s" % error.stage, file=sys.stderr)
    print("  file: %s" % error.path, file=sys.stderr)
    print("  detail: %s" % error.detail, file=sys.stderr)
    print("  next: %s" % error.next_step, file=sys.stderr)
    if final:
        print(final)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Offline first success for wallaby-agent-rules: init, demo, mcp-config.")
    parser.add_argument("--target", default=".", help="project root, default: current directory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create the memory files and install the governance CLI, never overwriting")
    sub.add_parser("demo", help="run the fictional first-success example in a temporary copy")
    mcp = sub.add_parser("mcp-config", help="print the wallaby-memory mcpServers entry")
    mcp.add_argument("--print", dest="print_only", action="store_true",
                     help="print JSON to stdout; writing client configs is not supported")
    return parser


def main(argv=None):
    use_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "demo":
            return cmd_demo(args)
        if args.command == "mcp-config":
            return cmd_mcp_config(args)
    except QuickstartError as e:
        if args.command == "demo":
            print_failure(e, final="Doctor: FAIL")
            return 1
        print_failure(e)
        return 2
    except OSError as e:
        error = QuickstartError("unexpected", "-", "%s: %s" % (type(e).__name__, e),
                                "run the command again with a writable target")
        if args.command == "demo":
            print_failure(error, final="Doctor: FAIL")
            return 1
        print_failure(error)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
