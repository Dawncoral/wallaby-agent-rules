#!/usr/bin/env python3
"""Memory governance CLI: conduction, premises, contradictions, and receipts.

Zero dependencies. Python 3.8+. The scanner is read-only; only explicit init,
impact --record, verify, contradiction mutations, map sync, and split write.

1.4.3 closes the loop between the registries and the memory files:
  route   one compact card per change: what to reuse, which map components,
          events and surfaces, the tier, and only the premises the change touches
  lookup  read-only rows from CAPABILITIES.md or MAP.md (the MCP server calls it)
  audit   unregistered capabilities, ghost entries, orphans, pointer stubs, volumes
  map     map sync keeps a generated block in MAP.md; --check reports drift
  split   month volumes for LOG.md (automatic), topic splits for MEMORY.md and
          INDEX.md (nominated, applied only with --confirm), rollback, verify
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.4.3"
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".credentials", ".memory", "node_modules",
    ".venv", "venv", "env", "__pycache__", ".pytest_cache", "dist",
    "build", ".next", ".nuxt", "out", "target", ".idea", ".vscode",
}
TEXT_EXTS = {
    ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml",
    ".txt", ".html", ".css", ".sh", ".sql",
}
MAX_FILE_BYTES = 512 * 1024
MAX_MATCHES = 200
MAX_FILES = 5000

DEFAULT_IMPACT = {
    "version": 1,
    "events": {
        "feature": {"surfaces": ["MAP.md", "CAPABILITIES.md", "INDEX.md", "CHANGELOG.md"], "premise_review": True, "contradiction_review": False},
        "mechanism": {"surfaces": ["MAP.md", "CHANGELOG.md", "PREMISES"], "premise_review": True, "contradiction_review": True},
        "document": {"surfaces": ["INDEX.md", "CAPABILITIES.md"], "premise_review": False, "contradiction_review": False},
        "external_copy": {"surfaces": ["README.md", "CHANGELOG.md"], "premise_review": False, "contradiction_review": True},
        "automation": {"surfaces": ["CAPABILITIES.md", "MAP.md"], "premise_review": True, "contradiction_review": False},
        "decision": {"surfaces": ["LOG.md", "NOW.md", "PREMISES"], "premise_review": True, "contradiction_review": True},
        "skill": {"surfaces": ["CAPABILITIES.md", "INDEX.md", "CHANGELOG.md"], "premise_review": False, "contradiction_review": False},
        "file_move": {"surfaces": ["INDEX.md", "MAP.md", "CAPABILITIES.md"], "premise_review": False, "contradiction_review": False},
        "closure": {"surfaces": ["LOG.md", "NOW.md"], "premise_review": False, "contradiction_review": False},
    },
}
DEFAULT_PREMISES = {
    "version": 1,
    "premises": [
        {
            "id": "P-001",
            "level": "P2",
            "assertion": "The project has a README, so a new session has an onboarding entry point.",
            "failure_signal": {"type": "file_missing", "path": "README.md"},
            "detection": "Run premise check before relying on the project map.",
            "status": "active",
            "source": "sanitized example",
        }
    ],
}
DEFAULT_CONTRADICTIONS = {
    "version": 1,
    "contradictions": [
        {
            "id": "C-001",
            "old": "The project map is optional.",
            "new": "The project map is maintained when files change.",
            "evidence": "README.md",
            "status": "resolved",
            "history": [
                {"ts": "2026-01-01T00:00:00+00:00", "status": "open", "evidence": "sanitized example"},
                {"ts": "2026-01-02T00:00:00+00:00", "status": "resolved", "evidence": "README.md"},
            ],
        }
    ],
}


class GovernanceError(Exception):
    pass


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise GovernanceError(f"missing {path}; run init first")
    except (OSError, json.JSONDecodeError) as e:
        raise GovernanceError(f"cannot read {path}: {e}")


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(50):
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                return self
            except FileExistsError:
                time.sleep(0.1)
        raise GovernanceError(f"could not acquire lock {self.path}; another writer may be active")

    def __exit__(self, *_):
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def memory_dir(root: Path):
    return root / ".memory"


def config_path(root: Path, name: str):
    return memory_dir(root) / name


def receipts_path(root: Path):
    return config_path(root, "receipts.jsonl")


def append_receipt(root: Path, entry):
    path = receipts_path(root)
    with FileLock(Path(str(path) + ".lock")):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_receipts(root: Path):
    path = receipts_path(root)
    if not path.exists():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise GovernanceError(f"bad receipt JSON at line {n}: {e}")
        rows.append(row)
    return rows


def iter_text_files(root: Path):
    count = 0
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in sorted(files):
            path = Path(base) / name
            if path.suffix.lower() not in TEXT_EXTS or not path.is_file():
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    yield path, "over_size"
                    continue
            except OSError:
                yield path, "stat_failed"
                continue
            count += 1
            if count > MAX_FILES:
                raise GovernanceError(f"scan stopped at {MAX_FILES} files; narrow the project or raise the explicit limit")
            yield path, None


def scan(root: Path, terms, allow=None):
    allow = allow or []
    matches = []
    skipped = []
    truncated = False
    for path, skip_reason in iter_text_files(root):
        rel = path.relative_to(root).as_posix()
        if skip_reason:
            skipped.append({"path": rel, "reason": skip_reason})
            continue
        if any(fnmatch.fnmatch(rel, pattern) for pattern in allow):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped.append({"path": rel, "reason": "read_failed"})
            continue
        found = {term: text.count(term) for term in terms if term and text.count(term)}
        if found:
            matches.append({"path": rel, "count": sum(found.values()), "terms": sorted(found)})
            if len(matches) >= MAX_MATCHES:
                truncated = True
                break
    return matches, truncated, skipped


def cmd_init(args):
    root = Path(args.target).resolve()
    root.mkdir(parents=True, exist_ok=True)
    mem = memory_dir(root)
    mem.mkdir(exist_ok=True)
    created = []
    for name, data in [("impact.json", DEFAULT_IMPACT), ("premises.json", DEFAULT_PREMISES), ("contradictions.json", DEFAULT_CONTRADICTIONS)]:
        path = mem / name
        if path.exists():
            print(f"KEEP {path.relative_to(root)}")
        else:
            atomic_json(path, data)
            created.append(str(path.relative_to(root)))
    receipts = receipts_path(root)
    receipts.touch(exist_ok=True)
    target_script = root / "scripts" / "memory_governance.py"
    target_script.parent.mkdir(exist_ok=True)
    source = Path(__file__).resolve()
    if target_script.resolve() != source and not target_script.exists():
        shutil.copy2(source, target_script)
        created.append(str(target_script.relative_to(root)))
    else:
        print(f"KEEP {target_script.relative_to(root)}")
    print(f"Initialized governance in {root}; created={created or ['nothing new']}")
    print("Next: python3 scripts/memory_governance.py doctor")
    return 0


def script_version(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise GovernanceError(f"cannot read CLI {path}: {e}")
    for line in text.splitlines():
        if line.startswith("VERSION = "):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise GovernanceError(f"VERSION not found in {path}")


def version_tuple(version: str):
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        raise GovernanceError(f"invalid version {version!r}; expected x.y.z")


def cmd_upgrade(args):
    root = Path(args.target).resolve()
    target = root / "scripts" / "memory_governance.py"
    source = Path(args.source).resolve() if args.source else Path(__file__).resolve()
    target_version = script_version(target)
    source_version = script_version(source)
    print(f"CURRENT {target_version} {target}")
    print(f"AVAILABLE {source_version} {source}")
    if source.resolve() == target.resolve() or source.read_bytes() == target.read_bytes():
        print("Already current; no files changed.")
        return 0
    if version_tuple(source_version) < version_tuple(target_version):
        raise GovernanceError(f"refusing downgrade {target_version} -> {source_version}")
    backup = memory_dir(root) / "backups" / f"memory_governance_{target_version}.py"
    print(f"BACKUP {backup}")
    if not args.apply:
        print(f"DRY RUN would replace only the CLI {target} -> {source_version}; memory data and all other files stay untouched.")
        print("Run with --apply to back up and replace the CLI, then verify it starts.")
        return 0
    with FileLock(memory_dir(root) / "upgrade.lock"):
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        fd, tmp_name = tempfile.mkstemp(prefix="memory_governance.upgrade.", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(source.read_bytes())
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        try:
            result = subprocess.run([sys.executable, str(target), "--version"], text=True, capture_output=True)
            if result.returncode != 0 or result.stdout.strip() != source_version:
                raise GovernanceError("new CLI failed the version check")
        except Exception as e:
            shutil.copy2(backup, target)
            raise GovernanceError(f"upgrade failed; original CLI restored: {e}")
    print(f"UPGRADED {target_version} -> {source_version}; backup={backup}")
    print("Memory data, configs, receipts, and all other project files were not modified.")
    return 0


def validate_impact(data):
    if data.get("version") != 1 or not isinstance(data.get("events"), dict):
        raise GovernanceError("impact.json needs version=1 and an events object")
    for name, rule in data["events"].items():
        if not rule.get("surfaces") or not isinstance(rule["surfaces"], list):
            raise GovernanceError(f"event {name} needs a non-empty surfaces list")


def cmd_impact(args):
    root = Path(args.target).resolve()
    data = load_json(config_path(root, "impact.json"))
    validate_impact(data)
    if args.event not in data["events"]:
        raise GovernanceError(f"unknown event {args.event}; choose from {', '.join(sorted(data['events']))}")
    terms = [t for t in args.terms if t]
    if not terms:
        raise GovernanceError("at least one non-empty --terms value is required")
    rule = data["events"][args.event]
    matches, truncated, skipped = scan(root, terms)
    print(f"EVENT {args.event}")
    print("SURFACES " + ", ".join(rule["surfaces"]))
    print(f"PREMISE_REVIEW {'required' if rule.get('premise_review') else 'not required'}")
    print(f"CONTRADICTION_REVIEW {'required' if rule.get('contradiction_review') else 'not required'}")
    print(f"MATCHES {len(matches)}")
    for row in matches:
        print(f"  {row['path']} ({row['count']})")
    matched_paths = [row["path"] for row in matches]
    components = registry_hits(root, "map", terms, matched_paths)
    capabilities = registry_hits(root, "capability", terms, matched_paths)
    print("COMPONENTS " + ("skipped (no MAP.md)" if components is None else ", ".join(components) or "none"))
    print("CAPABILITIES " + ("skipped (no CAPABILITIES.md)" if capabilities is None else ", ".join(capabilities) or "none"))
    if truncated:
        print(f"WARNING scan stopped after {MAX_MATCHES} matching files; narrow the terms", file=sys.stderr)
    if skipped:
        print(f"WARNING skipped {len(skipped)} unreadable or oversized file(s): {skipped}", file=sys.stderr)
    if args.record:
        receipt = {
            "type": "impact", "receipt": next_receipt_id(root), "event": args.event,
            "terms": terms, "matches": matches, "truncated": truncated, "skipped": skipped,
            "surfaces": rule["surfaces"], "status": "pending", "ts": now_iso(),
            "components": components or [], "capabilities": capabilities or [],
        }
        append_receipt(root, receipt)
        print(f"RECEIPT {receipt['receipt']} pending; run verify after reviewing the surfaces")
    return 0


def next_receipt_id(root: Path):
    highest = 0
    for row in read_receipts(root):
        rid = str(row.get("receipt", ""))
        if rid.startswith("R-"):
            try:
                highest = max(highest, int(rid[2:]))
            except ValueError:
                continue
    return f"R-{highest + 1:06d}"


def cmd_verify(args):
    root = Path(args.target).resolve()
    rows = read_receipts(root)
    impacts = [r for r in rows if r.get("type") == "impact" and r.get("receipt") == args.receipt]
    if not impacts:
        raise GovernanceError(f"receipt {args.receipt} not found")
    verified = any(r.get("type") == "verification" and r.get("receipt") == args.receipt for r in rows)
    if verified:
        print(f"{args.receipt} already verified")
        return 0
    impact = impacts[-1]
    matches, truncated, skipped = scan(root, impact["terms"], args.allow)
    if matches or truncated or skipped:
        print(f"NOT VERIFIED {args.receipt}: {len(matches)} unresolved and {len(skipped)} unread file(s)")
        for row in matches:
            print(f"  {row['path']} ({row['count']})")
        if skipped:
            print(f"  unreadable or oversized: {skipped}")
        print("Update the references or allow intentional historical mentions with --allow <glob>.")
        return 1
    append_receipt(root, {
        "type": "verification", "receipt": args.receipt, "status": "verified",
        "evidence": "zero unresolved matches", "ts": now_iso(),
    })
    print(f"VERIFIED {args.receipt}: zero unresolved matches")
    return 0


def json_path(data, path):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def evaluate_premise(root: Path, premise):
    signal = premise.get("failure_signal", {})
    kind = signal.get("type")
    path = signal.get("path", "")
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return "failing", "signal path leaves the project"
    if kind == "file_missing":
        return ("failing", f"missing {path}") if not target.exists() else ("ok", f"present {path}")
    if kind == "file_exists":
        return ("failing", f"unexpected {path}") if target.exists() else ("ok", f"absent {path}")
    if kind == "text_contains":
        if not target.is_file():
            return "failing", f"missing {path}"
        text = target.read_text(encoding="utf-8", errors="replace")
        value = signal.get("value", "")
        return ("ok", f"text found in {path}") if value in text else ("failing", f"expected text absent in {path}")
    if kind == "json_equals":
        if not target.is_file():
            return "failing", f"missing {path}"
        data = load_json(target)
        actual = json_path(data, signal.get("key", ""))
        return ("ok", f"JSON value matches in {path}") if actual == signal.get("expected") else ("failing", f"JSON value differs in {path}: {actual!r}")
    if kind == "manual":
        return "unverified", "manual evidence required"
    return "failing", f"unknown signal type {kind!r}"


def premise_rows(root: Path):
    data = load_json(config_path(root, "premises.json"))
    if data.get("version") != 1 or not isinstance(data.get("premises"), list):
        raise GovernanceError("premises.json needs version=1 and a premises list")
    rows = []
    seen = set()
    for premise in data["premises"]:
        pid = premise.get("id")
        if not pid or pid in seen:
            raise GovernanceError(f"duplicate or missing premise id {pid!r}")
        seen.add(pid)
        if premise.get("level") not in {"P0", "P1", "P2"}:
            raise GovernanceError(f"premise {pid} needs level P0, P1, or P2")
        if premise.get("status") == "retired":
            continue
        if not premise.get("assertion") or not premise.get("detection"):
            raise GovernanceError(f"premise {pid} needs assertion and detection")
        state, detail = evaluate_premise(root, premise)
        rows.append((premise, state, detail))
    return rows


def cmd_premise(args):
    root = Path(args.target).resolve()
    rows = premise_rows(root)
    code = 0
    for premise, state, detail in rows:
        print(f"{premise['id']} {premise['level']} {state.upper()}: {detail}")
        if state == "failing":
            code = max(code, 2 if premise["level"] == "P0" else 1 if premise["level"] == "P1" else 0)
        elif state == "unverified" and premise["level"] in {"P0", "P1"}:
            code = max(code, 1)
    if not rows:
        print("No active premises.")
    return code


def contradiction_data(root: Path):
    data = load_json(config_path(root, "contradictions.json"))
    if data.get("version") != 1 or not isinstance(data.get("contradictions"), list):
        raise GovernanceError("contradictions.json needs version=1 and a contradictions list")
    return data


def cmd_contradict(args):
    root = Path(args.target).resolve()
    data = contradiction_data(root)
    rows = data["contradictions"]
    if args.action == "add":
        nums = [int(r["id"].split("-")[-1]) for r in rows if r.get("id", "").startswith("C-") and r["id"].split("-")[-1].isdigit()]
        cid = f"C-{max(nums or [0]) + 1:03d}"
        row = {
            "id": cid, "old": args.old, "new": args.new, "evidence": args.evidence,
            "status": "open", "history": [{"ts": now_iso(), "status": "open", "evidence": args.evidence}],
        }
        rows.append(row)
        atomic_json(config_path(root, "contradictions.json"), data)
        print(f"ADDED {cid} open")
        return 0
    if args.action == "resolve":
        found = next((r for r in rows if r.get("id") == args.id), None)
        if not found:
            raise GovernanceError(f"contradiction {args.id} not found")
        found["history"].append({"ts": now_iso(), "status": "resolved", "evidence": args.evidence})
        found["status"] = "resolved"
        found["evidence"] = args.evidence
        atomic_json(config_path(root, "contradictions.json"), data)
        print(f"RESOLVED {args.id}")
        return 0
    open_rows = [r for r in rows if r.get("status") != "resolved"]
    if args.action == "list":
        for row in rows:
            if not args.open or row.get("status") != "resolved":
                print(f"{row.get('id')} {row.get('status')}: {row.get('old')} -> {row.get('new')}")
        return 0
    if open_rows:
        print(f"OPEN CONTRADICTIONS {len(open_rows)}")
        for row in open_rows:
            print(f"  {row.get('id')}: {row.get('old')}")
        return 1
    print("No open contradictions.")
    return 0


def cmd_doctor(args):
    root = Path(args.target).resolve()
    impact = load_json(config_path(root, "impact.json"))
    validate_impact(impact)
    code = cmd_premise(args)
    contradictions = contradiction_data(root)["contradictions"]
    open_rows = [r for r in contradictions if r.get("status") != "resolved"]
    receipts = read_receipts(root)
    verified = {r.get("receipt") for r in receipts if r.get("type") == "verification"}
    pending = [r for r in receipts if r.get("type") == "impact" and r.get("receipt") not in verified]
    print(f"CONTRADICTIONS open={len(open_rows)}")
    print(f"RECEIPTS pending={len(pending)}")
    if open_rows or pending:
        code = max(code, 1)
    report = audit_report(root)
    counts = " ".join(f"{k}={len(report[k])}" for k in AUDIT_KINDS)
    print(f"AUDIT {counts}" + (f" (skipped: {'; '.join(report['skipped'])})" if report["skipped"] else ""))
    map_state = map_sync(root, check=True)
    print(f"MAP {map_state['status']}")
    if any(report[k] for k in AUDIT_KINDS) or map_state["status"] == "drift":
        code = max(code, 1)
    if code == 0:
        print("DOCTOR OK")
    else:
        print(f"DOCTOR FINDINGS exit={code}")
    return code


# ---------------------------------------------------------------------------
# 1.4.3 · shared readers for MAP.md, CAPABILITIES.md and INDEX.md
# ---------------------------------------------------------------------------

MAP_NAME = "MAP.md"
CAPS_NAME = "CAPABILITIES.md"
INDEX_NAME = "INDEX.md"
LOG_NAME = "LOG.md"
MEMORY_NAME = "MEMORY.md"
OUTPUT_BUDGET = 2048   # bytes: the default size of a route card
LIST_CAP = 5           # rows per list in a default card; --detail lifts it
TEXT_CAP = 160         # characters per assertion or note in a default card
CAP_COLUMNS = (("name", ("capability", "能力")), ("entry", ("entry", "入口")), ("triggers", ("trigger", "触发")),
               ("state", ("state", "status", "状态")), ("call", ("call", "output", "调用")), ("form", ("form", "形态")))
MAP_COLUMNS = (("component", ("component", "组件")), ("keywords", ("keyword", "关键词", "关键字")),
               ("details", ("detail", "详情", "正本")), ("job", ("job", "职责", "作用")))
_SEP_CELL = re.compile(r"^:?-+:?$")
_KW_SPLIT = re.compile(r"[,，、;；/]+")
_TICKED = re.compile(r"`([^`]+)`")


def read_text(path: Path):
    with open(str(path), encoding="utf-8", newline="") as f:
        return f.read()


def write_text_atomic(path: Path, text: str, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        if path.exists():
            mode = path.stat().st_mode & 0o777
        else:
            mask = os.umask(0)
            os.umask(mask)
            mode = 0o666 & ~mask
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def sha256_text(text: str):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def norm_path(p: str):
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def relp(root: Path, p: Path):
    return Path(p).resolve().relative_to(root.resolve()).as_posix()


def clean(cell: str):
    return (cell or "").replace("`", "").strip()


def _cells(line: str):
    s = line.strip()
    if not s.startswith("|"):
        return None
    s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_sep(cells):
    return bool(cells) and all(_SEP_CELL.match(c) for c in cells)


def _placeholder(value: str):
    v = clean(value)
    return v.startswith("<") and v.endswith(">")


def parse_registry(text: str, columns, required):
    """Rows of every Markdown table whose header names the registry's columns.

    Each row keeps its `## ` area, line number, and raw cells; template placeholder rows are skipped."""
    rows, area, fence = [], "", False
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            fence = not fence
            i += 1
            continue
        if fence:
            i += 1
            continue
        if line.startswith("## "):
            area = line[3:].strip()
        header = _cells(line)
        nxt = _cells(lines[i + 1]) if i + 1 < len(lines) else None
        if header and nxt and _is_sep(nxt):
            keys = {}
            for idx, cell in enumerate(header):
                low = cell.lower()
                for key, aliases in columns:
                    if key not in keys and any(a in low for a in aliases):
                        keys[key] = idx
                        break
            i += 2
            while i < len(lines) and _cells(lines[i]) is not None:
                cells = _cells(lines[i])
                if all(k in keys for k in required):
                    row = {k: (cells[idx] if idx < len(cells) else "") for k, idx in keys.items()}
                    if not _placeholder(row[required[0]]) and clean(row[required[0]]):
                        row.update(area=area, line=i + 1, _cells=cells, _keys=keys)
                        rows.append(row)
                i += 1
            continue
        i += 1
    return rows


def load_caps(root: Path):
    p = root / CAPS_NAME
    return parse_registry(read_text(p), CAP_COLUMNS, ("name", "entry")) if p.is_file() else None


def load_map(root: Path):
    p = root / MAP_NAME
    return parse_registry(read_text(p), MAP_COLUMNS, ("component", "keywords")) if p.is_file() else None


def keywords(cell: str):
    return [w.strip() for w in _KW_SPLIT.split(clean(cell).lower()) if len(w.strip()) >= 2 and not _placeholder(w)]


def name_variants(cell: str):
    """`health_check.py` is also found as "health_check" and "health check"."""
    name = clean(cell).lower()
    out = [name] if len(name) >= 3 else []
    stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0] if "." in name.rsplit("/", 1)[-1] else name.rsplit("/", 1)[-1]
    for v in (stem, re.sub(r"[_-]+", " ", stem)):
        if len(v) >= 3 and v not in out:
            out.append(v)
    return out


def kw_hit(kw: str, text: str):
    """Whole-word match for Latin keywords (plural and past forms allowed); substring match for CJK."""
    if re.match(r"^[a-z0-9][a-z0-9 ._+-]*$", kw):
        return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?:s|es|ed|d|ing)?(?![a-z0-9])", text) is not None
    return kw in text


def cell_paths(cell: str):
    """Path-like tokens in a cell: backticked first, else the bare cell; commands and URLs are skipped."""
    toks = _TICKED.findall(cell or "") or [clean(cell)]
    out = []
    for t in toks:
        t = norm_path(t.split("#", 1)[0])
        if not t or " " in t or t.startswith(("http://", "https://", "<", "(")):
            continue
        if "/" in t or re.search(r"\.[A-Za-z0-9]{1,6}$", t):
            out.append(t)
    return out


def path_hit(changed: str, target: str):
    c, t = norm_path(changed).rstrip("/"), norm_path(target).rstrip("/")
    return bool(c and t) and (c == t or c.startswith(t + "/") or t.startswith(c + "/"))


def glob_hit(path: str, pattern: str):
    """gitignore-like: no slash = any basename; trailing slash = directory prefix; `**` = any depth."""
    path, pattern = norm_path(path), norm_path(pattern)
    if not pattern:
        return False
    if pattern.endswith("/"):
        return path == pattern.rstrip("/") or path.startswith(pattern)
    if "**" in pattern:
        return fnmatch.fnmatchcase(path, pattern.replace("**/", "*").replace("**", "*"))
    if "/" not in pattern:
        return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)
    ps, qs = path.split("/"), pattern.split("/")
    return len(ps) == len(qs) and all(fnmatch.fnmatchcase(a, b) for a, b in zip(ps, qs))


def index_texts(root: Path):
    """INDEX.md plus the parts it points to (`INDEX/<part>.md`), one hop."""
    main = root / INDEX_NAME
    if not main.is_file():
        return []
    out = [(INDEX_NAME, read_text(main))]
    for rel in sorted(set(re.findall(r"`(INDEX/[^`\s]+\.md)`", out[0][1]))):
        if (root / rel).is_file():
            out.append((rel, read_text(root / rel)))
    return out


def index_row_paths(root: Path):
    paths = []
    for _, text in index_texts(root):
        for line in text.splitlines():
            s = line.strip()
            if not (s.startswith("|") or s.startswith("- ")) or _is_sep(_cells(s) or []):
                continue
            found = cell_paths(s.split("|")[1] if s.startswith("|") else s)
            if found:
                paths.append(found[0])
    return paths


def load_impact_or_default(root: Path):
    path = config_path(root, "impact.json")
    if not path.exists():
        return DEFAULT_IMPACT, "built-in defaults"
    data = load_json(path)
    validate_impact(data)
    return data, ".memory/impact.json"


def walk_files(root: Path, limit=50000):
    count = 0
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            count += 1
            if count > limit:
                return
            yield (Path(base) / name).relative_to(root).as_posix()


def registry_hits(root: Path, registry: str, terms, matched_paths):
    """Names of MAP components or capabilities that an impact scan touches (None when the file is absent)."""
    rows = load_map(root) if registry == "map" else load_caps(root)
    if rows is None:
        return None
    name_key, cols = ("component", ("component", "keywords", "details")) if registry == "map" else ("name", ("name", "entry", "triggers"))
    hits = []
    for r in rows:
        hay = " ".join(clean(r.get(c, "")) for c in cols).lower()
        targets = [p for c in cols for p in cell_paths(r.get(c, ""))]
        if any(t.lower() in hay for t in terms) or any(path_hit(m, t) for m in matched_paths for t in targets):
            name = clean(r[name_key])
            if name not in hits:
                hits.append(name)
    return hits


# ---------------------------------------------------------------------------
# 1.4.3 · route: the reflex card
# ---------------------------------------------------------------------------

DEFAULT_MATCH = {
    "feature": {"words": ["feature", "add", "new", "introduce", "功能", "新增"], "paths": []},
    "mechanism": {"words": ["rule", "policy", "mechanism", "threshold", "workflow", "process", "规则", "机制", "流程", "阈值"],
                  "paths": [".memory/"]},
    "document": {"words": ["doc", "docs", "documentation", "readme", "guide", "typo", "wording", "文档", "说明", "错别字"],
                 "paths": ["*.md", "docs/"]},
    "external_copy": {"words": ["announce", "announcement", "blog", "tweet", "newsletter", "landing page", "marketing",
                                "press", "对外", "文案", "博客", "推文", "公告"], "paths": []},
    "automation": {"words": ["script", "cron", "schedule", "scheduled", "automate", "automation", "hook", "ci", "pipeline",
                             "脚本", "定时", "自动化"], "paths": ["scripts/", "bin/", ".github/workflows/"]},
    "decision": {"words": ["decide", "decision", "approve", "决定", "决策", "拍板"], "paths": []},
    "skill": {"words": ["skill", "技能"], "paths": ["skills/", "SKILL.md"]},
    "file_move": {"words": ["move", "rename", "relocate", "移动", "改名", "迁移"], "paths": []},
    "closure": {"words": ["done", "finish", "close", "closeout", "wrap up", "shipped", "收工", "完成", "收尾"], "paths": []},
}
DEFAULT_LIGHT = {"document", "closure"}
DEFAULT_ALWAYS_HEAVY = {"external_copy"}
DEFAULT_RISK = {
    "words": ["publish", "release", "deploy", "delete", "remove", "drop", "migrate", "migration", "credential", "secret",
              "password", "api key", "production", "payment", "billing", "pricing", "refund", "irreversible",
              "发布", "上线", "部署", "删除", "迁移", "凭证", "密钥", "密码", "生产", "付款", "支付", "计费", "价格", "退款", "不可逆"],
    "paths": [".env", ".env.*", "*.pem", "*.key", ".credentials/", "**/migrations/**"],
}
DEFAULT_CAPABILITY_GLOBS = ["scripts/*.py", "scripts/*.sh", "scripts/*.js", "scripts/*.mjs", "scripts/*.ts", "scripts/*.rb",
                            "bin/*", "skills/*/SKILL.md", ".claude/skills/*/SKILL.md",
                            ".github/workflows/*.yml", ".github/workflows/*.yaml"]
DEFAULT_CAPABILITY_EXEMPT = ["scripts/memory_governance.py", "scripts/health_check.py", "scripts/reconcile.py",
                             "scripts/__init__.py"]


def _clip(text, detail):
    text = " ".join(str(text or "").split())
    return text if detail or len(text) <= TEXT_CAP else text[:TEXT_CAP - 1] + "…"


def _audit_config(impact):
    cfg = impact.get("audit") if isinstance(impact.get("audit"), dict) else {}
    globs = cfg.get("capability_globs") if isinstance(cfg.get("capability_globs"), list) else DEFAULT_CAPABILITY_GLOBS
    exempt = cfg.get("exempt") if isinstance(cfg.get("exempt"), list) else DEFAULT_CAPABILITY_EXEMPT
    return globs, exempt


def capability_like(rel: str, globs, exempt):
    return any(glob_hit(rel, g) for g in globs) and not any(glob_hit(rel, g) for g in exempt)


def registered_in(rel: str, caps_text: str):
    if rel in caps_text:
        return True
    parent, _, base = rel.rpartition("/")
    if base == "SKILL.md":
        skill = parent.rsplit("/", 1)[-1]
        return parent in caps_text or (len(skill) >= 4 and skill in caps_text)
    return base in caps_text


def route_card(root: Path, intent: str, paths=(), events=(), reversible=False, single_area=False, detail=False):
    impact, config = load_impact_or_default(root)
    text = " ".join((intent or "").lower().split())
    paths = [norm_path(p) for p in paths if p and p.strip()]
    rules = impact["events"]
    hit = OrderedDict()
    for name in events:
        if name not in rules:
            raise GovernanceError(f"unknown event {name}; choose from {', '.join(sorted(rules))}")
        hit[name] = "named with --event"
    for name, rule in rules.items():
        if name in hit:
            continue
        m = rule.get("match") if isinstance(rule.get("match"), dict) else DEFAULT_MATCH.get(name, {})
        word = next((w for w in m.get("words", []) if kw_hit(str(w).lower(), text)), None)
        if word:
            hit[name] = f"word '{word}'"
            continue
        p = next((p for p in paths for g in m.get("paths", []) if glob_hit(p, g)), None)
        if p:
            hit[name] = f"path {p}"
    risk = impact.get("risk") if isinstance(impact.get("risk"), dict) else DEFAULT_RISK
    risky = [w for w in risk.get("words", []) if kw_hit(str(w).lower(), text)]
    risky += [p for p in paths if any(glob_hit(p, g) for g in risk.get("paths", []))]

    reuse, register = [], []
    caps = load_caps(root)
    for row in caps or []:
        by = next((f"word '{k}'" for k in keywords(row.get("triggers", "")) + name_variants(row["name"]) if kw_hit(k, text)), None)
        if not by:
            by = next((f"path {e}" for e in cell_paths(row["entry"]) if any(path_hit(p, e) for p in paths)), None)
        if by:
            state = clean(row.get("state", "")).lower() or "unknown"
            item = {"capability": clean(row["name"]), "state": state, "entry": clean(row["entry"]), "hit": by}
            if detail or state.startswith("retired"):
                item["call"] = _clip(row.get("call", ""), detail)
            if state.startswith("retired"):
                item["note"] = "retired: do not build on it; its row names the replacement"
            reuse.append(item)
    rank = {"active": 0, "incubating": 1}
    reuse.sort(key=lambda r: rank.get(r["state"].split()[0] if r["state"] else "", 2))
    if caps is not None:
        globs, exempt = _audit_config(impact)
        caps_text = read_text(root / CAPS_NAME)
        register = [p for p in paths if capability_like(p, globs, exempt) and not registered_in(p, caps_text)]

    components = []
    for row in load_map(root) or []:
        by = next((f"word '{k}'" for k in keywords(row.get("keywords", "")) + name_variants(row["component"]) if kw_hit(k, text)), None)
        if not by:
            targets = cell_paths(row["component"]) + cell_paths(row.get("details", ""))
            by = next((f"path {t}" for t in targets if any(path_hit(p, t) for p in paths)), None)
        if by:
            components.append({"component": clean(row["component"]), "area": row["area"],
                               "details": clean(row.get("details", "")), "hit": by})

    names = list(hit)
    premise_review = any(rules[n].get("premise_review") for n in names)
    contradiction_review = any(rules[n].get("contradiction_review") for n in names)
    premises = []
    if config_path(root, "premises.json").exists():
        for premise, state, _ in premise_rows(root):
            deps = premise.get("depends_on") if isinstance(premise.get("depends_on"), list) else []
            if not deps:
                scope = "unscoped"
            elif not paths:
                scope = "unfiltered"
            elif any(glob_hit(p, g) for p in paths for g in deps):
                scope = "matched"
            else:
                continue
            premises.append({"id": premise["id"], "level": premise["level"], "state": state, "scope": scope,
                             "assertion": _clip(premise.get("assertion", ""), detail)})
    if not (premise_review or any(p["scope"] == "matched" for p in premises)):
        premises_note = f"{len(premises)} premise(s) apply, review not required for these events"
        shown_premises = []
    else:
        premises_note = "review required" if premise_review else "a premise depends on a changed path"
        shown_premises = premises

    reasons = []
    always = [n for n in names if rules[n].get("always_heavy", n in DEFAULT_ALWAYS_HEAVY)]
    light_events = all(rules[n].get("light", n in DEFAULT_LIGHT) for n in names) if names else False
    areas = sorted({c["area"] for c in components})
    if not names:
        reasons.append("no event type matched; name one with --event")
    if risky:
        reasons.append("risk: " + ", ".join(risky[:5]))
    if always:
        reasons.append("always heavy: " + ", ".join(always))
    if len(areas) > 1:
        reasons.append(f"components in {len(areas)} map areas: " + ", ".join(areas))
    if names and not light_events and not (reversible and single_area):
        reasons.append("an event is not marked light; pass --reversible --single-area only when both hold")
    tier = "heavy" if reasons else "light"
    if tier == "light":
        reasons.append("every event is light" if light_events else "declared reversible and single-area")

    surfaces = []
    for n in names:
        for s in rules[n]["surfaces"]:
            if s not in surfaces:
                surfaces.append(s)
    nxt = []
    if register:
        nxt.append("register in CAPABILITIES.md before building on it: " + ", ".join(register))
    active = [r["capability"] for r in reuse if r["state"].startswith("active")]
    if active:
        nxt.append("reuse before building: " + ", ".join(active))
    if tier == "heavy" and names:
        nxt.append(f"python3 scripts/memory_governance.py impact --event {names[0]} --terms \"<old name or path>\" --record, "
                   "then verify --receipt <id>")
    elif names:
        nxt.append("update the surfaces above; no receipt needed")
    if premise_review:
        nxt.append("python3 scripts/memory_governance.py premise check")
    if contradiction_review:
        nxt.append("record a reversed rule with: contradict add --old … --new … --evidence …")

    card = OrderedDict(
        intent=" ".join((intent or "").split()), paths=paths, config=config, tier=tier, tier_reasons=reasons,
        events=[{"event": n, "by": hit[n]} for n in names], surfaces=surfaces,
        premise_review=premise_review, contradiction_review=contradiction_review,
        reuse=reuse, register=register, components=components,
        premises=shown_premises, premises_note=premises_note, next=nxt,
    )
    if not detail:
        more = {}
        for key in ("reuse", "components", "premises", "register"):
            if len(card[key]) > LIST_CAP:
                more[key] = len(card[key]) - LIST_CAP
                card[key] = card[key][:LIST_CAP]
        if more:
            card["more"] = more
    return card


def render_route(card):
    out = [f"ROUTE tier={card['tier']} ({'; '.join(card['tier_reasons'])})"]
    out.append("EVENTS " + (", ".join(f"{e['event']} ({e['by']})" for e in card["events"]) or "none"))
    out.append("SURFACES " + (", ".join(card["surfaces"]) or "none"))
    if card["reuse"]:
        out.append("REUSE")
        for r in card["reuse"]:
            tail = f" — {r['note']}: {r.get('call', '')}" if r.get("note") else ""
            out.append(f"  {r['capability']} [{r['state']}] {r['entry']}{tail}")
    if card["register"]:
        out.append("REGISTER " + ", ".join(card["register"]))
    if card["components"]:
        out.append("COMPONENTS")
        for c in card["components"]:
            out.append(f"  {c['component']} ({c['area'] or 'map'}) -> {c['details'] or '-'}")
    out.append(f"PREMISES {card['premises_note']}")
    for p in card["premises"]:
        out.append(f"  {p['id']} {p['level']} {p['state'].upper()} {p['scope']}: {p['assertion']}")
    for step in card["next"]:
        out.append(f"NEXT {step}")
    if card.get("more"):
        out.append("MORE " + ", ".join(f"{k}+{v}" for k, v in card["more"].items()) + " (use --detail)")
    text = "\n".join(out)
    if len(text.encode("utf-8")) > OUTPUT_BUDGET and not card.get("_detail"):
        cut = text.encode("utf-8")[:OUTPUT_BUDGET - 40].decode("utf-8", "ignore").rsplit("\n", 1)[0]
        text = cut + "\nMORE card cut at 2 KB (use --detail)"
    return text


def cmd_route(args):
    root = Path(args.target).resolve()
    card = route_card(root, args.intent, args.paths, args.event, args.reversible, args.single_area, args.detail)
    if args.json:
        print(json.dumps(card, ensure_ascii=False))
    else:
        card["_detail"] = args.detail
        print(render_route(card))
    return 0


# ---------------------------------------------------------------------------
# 1.4.3 · lookup: read-only rows (the MCP server's memory_lookup calls this)
# ---------------------------------------------------------------------------

def lookup(root: Path, registry: str, query="", status=None, limit=10, detail=False):
    rows = load_caps(root) if registry == "capability" else load_map(root)
    source = CAPS_NAME if registry == "capability" else MAP_NAME
    result = OrderedDict(registry=registry, source=source, query=query, status=status, total=0, rows=[])
    if rows is None:
        result["note"] = f"no {source} in this project"
        return result
    terms = [t for t in (query or "").lower().split() if t]
    found = []
    for r in rows:
        hay = " ".join(clean(v) for k, v in r.items() if not k.startswith("_") and k != "line").lower()
        if terms and not all(t in hay for t in terms):
            continue
        if status and registry == "capability" and status.lower() not in clean(r.get("state", "")).lower():
            continue
        found.append(r)
    result["total"] = len(found)
    for r in found[:max(1, limit)]:
        if registry == "capability":
            item = OrderedDict(capability=clean(r["name"]), state=clean(r.get("state", "")), entry=clean(r["entry"]),
                               triggers=_clip(r.get("triggers", ""), detail))
            if detail:
                item.update(form=clean(r.get("form", "")), call=clean(r.get("call", "")))
        else:
            item = OrderedDict(component=clean(r["component"]), area=r["area"], keywords=_clip(r.get("keywords", ""), detail),
                               details=clean(r.get("details", "")))
            if detail:
                item["job"] = clean(r.get("job", ""))
        item["line"] = r["line"]
        result["rows"].append(item)
    return result


def cmd_lookup(args):
    root = Path(args.target).resolve()
    result = lookup(root, args.registry, args.query, args.status, args.limit, args.detail)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if result.get("note"):
        print(result["note"])
        return 0
    print(f"{result['source']}: {result['total']} row(s)" + (f", showing {len(result['rows'])}" if result["total"] > len(result["rows"]) else ""))
    for r in result["rows"]:
        print("  " + " | ".join(str(v) for k, v in r.items() if k != "line") + f"  (line {r['line']})")
    return 0


# ---------------------------------------------------------------------------
# 1.4.3 · audit: missing, ghost, orphan, stub, volume
# ---------------------------------------------------------------------------

AUDIT_KINDS = ("missing", "ghost", "orphan", "stub", "volume")
STUB_MARK = "<!-- pointer-stub -->"
STUB_LINE_RE = re.compile(r"^> Moved to `([^`]+)` on (\d{4}-\d{2}-\d{2})\. This is a pointer only; do not write here\.$")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")


def stub_problems(root: Path):
    """A pointer stub is a heading (or the top of a file), the marker, and one pointer line. Nothing else."""
    stubs, ghosts = [], []
    for rel in walk_files(root):
        if not rel.endswith(".md"):
            continue
        try:
            if (root / rel).stat().st_size > MAX_FILE_BYTES:
                continue
            text = read_text(root / rel)
        except (OSError, UnicodeDecodeError):
            continue
        if STUB_MARK not in text:
            continue
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if ln.strip() != STUB_MARK:
                continue
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            m = _HEADING.match(lines[j]) if j >= 0 else None
            if m:
                level = len(m.group(1))
                end = next((k for k in range(i + 1, len(lines)) if (_HEADING.match(lines[k]) and
                            len(_HEADING.match(lines[k]).group(1)) <= level)), len(lines))
                body = [x.strip() for x in lines[i:end] if x.strip()]
                where = f"{rel}:{j + 1} \"{m.group(2)}\""
            elif j < 0:
                body = [x.strip() for x in lines[i:] if x.strip()]
                where = f"{rel} (whole-file stub)"
            else:
                stubs.append({"item": f"{rel}:{i + 1}", "detail": "pointer-stub marker is neither under a heading nor at the top of the file"})
                continue
            pm = STUB_LINE_RE.match(body[1]) if len(body) == 2 else None
            if not pm:
                stubs.append({"item": where, "detail": f"stub carries text besides its pointer ({len(body) - 1} line(s)); the old place must not grow a second copy"})
                continue
            if not (root / pm.group(1)).exists():
                ghosts.append({"item": where, "detail": f"stub points at missing `{pm.group(1)}`"})
    return stubs, ghosts


def audit_report(root: Path):
    impact, _ = load_impact_or_default(root)
    globs, exempt = _audit_config(impact)
    report = OrderedDict((k, []) for k in AUDIT_KINDS)
    report["skipped"] = []
    caps = load_caps(root)
    rows_map = load_map(root)
    if caps is None:
        report["skipped"].append("no CAPABILITIES.md: missing and orphan checks off")
    else:
        caps_text = read_text(root / CAPS_NAME)
        for rel in walk_files(root):
            if capability_like(rel, globs, exempt) and not registered_in(rel, caps_text):
                report["missing"].append({"item": rel, "detail": "capability-like file not in CAPABILITIES.md"})
        for row in caps:
            state = clean(row.get("state", "")).lower()
            if state.startswith("retired"):
                continue
            for p in cell_paths(row["entry"]):
                if not (root / p).exists():
                    report["ghost"].append({"item": f"{CAPS_NAME}:{row['line']} {clean(row['name'])}",
                                            "detail": f"entry point `{p}` does not exist"})
        try:
            report["orphan"] = orphans(root, caps)
        except GovernanceError as e:
            report["skipped"].append(f"orphan check off: {e}")
    if rows_map is None:
        report["skipped"].append("no MAP.md: map path checks off")
    else:
        for row in rows_map:
            for p in OrderedDict.fromkeys(cell_paths(row["component"]) + cell_paths(row.get("details", ""))):
                if not (root / p).exists():
                    report["ghost"].append({"item": f"{MAP_NAME}:{row['line']} {clean(row['component'])}",
                                            "detail": f"path `{p}` does not exist"})
    stubs, ghosts = stub_problems(root)
    report["stub"] += stubs
    report["ghost"] += ghosts
    report["volume"] = [{"item": p.split(":", 1)[0], "detail": p} for p in volume_verify(root)]
    return report


def orphans(root: Path, caps):
    """Active capabilities that nothing outside the registries mentions."""
    registries = {CAPS_NAME, MAP_NAME} | {rel for rel, _ in index_texts(root)}
    todo = []
    for row in caps:
        if not clean(row.get("state", "")).lower().startswith("active"):
            continue
        entries = cell_paths(row["entry"])
        needles = set()
        own = set(entries)
        for e in entries:
            parent, _, base = e.rstrip("/").rpartition("/")
            if base == "SKILL.md":
                needles.add(parent.rsplit("/", 1)[-1])
                own.add(parent + "/")
            else:
                needles.add(base)
        name = clean(row["name"])
        if len(name) >= 3:
            needles.add(name)
        needles = {n for n in needles if len(n) >= 3}
        if needles:
            todo.append((row, needles, own))
    if not todo:
        return []
    seen = set()
    for path, skip in iter_text_files(root):
        if skip:
            continue
        rel = path.relative_to(root).as_posix()
        if rel in registries:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, (row, needles, own) in enumerate(todo):
            if n in seen or any(rel == o or (o.endswith("/") and rel.startswith(o)) for o in own):
                continue
            if any(x in text for x in needles):
                seen.add(n)
        if len(seen) == len(todo):
            break
    return [{"item": f"{CAPS_NAME}:{row['line']} {clean(row['name'])}",
             "detail": "active, but nothing outside CAPABILITIES.md, MAP.md and INDEX.md mentions it"}
            for n, (row, _, _) in enumerate(todo) if n not in seen]


def cmd_audit(args):
    root = Path(args.target).resolve()
    report = audit_report(root)
    total = sum(len(report[k]) for k in AUDIT_KINDS)
    if args.json:
        print(json.dumps(OrderedDict(report, total=total), ensure_ascii=False))
        return 1 if total else 0
    for k in AUDIT_KINDS:
        print(f"{k.upper()} {len(report[k])}")
        for f in report[k][:50]:
            print(f"  {f['item']}: {f['detail']}")
    for s in report["skipped"]:
        print(f"SKIPPED {s}")
    print("AUDIT OK" if not total else f"AUDIT FINDINGS {total}; run map sync for paste-ready rows")
    return 1 if total else 0


# ---------------------------------------------------------------------------
# 1.4.3 · map sync: a generated block inside MAP.md
# ---------------------------------------------------------------------------

MAP_BEGIN = "<!-- map:auto:begin"
MAP_END = "<!-- map:auto:end -->"


def split_note(root: Path, d: str):
    main = root / f"{d}.md"
    if not main.is_file() or not (root / d).is_dir():
        return ""
    names = [p.name for p in (root / d).iterdir() if p.is_file() and p.suffix == ".md"]
    vols = sum(1 for n in names if VOLUME_NAME_RE.match(n))
    parts = len(names) - vols
    bits = ([f"{vols} volume{'s' if vols != 1 else ''}"] if vols else []) + ([f"{parts} part{'s' if parts != 1 else ''}"] if parts else [])
    return f"`{d}.md` · " + ", ".join(bits) if bits else ""


def render_map_region(root: Path):
    impact, _ = load_impact_or_default(root)
    globs, exempt = _audit_config(impact)
    caps = load_caps(root) or []
    caps_text = read_text(root / CAPS_NAME) if (root / CAPS_NAME).is_file() else None
    entries = [p for r in caps for p in cell_paths(r["entry"])]
    idx = index_row_paths(root)
    files = list(walk_files(root))
    missing = [f for f in files if caps_text is not None and capability_like(f, globs, exempt) and not registered_in(f, caps_text)]

    def top(p):
        p = norm_path(p)
        return p.split("/", 1)[0] + "/" if "/" in p.rstrip("/") else "(root)"

    tops = ["(root)"] + sorted({top(f) for f in files} - {"(root)"}, key=str.lower)
    rows = []
    for t in tops:
        hidden = t.startswith(".")
        if hidden:
            continue
        note = split_note(root, t.rstrip("/")) if t != "(root)" else ""
        rows.append(f"| `{t}` | {sum(1 for f in files if top(f) == t and not f.rsplit('/', 1)[-1].startswith('.'))} "
                    f"| {sum(1 for p in idx if top(p) == t)} | {sum(1 for e in entries if top(e) == t)} "
                    f"| {sum(1 for m in missing if top(m) == t)} | {note} |")
    lines = [f"{MAP_BEGIN} (generated by memory_governance.py map sync; edit outside this block) -->",
             "| Directory | Files | INDEX rows | Capabilities | Not registered | Split files |",
             "|---|---|---|---|---|---|"] + rows + [MAP_END]
    return "\n".join(lines) + "\n", missing


def map_suggestions(root: Path, missing):
    out = {"capabilities_add": [], "capabilities_retire": [], "map_add": []}
    for m in missing:
        parent, _, base = m.rpartition("/")
        if base == "SKILL.md":
            name, form, call = parent.rsplit("/", 1)[-1], "Skill", f"`{m}`"
        elif m.startswith(".github/workflows/"):
            name, form, call = base, "CI workflow", "runs on its trigger"
        else:
            name, form = base, "Script"
            call = f"`python3 {m}`" if m.endswith(".py") else f"`bash {m}`" if m.endswith(".sh") else f"`{m}`"
        out["capabilities_add"].append(f"| `{name}` | {form} | `{m}` | <trigger words> | incubating | {call} |")
    report_caps = load_caps(root)
    if report_caps is not None:
        try:
            retire = {f["item"].split(" ", 1)[0] for f in orphans(root, report_caps)}
        except GovernanceError:
            retire = set()
        for row in report_caps:
            gone = [p for p in cell_paths(row["entry"]) if not (root / p).exists()]
            if (f"{CAPS_NAME}:{row['line']}" in retire or gone) and not clean(row.get("state", "")).lower().startswith("retired"):
                cells = list(row["_cells"])
                if "state" in row["_keys"]:
                    cells[row["_keys"]["state"]] = "retired"
                out["capabilities_retire"].append("| " + " | ".join(cells) + " |")
    rows_map = load_map(root)
    if rows_map is not None:
        covered = {p.split("/", 1)[0] for r in rows_map for p in cell_paths(r["component"]) + cell_paths(r.get("details", "")) if "/" in p}
        memory_dirs = {n for n in ("LOG", "MEMORY", "INDEX") if (root / f"{n}.md").is_file()}
        for d in sorted({f.split("/", 1)[0] for f in walk_files(root) if "/" in f}):
            if d.startswith(".") or d in covered or d in memory_dirs:
                continue
            out["map_add"].append(f"| `{d}/` | <one sentence> | <change keywords> | `{d}/` |")
    return out


def map_sync(root: Path, check=False):
    p = root / MAP_NAME
    if not p.is_file():
        return {"status": "skipped", "reason": "no MAP.md"}
    text = read_text(p)
    region, missing = render_map_region(root)
    b = text.find(MAP_BEGIN)
    if b >= 0:
        e = text.find(MAP_END, b)
        if e < 0:
            raise GovernanceError("MAP.md has a map:auto:begin marker without map:auto:end")
        e += len(MAP_END)
        if text[e:e + 1] == "\n":
            e += 1
        current, new_text = text[b:e], text[:b] + region + text[e:]
    else:
        current, new_text = None, text.rstrip("\n") + "\n\n## Generated overview\n\n" + region
    if check:
        status = "no_region" if current is None else "ok" if current == region else "drift"
        return {"status": status, "missing": missing}
    if new_text == text:
        return {"status": "unchanged", "missing": missing}
    write_text_atomic(p, new_text)
    return {"status": "updated", "missing": missing}


def refresh_map(root: Path):
    """After a split: rewrite the generated block only when MAP.md already has one."""
    try:
        p = root / MAP_NAME
        if not p.is_file() or MAP_BEGIN not in read_text(p):
            return {"status": "no_region"}
        return {"status": map_sync(root)["status"]}
    except Exception as e:  # noqa: BLE001 — the split is done; doctor reports any drift
        return {"status": "error", "reason": f"{type(e).__name__}: {e}"}


def cmd_map(args):
    root = Path(args.target).resolve()
    result = map_sync(root, check=args.check)
    sugg = map_suggestions(root, result.get("missing", [])) if result["status"] != "skipped" else {}
    if args.json:
        print(json.dumps(OrderedDict(status=result["status"], reason=result.get("reason"), suggestions=sugg), ensure_ascii=False))
    else:
        print(f"MAP {result['status']}" + (f" ({result['reason']})" if result.get("reason") else ""))
        if result["status"] == "drift":
            print("The generated block in MAP.md is out of date; run: python3 scripts/memory_governance.py map sync")
        if result["status"] == "no_region":
            print("MAP.md has no generated block yet; map sync adds one at the end.")
        labels = (("capabilities_add", "SUGGEST ADD to CAPABILITIES.md (state stays incubating until reused):"),
                  ("capabilities_retire", "SUGGEST RETIRE in CAPABILITIES.md (or point Entry at the replacement):"),
                  ("map_add", "SUGGEST ADD to MAP.md (only if a change there makes you ask what else to update):"))
        for key, label in labels:
            if sugg.get(key):
                print(label)
                for line in sugg[key]:
                    print("  " + line)
    return 1 if result["status"] == "drift" else 0


# ---------------------------------------------------------------------------
# 1.4.3 · split: month volumes (automatic) and topic splits (with --confirm)
# ---------------------------------------------------------------------------

VOLUME_NAME_RE = re.compile(r"^(\d{4})-(\d{2})\.md$")
TOC_BEGIN = "<!-- volumes:begin"
TOC_END = "<!-- volumes:end -->"
TOC_ROW_RE = re.compile(r"^> - `([^`]+)` · ([\d,]+) sections? · sha256 ([0-9a-f]{12})$")
ORDER_WORDS = {"desc": "newest-first", "asc": "oldest-first"}
VOLUME_THRESHOLD = 128 * 1024
TOPIC_MARK = "<!-- split:body -->"
MEMORY_SOFT_LINES = 150
MEMORY_MAX_TOKENS = 8192
INDEX_SOFT_ROWS = 300
INDEX_SOFT_BYTES = 32 * 1024
TOPIC_MIN_LINES = 3
INDEX_RUN_MIN = 20
_HEAD_AT = re.compile(r"(?m)^## ")
_MONTH = re.compile(r"^## +(\d{4})-(\d{2})(?![0-9])")


def splits_dir(root: Path):
    return memory_dir(root) / "splits"


def stamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def new_tx(root: Path, prefix: str, plan_sha: str):
    base = f"{prefix}-{stamp()}-{plan_sha[:8]}"
    tx, n = base, 2
    while (splits_dir(root) / f"{tx}.json").exists():
        tx, n = f"{base}-{n}", n + 1
    return tx


def parse_today(value):
    if not value:
        return datetime.now()
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise GovernanceError(f"--today needs YYYY-MM-DD, got {value!r}")


def volume_dir(path: Path):
    return path.with_name(path.stem)


def volume_rel(rel: str, month: str):
    """`LOG.md` -> `LOG/2026-09.md`; `docs/notes.md` -> `docs/notes/2026-09.md` (beside the main file)."""
    return f"{Path(rel).with_suffix('').as_posix()}/{month}.md"


def volume_files(path: Path):
    d = volume_dir(path)
    if not d.is_dir():
        return []
    return sorted((p for p in d.iterdir() if p.is_file() and VOLUME_NAME_RE.match(p.name)), key=lambda p: p.name)


def toc_span(text: str):
    b = text.find(TOC_BEGIN)
    if b < 0 or (b and text[b - 1] != "\n"):
        return None
    first = _HEAD_AT.search(text)
    if first and first.start() < b:
        return None
    e = text.find(TOC_END, b)
    if e < 0:
        return None
    e += len(TOC_END)
    if text[e:e + 1] == "\n":
        e += 1
    return b, e


def strip_toc(text: str):
    span = toc_span(text)
    return text if not span else text[:span[0]] + text[span[1]:]


def toc_order(text: str):
    span = toc_span(text)
    if not span:
        return None
    line = text[span[0]:text.find("\n", span[0])]
    return "asc" if "order=oldest-first" in line else "desc" if "order=newest-first" in line else None


def raw_split(text: str):
    """Text -> (head, [sections]); a section starts at a line beginning with `## `. Lossless."""
    starts = [m.start() for m in _HEAD_AT.finditer(text)]
    if not starts:
        return text, []
    return text[:starts[0]], [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]


def month_keys(sections):
    """Month of each section; a section whose heading has no month follows its neighbour above (or below)."""
    raw = []
    for s in sections:
        m = _MONTH.match(s)
        raw.append(f"{m.group(1)}-{m.group(2)}" if m else None)
    out, last = [], None
    for k in raw:
        last = k or last
        out.append(last)
    nxt = None
    for i in range(len(out) - 1, -1, -1):
        nxt = raw[i] or nxt
        if out[i] is None:
            out[i] = nxt
    return out, raw


def compose(main_text: str, vols, order: str):
    """Full view = the main file without its volume list, with every volume's sections joined back in place."""
    head, secs = raw_split(strip_toc(main_text))
    if not vols:
        return head + "".join(secs)
    months = sorted(vols, reverse=(order == "desc"))
    body = "".join("".join(raw_split(vols[m])[1]) for m in months)
    return head + (body + "".join(secs) if order == "asc" else "".join(secs) + body)


def by_month(vols):
    return {Path(v).stem: t for v, t in vols.items()}


def full_view(path: Path):
    text = read_text(path)
    vols = {p.stem: read_text(p) for p in volume_files(path)}
    return compose(text, vols, toc_order(text) or "desc") if vols else text


def volume_head(rel: str, month: str):
    name = Path(rel).name
    return (f"# {name} · {month} (read-only volume)\n\n"
            f"> Generated by memory_governance.py split. Do not edit or append here: new entries go to `{name}`, "
            "which lists every volume at its top. This header is not part of the full view.\n\n")


def render_toc(rel: str, vols, order: str):
    base = Path(rel).parent.as_posix()
    lines = [f"{TOC_BEGIN} order={ORDER_WORDS[order]} (generated by memory_governance.py split; do not edit) -->",
             "> Past months live in read-only volumes:"]
    for vrel in sorted(vols, reverse=True):
        n = len(raw_split(vols[vrel])[1])
        short = vrel[len(base) + 1:] if base not in ("", ".") else vrel
        lines.append(f"> - `{short}` · {n:,} section{'s' if n != 1 else ''} · sha256 {sha256_text(vols[vrel])[:12]}")
    lines.append(TOC_END)
    return "\n".join(lines) + "\n"


def insert_toc(text: str, toc: str):
    """The volume list goes right after the first line of the file head (the version marker stays first)."""
    first = _HEAD_AT.search(text)
    head_end = first.start() if first else len(text)
    nl = text.find("\n")
    if nl < 0 or nl >= head_end:
        return toc + text
    return text[:nl + 1] + toc + text[nl + 1:]


def volume_layout(root: Path, rel: str, raw: str, cur: str, order: str):
    path = root / rel
    head, secs = raw_split(strip_toc(raw))
    keys, _ = month_keys(secs)
    keep = [s for s, k in zip(secs, keys) if not k or k >= cur]
    moved = OrderedDict()
    for s, k in zip(secs, keys):
        if k and k < cur:
            moved.setdefault(k, []).append(s)
    vols = {relp(root, p): read_text(p) for p in volume_files(path)}
    for m, ss in moved.items():
        vrel = volume_rel(rel, m)
        body = "".join(ss)
        if vrel in vols:
            vh, vs = raw_split(vols[vrel])
            vols[vrel] = vh + (body + "".join(vs) if order == "desc" else "".join(vs) + body)
        else:
            vols[vrel] = volume_head(rel, m) + body
    return insert_toc(head + "".join(keep), render_toc(rel, vols, order)), vols, moved


def volume_plan(root: Path, rel: str, today=None, threshold=None):
    threshold = VOLUME_THRESHOLD if threshold is None else threshold
    rel = norm_path(rel)
    path = root / rel
    if not path.is_file():
        raise GovernanceError(f"{rel} not found")
    raw = read_text(path)
    head, secs = raw_split(strip_toc(raw))
    keys, rawkeys = month_keys(secs)
    existing = volume_files(path)
    declared = toc_order(raw)
    cur = (today or datetime.now()).strftime("%Y-%m")
    size = len(raw.encode("utf-8"))
    reasons = []
    if "\r" in raw:
        reasons.append("the file has CR line endings; cutting would change how readers decode it")
    if not any(rawkeys):
        reasons.append("no `## YYYY-MM` month sections to cut at")
    if size <= threshold and not existing:
        reasons.append(f"size {size:,} B is under the {threshold:,} B threshold")
    pairs = [(a, b) for a, b in zip(keys, keys[1:]) if a and b]
    asc, desc = all(a <= b for a, b in pairs), all(a >= b for a, b in pairs)
    order = declared or ("desc" if desc else "asc" if asc else "desc")
    if not (asc if order == "asc" else desc):
        reasons.append("month sections are out of order (newest-first or oldest-first both work; mixed does not)")
    past = sorted({k for k in keys if k and k < cur}, reverse=True)
    if not past:
        reasons.append("no finished month left in the main file")
    vdir = volume_dir(path)
    stats = OrderedDict()
    for s, k in zip(secs, keys):
        st = stats.setdefault(k or "?", {"sections": 0, "bytes": 0})
        st["sections"] += 1
        st["bytes"] += len(s.encode("utf-8"))
    view = full_view(path)
    if not reasons:
        new_main, vols, _ = volume_layout(root, rel, raw, cur, order)
        if compose(new_main, by_month(vols), order) != view:
            reasons.append("the cut would change the full view (an older month sits out of place); move it by hand first")
    plan = OrderedDict(
        file=rel, size=size, threshold=threshold, current_month=cur, order=ORDER_WORDS[order],
        eligible=not reasons, reasons=reasons,
        keep={"sections": sum(v["sections"] for m, v in stats.items() if m == "?" or m >= cur),
              "bytes": len(head.encode("utf-8")) + sum(v["bytes"] for m, v in stats.items() if m == "?" or m >= cur)},
        volumes=[{"month": m, "path": volume_rel(rel, m),
                  "sections": stats[m]["sections"], "bytes": stats[m]["bytes"],
                  "merge_into_existing": (vdir / f"{m}.md").exists()} for m in past],
        existing_volumes=[relp(root, p) for p in existing],
        source_sha256=sha256_text(raw), view_sha256=sha256_text(view),
    )
    plan["plan_sha"] = sha256_text(json.dumps(plan, ensure_ascii=False, sort_keys=True))[:16]
    return plan


def save_manifest(root: Path, manifest):
    atomic_json(splits_dir(root) / f"{manifest['tx']}.json", manifest)


def load_manifest(root: Path, tx: str):
    if not re.match(r"^[A-Za-z0-9_.-]+$", tx or ""):
        raise GovernanceError(f"bad transaction id {tx!r}")
    return load_json(splits_dir(root) / f"{tx}.json")


def manifests(root: Path):
    d = splits_dir(root)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def backup_files(root: Path, tx: str, rels):
    backups = {}
    for rel in rels:
        b = splits_dir(root) / "backup" / tx / rel
        write_text_atomic(b, read_text(root / rel))
        backups[rel] = relp(root, b)
    return backups


def restore(root: Path, manifest):
    for rel, b in manifest.get("backups", {}).items():
        write_text_atomic(root / rel, read_text(root / b))
    for rel in manifest.get("created", []):
        p = root / rel
        if p.exists():
            p.unlink()
        if p.parent != root and p.parent.is_dir() and not any(p.parent.iterdir()):
            p.parent.rmdir()


def volume_apply(root: Path, rel: str, plan_sha=None, auto=False, today=None, threshold=None):
    rel = norm_path(rel)
    path = root / rel
    with FileLock(memory_dir(root) / "split.lock"):
        plan = volume_plan(root, rel, today, threshold)
        if not auto and plan_sha != plan["plan_sha"]:
            raise GovernanceError(f"plan changed (now {plan['plan_sha']}, given {plan_sha}); run split volume plan again")
        if not plan["eligible"]:
            raise GovernanceError("not eligible: " + "; ".join(plan["reasons"]))
        order = "asc" if plan["order"] == "oldest-first" else "desc"
        raw = read_text(path)
        before = full_view(path)
        new_main, vols, moved = volume_layout(root, rel, raw, plan["current_month"], order)
        if compose(new_main, by_month(vols), order) != before:
            raise GovernanceError("self-check failed in memory: the full view would change; nothing was written")
        existing = {relp(root, p): read_text(p) for p in volume_files(path)}
        tx = new_tx(root, "vol", plan["plan_sha"])
        created = sorted(v for v in vols if v not in existing)
        modified = sorted([rel] + [v for v in vols if v in existing and vols[v] != existing[v]])
        manifest = OrderedDict(
            tx=tx, kind="volume", file=rel, status="applying", ts=now_iso(), plan_sha=plan["plan_sha"], order=order,
            created=created, modified=modified, backups=backup_files(root, tx, modified),
            moved={m: [sha256_text(s) for s in ss] for m, ss in moved.items()},
            before={"view_sha256": sha256_text(before), "source_sha256": sha256_text(raw)},
        )
        save_manifest(root, manifest)
        try:
            mode = path.stat().st_mode & 0o777
            for v in sorted(vols):
                if vols[v] != existing.get(v):
                    write_text_atomic(root / v, vols[v], mode)
            write_text_atomic(path, new_main, mode)
            if full_view(path) != before:
                raise GovernanceError("self-check failed on disk: the full view changed")
            problems = volume_verify(root, [rel])
            if problems:
                raise GovernanceError("volume list does not match the volumes: " + "; ".join(problems))
        except Exception:
            restore(root, manifest)
            manifest["status"] = "failed_rolled_back"
            save_manifest(root, manifest)
            raise
        rid = next_receipt_id(root)
        append_receipt(root, {"type": "split", "receipt": rid, "kind": "volume", "tx": tx, "file": rel,
                              "status": "applied", "months": sorted(moved), "ts": now_iso()})
        manifest.update(status="applied", receipt=rid,
                        after={r: sha256_text(read_text(root / r)) for r in sorted(set(created) | set(modified))})
        manifest["map"] = refresh_map(root)
        save_manifest(root, manifest)
        return manifest


def volume_rollback(root: Path, tx: str):
    manifest = load_manifest(root, tx)
    if manifest.get("kind") != "volume" or manifest.get("status") != "applied":
        raise GovernanceError(f"{tx} is not an applied volume split (status={manifest.get('status')})")
    rel, order = manifest["file"], manifest["order"]
    path = root / rel
    with FileLock(memory_dir(root) / "split.lock"):
        before = full_view(path)
        vols = {relp(root, p): read_text(p) for p in volume_files(path)}
        back = OrderedDict()
        new_vols = OrderedDict()
        for m, shas in manifest["moved"].items():
            vrel = volume_rel(rel, m)
            if vrel not in vols:
                raise GovernanceError(f"volume {vrel} is missing; cannot roll back")
            vh, vs = raw_split(vols[vrel])
            want, keep, got = Counter(shas), [], []
            for s in vs:
                h = sha256_text(s)
                if want[h] > 0:
                    want[h] -= 1
                    got.append(s)
                else:
                    keep.append(s)
            if sum(want.values()):
                raise GovernanceError(f"volume {vrel} lost {sum(want.values())} section(s) this split moved; rollback refused")
            back[m] = got
            new_vols[vrel] = vh + "".join(keep) if keep else None
        head, secs = raw_split(strip_toc(read_text(path)))
        back_text = "".join("".join(back[m]) for m in sorted(back, reverse=(order == "desc")))
        restored = head + ("".join(secs) + back_text if order == "desc" else back_text + "".join(secs))
        remaining = {v: t for v, t in vols.items() if new_vols.get(v, t) is not None}
        remaining.update({v: t for v, t in new_vols.items() if t is not None})
        new_main = insert_toc(restored, render_toc(rel, remaining, order)) if remaining else restored
        if compose(new_main, by_month(remaining), order) != before:
            raise GovernanceError("rollback self-check failed in memory; nothing was written")
        for vrel, t in new_vols.items():
            if t is None:
                (root / vrel).unlink()
            elif t != vols[vrel]:
                write_text_atomic(root / vrel, t)
        write_text_atomic(path, new_main)
        d = volume_dir(path)
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
        if full_view(path) != before:
            raise GovernanceError(f"rollback self-check failed on disk; backups are in .memory/splits/backup/{tx}/")
        rid = next_receipt_id(root)
        append_receipt(root, {"type": "split", "receipt": rid, "kind": "volume", "tx": tx, "file": rel,
                              "status": "rolled_back", "ts": now_iso()})
        manifest.update(status="rolled_back", rollback_receipt=rid, rolled_back_at=now_iso())
        manifest["map"] = refresh_map(root)
        save_manifest(root, manifest)
        return manifest


def volume_candidates(root: Path):
    rels = [LOG_NAME] + [m["file"] for m in manifests(root) if m.get("kind") == "volume" and m.get("status") == "applied"]
    out = []
    for r in rels:
        if r not in out and (root / r).is_file():
            out.append(r)
    return out


def volume_verify(root: Path, rels=None):
    problems = []
    for rel in rels or volume_candidates(root):
        path = root / rel
        if not path.is_file():
            continue
        raw = read_text(path)
        span = toc_span(raw)
        toc = {}
        base = Path(rel).parent.as_posix()
        if span:
            for line in raw[span[0]:span[1]].splitlines():
                m = TOC_ROW_RE.match(line)
                if m:
                    toc[m.group(1) if base in ("", ".") else f"{base}/{m.group(1)}"] = m.group(3)
        actual = {relp(root, p): sha256_text(read_text(p))[:12] for p in volume_files(path)}
        if not actual and not toc:
            continue
        for v in sorted(set(actual) - set(toc)):
            problems.append(f"{rel}: volume {v} is not in the volume list")
        for v in sorted(set(toc) - set(actual)):
            problems.append(f"{rel}: listed volume {v} does not exist")
        for v in sorted(set(toc) & set(actual)):
            if toc[v] != actual[v]:
                problems.append(f"{rel}: volume {v} sha256 {actual[v]} differs from the list ({toc[v]}); a volume was edited")
    return problems


def volume_auto(root: Path, today=None, threshold=None, dry_run=False):
    """LOG.md is cut automatically; any other file joins once it has been cut by hand with a reviewed plan."""
    out = []
    for rel in volume_candidates(root):
        plan = volume_plan(root, rel, today, threshold)
        if dry_run or not plan["eligible"]:
            out.append(OrderedDict(file=rel, result="plan" if dry_run else "skip", eligible=plan["eligible"],
                                   reasons=plan["reasons"], plan_sha=plan["plan_sha"],
                                   months=[v["month"] for v in plan["volumes"]]))
            continue
        m = volume_apply(root, rel, auto=True, today=today, threshold=threshold)
        out.append(OrderedDict(file=rel, result="cut", tx=m["tx"], receipt=m["receipt"], months=sorted(m["moved"])))
    return out


def est_tokens(text: str):
    cjk = len(re.findall("[　-鿿가-힯]", text))
    return cjk + (len(text) - cjk) // 4


def heading_spans(text: str):
    """Each ATX heading outside code fences, with its span up to the next heading of the same or higher level."""
    heads, pos, fence = [], 0, False
    for ln in text.splitlines(keepends=True):
        s = ln.rstrip("\r\n")
        if s.lstrip().startswith("```"):
            fence = not fence
        elif not fence:
            m = _HEADING.match(s)
            if m:
                heads.append((pos, len(m.group(1)), m.group(2).strip().rstrip("#").strip(), s))
        pos += len(ln)
    spans = []
    for i, (start, level, title, line) in enumerate(heads):
        end = next((h[0] for h in heads[i + 1:] if h[1] <= level), len(text))
        spans.append({"start": start, "end": end, "level": level, "title": title, "line": line})
    return spans


def slugify(title: str):
    s = re.sub(r"[^\w-]+", "-", title.strip().lower()).strip("-_")
    return (s or "topic")[:60]


def _dated(text: str):
    return sum(1 for ln in text.splitlines() if re.match(r"^\s*[-*]\s*\[\d{4}-\d{2}-\d{2}\]", ln) or
               (ln.strip().startswith("|") and not _is_sep(_cells(ln) or [])))


def _target_for(root: Path, rel: str, title: str, taken):
    stem = Path(rel).with_suffix("").as_posix()
    base = slugify(title)
    target, n = f"{stem}/{base}.md", 2
    while (root / target).exists() or target in taken:
        target, n = f"{stem}/{base}-{n}.md", n + 1
    taken.add(target)
    return target


def topic_nominations(root: Path, file=None, section=None, today=None):
    day = (today or datetime.now()).strftime("%Y-%m-%d")
    noms, taken = [], set()

    def add(rel, text, kind, span, title, reason, extra=None):
        nom = OrderedDict(file=rel, kind=kind, section=title, start=span[0], end=span[1],
                          target=_target_for(root, rel, title.rstrip("/"), taken),
                          lines=text[span[0]:span[1]].count("\n"), bytes=len(text[span[0]:span[1]].encode("utf-8")),
                          reason=reason, date=day)
        if extra:
            nom.update(extra)
        nom["plan_sha"] = sha256_text(json.dumps([nom, sha256_text(text)], ensure_ascii=False, sort_keys=True))[:16]
        noms.append(nom)

    def is_stub(text, sp):
        return STUB_MARK in text[sp["start"]:sp["end"]]

    if file:
        rel = norm_path(file)
        if not (root / rel).is_file():
            raise GovernanceError(f"{rel} not found")
        text = read_text(root / rel)
        spans = [sp for sp in heading_spans(text) if sp["title"] == (section or "") and sp["level"] >= 2]
        if not spans:
            raise GovernanceError(f"no `##`-level heading titled {section!r} in {rel}")
        if is_stub(text, spans[0]):
            raise GovernanceError(f"{section!r} in {rel} is already a pointer stub")
        sp = spans[0]
        add(rel, text, "section", (sp["start"], sp["end"]), sp["title"], "named with --file/--section",
            {"heading": sp["line"]})
        return noms

    mem = root / MEMORY_NAME
    if mem.is_file():
        text = read_text(mem)
        lines, tokens = text.count("\n"), est_tokens(text)
        if lines > MEMORY_SOFT_LINES or tokens > MEMORY_MAX_TOKENS:
            reason = f"MEMORY.md has {lines} lines / ~{tokens} tokens (soft wall {MEMORY_SOFT_LINES} lines / {MEMORY_MAX_TOKENS} tokens)"
            cands = [sp for sp in heading_spans(text) if sp["level"] in (2, 3) and sp["title"].lower() != "active"
                     and not is_stub(text, sp) and _dated(text[sp["start"]:sp["end"]]) >= TOPIC_MIN_LINES]
            cands.sort(key=lambda sp: (0 if sp["title"].lower() in ("dormant", "standby") else 1, sp["start"] - sp["end"]))
            chosen, left, left_tok = [], lines, tokens
            for sp in cands:
                if left <= MEMORY_SOFT_LINES and left_tok <= MEMORY_MAX_TOKENS:
                    break
                if any(not (sp["end"] <= c["start"] or sp["start"] >= c["end"]) for c in chosen):
                    continue
                chosen.append(sp)
                left -= text[sp["start"]:sp["end"]].count("\n") - 3
                left_tok -= est_tokens(text[sp["start"]:sp["end"]])
            for sp in sorted(chosen, key=lambda s: s["start"]):
                add(MEMORY_NAME, text, "section", (sp["start"], sp["end"]), sp["title"], reason, {"heading": sp["line"]})
    idx = root / INDEX_NAME
    if idx.is_file():
        text = read_text(idx)
        lines = text.splitlines(keepends=True)
        rows = [ln for ln in lines if ln.strip().startswith("|") and not _is_sep(_cells(ln) or [])]
        nbytes = len(text.encode("utf-8"))
        if len(rows) > INDEX_SOFT_ROWS or nbytes > INDEX_SOFT_BYTES:
            reason = f"INDEX.md has {len(rows)} rows / {nbytes:,} B (soft wall {INDEX_SOFT_ROWS} rows / {INDEX_SOFT_BYTES:,} B)"
            secs = [sp for sp in heading_spans(text) if sp["level"] == 2 and not is_stub(text, sp)
                    and _dated(text[sp["start"]:sp["end"]]) >= INDEX_RUN_MIN]
            if secs:
                for sp in sorted(secs, key=lambda s: s["start"] - s["end"])[:5]:
                    add(INDEX_NAME, text, "section", (sp["start"], sp["end"]), sp["title"], reason, {"heading": sp["line"]})
            else:
                pos, run, header = 0, None, None
                offsets = []
                for ln in lines:
                    offsets.append(pos)
                    pos += len(ln)
                runs = []
                for i, ln in enumerate(lines):
                    cells = _cells(ln)
                    nxt = _cells(lines[i + 1]) if i + 1 < len(lines) else None
                    if cells and nxt and _is_sep(nxt):
                        header = (ln.rstrip("\n"), lines[i + 1].rstrip("\n"), len(cells))
                    paths = cell_paths(cells[0]) if cells and not _is_sep(cells) else []
                    top = paths[0].split("/", 1)[0] if paths and "/" in paths[0] else None
                    if top and run and run["dir"] == top:
                        run["end"] = i
                    else:
                        if run:
                            runs.append(run)
                        run = {"dir": top, "start": i, "end": i, "header": header} if top else None
                if run:
                    runs.append(run)
                for r in sorted((r for r in runs if r["end"] - r["start"] + 1 >= INDEX_RUN_MIN and r["header"]),
                                key=lambda r: r["start"] - r["end"])[:5]:
                    end_off = offsets[r["end"]] + len(lines[r["end"]])
                    add(INDEX_NAME, text, "rows", (offsets[r["start"]], end_off), r["dir"] + "/", reason,
                        {"table_header": r["header"][0], "table_sep": r["header"][1], "columns": r["header"][2]})
    return noms


def _section_stub(heading: str, target: str, day: str, blank_tail: bool):
    return (f"{heading}\n{STUB_MARK}\n> Moved to `{target}` on {day}. This is a pointer only; do not write here.\n"
            + ("\n" if blank_tail else ""))


def _topic_file(source: str, title: str, day: str, body: str, kind: str, table=None):
    lead = (f"# {source} · {title}\n\n"
            f"> Split from `{source}` on {day}; the old place keeps a one-line pointer. Read and write this topic here. "
            "Everything below the marker is the moved text.\n\n")
    if kind == "rows":
        return lead + f"{TOPIC_MARK}\n{table[0]}\n{table[1]}\n{body}"
    return lead + f"{TOPIC_MARK}\n{body}"


def topic_body(text: str, kind: str):
    if TOPIC_MARK + "\n" not in text:
        raise GovernanceError("topic file lost its split:body marker; merge it by hand from the backup")
    after = text.split(TOPIC_MARK + "\n", 1)[1]
    return after.split("\n", 2)[2] if kind == "rows" else after


def _pointer_row(target: str, title: str, n: int, day: str, columns: int):
    cells = [f"`{target}`", f"Index part: {n} rows for `{title}`, split on {day}"] + [""] * max(0, columns - 2)
    return "| " + " | ".join(cells) + " |\n"


def add_index_row(text: str, path: str, note: str):
    """Append one row to the first table in INDEX.md (or one line at the end when it has no table)."""
    lines = text.splitlines(keepends=True)
    for i in range(len(lines) - 1):
        head, sep = _cells(lines[i]), _cells(lines[i + 1])
        if head and sep and _is_sep(sep):
            cells = [f"`{path}`", note] + [""] * max(0, len(head) - 2)
            row = "| " + " | ".join(cells) + " |\n"
            j = i + 2
            while j < len(lines) and _cells(lines[j]) is not None:
                j += 1
            if j and not lines[j - 1].endswith("\n"):
                lines[j - 1] += "\n"
            return "".join(lines[:j] + [row] + lines[j:]), row
    row = f"- `{path}` | {note}\n"
    return (text if text.endswith("\n") or not text else text + "\n") + row, row


def topic_apply(root: Path, plan_sha: str, confirm=False, file=None, section=None, today=None):
    if not confirm:
        raise GovernanceError("a topic split changes what agents read at session start; review the nomination, "
                              "then repeat with --confirm")
    with FileLock(memory_dir(root) / "split.lock"):
        nom = next((n for n in topic_nominations(root, file, section, today) if n["plan_sha"] == plan_sha), None)
        if not nom:
            raise GovernanceError(f"no current nomination has plan_sha {plan_sha}; the file changed or the day rolled over; "
                                  "run split topic propose again")
        rel, kind, target, day = nom["file"], nom["kind"], nom["target"], nom["date"]
        text = read_text(root / rel)
        if "\r" in text:
            raise GovernanceError(f"{rel} has CR line endings; topic splits need LF")
        piece = text[nom["start"]:nom["end"]]
        if kind == "section":
            stub = _section_stub(nom["heading"], target, day, piece.endswith("\n\n"))
            target_text = _topic_file(rel, nom["section"], day, piece, kind)
        else:
            n = piece.count("\n")
            stub = _pointer_row(target, nom["section"], n, day, nom["columns"])
            target_text = _topic_file(rel, nom["section"], day, piece, kind, (nom["table_header"], nom["table_sep"]))
        new_src = text[:nom["start"]] + stub + text[nom["end"]:]
        if new_src.count(stub) != 1:
            raise GovernanceError("the pointer would not be unique in the file; nothing was written")
        if new_src.replace(stub, topic_body(target_text, kind), 1) != text:
            raise GovernanceError("self-check failed in memory: the merged view would change; nothing was written")
        index_row, new_index = None, None
        if rel != INDEX_NAME and (root / INDEX_NAME).is_file():
            new_index, index_row = add_index_row(read_text(root / INDEX_NAME), target,
                                                 f"{rel} topic \"{nom['section']}\", split on {day}")
        tx = new_tx(root, "topic", plan_sha)
        modified = [rel] + ([INDEX_NAME] if new_index is not None else [])
        manifest = OrderedDict(
            tx=tx, kind="topic", piece=kind, file=rel, section=nom["section"], target=target, status="applying",
            ts=now_iso(), plan_sha=plan_sha, stub=stub, index_row=index_row, created=[target], modified=modified,
            backups=backup_files(root, tx, modified), before={"source_sha256": sha256_text(text)},
        )
        save_manifest(root, manifest)
        try:
            if (root / target).exists():
                raise GovernanceError(f"{target} already exists")
            write_text_atomic(root / target, target_text)
            write_text_atomic(root / rel, new_src)
            if new_index is not None:
                write_text_atomic(root / INDEX_NAME, new_index)
            if read_text(root / rel).replace(stub, topic_body(read_text(root / target), kind), 1) != text:
                raise GovernanceError("self-check failed on disk: the merged view changed")
        except Exception:
            restore(root, manifest)
            manifest["status"] = "failed_rolled_back"
            save_manifest(root, manifest)
            raise
        rid = next_receipt_id(root)
        append_receipt(root, {"type": "split", "receipt": rid, "kind": "topic", "tx": tx, "file": rel,
                              "target": target, "status": "applied", "ts": now_iso()})
        manifest.update(status="applied", receipt=rid)
        manifest["map"] = refresh_map(root)
        save_manifest(root, manifest)
        return manifest


def topic_rollback(root: Path, tx: str):
    manifest = load_manifest(root, tx)
    if manifest.get("kind") != "topic" or manifest.get("status") != "applied":
        raise GovernanceError(f"{tx} is not an applied topic split (status={manifest.get('status')})")
    rel, target, stub, kind = manifest["file"], manifest["target"], manifest["stub"], manifest["piece"]
    with FileLock(memory_dir(root) / "split.lock"):
        src = read_text(root / rel)
        if src.count(stub) != 1:
            raise GovernanceError(f"the pointer in {rel} was edited; restore it or merge by hand "
                                  f"(backup in .memory/splits/backup/{tx}/)")
        if not (root / target).is_file():
            raise GovernanceError(f"{target} is missing; cannot merge it back")
        merged = src.replace(stub, topic_body(read_text(root / target), kind), 1)
        new_index = None
        if manifest.get("index_row") and (root / INDEX_NAME).is_file():
            idx = read_text(root / INDEX_NAME)
            if manifest["index_row"] in idx:
                new_index = idx.replace(manifest["index_row"], "", 1)
        write_text_atomic(root / rel, merged)
        if new_index is not None:
            write_text_atomic(root / INDEX_NAME, new_index)
        (root / target).unlink()
        d = (root / target).parent
        if d != root and d.is_dir() and not any(d.iterdir()):
            d.rmdir()
        if read_text(root / rel) != merged:
            raise GovernanceError(f"rollback self-check failed on disk; backups are in .memory/splits/backup/{tx}/")
        rid = next_receipt_id(root)
        append_receipt(root, {"type": "split", "receipt": rid, "kind": "topic", "tx": tx, "file": rel,
                              "target": target, "status": "rolled_back", "ts": now_iso()})
        manifest.update(status="rolled_back", rollback_receipt=rid, rolled_back_at=now_iso())
        manifest["map"] = refresh_map(root)
        save_manifest(root, manifest)
        return manifest


def _emit(data, as_json, lines):
    if as_json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def cmd_split(args):
    root = Path(args.target).resolve()
    today = parse_today(getattr(args, "today", None))
    if args.split_kind == "stub":
        stubs, ghosts = stub_problems(root)
        found = stubs + ghosts
        _emit({"stub": stubs, "ghost": ghosts}, args.json,
              [f"  {f['item']}: {f['detail']}" for f in found] + ["STUBS OK" if not found else f"STUB FINDINGS {len(found)}"])
        return 1 if found else 0
    if args.split_kind == "volume":
        if args.cmd == "plan":
            plan = volume_plan(root, args.file or LOG_NAME, today, args.threshold)
            vols = [f"  {v['month']} -> {v['path']} ({v['sections']} sections, {v['bytes']:,} B"
                    + (", merged into the existing volume" if v["merge_into_existing"] else "") + ")" for v in plan["volumes"]]
            _emit(plan, args.json, [f"PLAN {plan['file']} eligible={str(plan['eligible']).lower()} plan_sha={plan['plan_sha']}"]
                  + [f"  reason: {r}" for r in plan["reasons"]] + vols
                  + [f"  keep: {plan['keep']['sections']} sections, {plan['keep']['bytes']:,} B ({plan['order']})"])
            return 0
        if args.cmd == "apply":
            if not args.plan_sha:
                raise GovernanceError("split volume apply needs --plan-sha from split volume plan")
            m = volume_apply(root, args.file or LOG_NAME, args.plan_sha, today=today, threshold=args.threshold)
            _emit(m, args.json, [f"CUT {m['file']} months={','.join(sorted(m['moved']))} tx={m['tx']} receipt={m['receipt']}",
                                 "Full view unchanged (checked in memory and on disk)."])
            return 0
        if args.cmd == "auto":
            rows = volume_auto(root, today, args.threshold, args.dry_run)
            _emit(rows, args.json, [f"{r['result'].upper()} {r['file']}"
                                    + (f" tx={r['tx']} receipt={r['receipt']} months={','.join(r['months'])}" if r["result"] == "cut"
                                       else f" plan_sha={r['plan_sha']}" + ("" if r["eligible"] else " — " + "; ".join(r["reasons"])))
                                    for r in rows] or ["Nothing to cut."])
            return 0
        if args.cmd == "rollback":
            if not args.tx:
                raise GovernanceError("split volume rollback needs --tx")
            m = volume_rollback(root, args.tx)
            _emit(m, args.json, [f"ROLLED BACK {m['tx']} on {m['file']}; receipt={m['rollback_receipt']}; full view unchanged"])
            return 0
        problems = volume_verify(root, [norm_path(args.file)] if args.file else None)
        _emit({"problems": problems}, args.json, [f"  {p}" for p in problems] + ["VOLUMES OK" if not problems else f"VOLUME FINDINGS {len(problems)}"])
        return 1 if problems else 0
    if args.cmd == "propose":
        noms = topic_nominations(root, args.file, args.section, today)
        _emit(noms, args.json, [f"NOMINATE plan_sha={n['plan_sha']} {n['file']} \"{n['section']}\" -> {n['target']} "
                                f"({n['lines']} lines, {n['bytes']:,} B); {n['reason']}" for n in noms]
              + (["Review each, then: split topic apply --plan-sha <sha> --confirm"] if noms else ["Nothing to nominate: MEMORY.md and INDEX.md are within budget."]))
        return 0
    if args.cmd == "apply":
        if not args.plan_sha:
            raise GovernanceError("split topic apply needs --plan-sha from split topic propose")
        m = topic_apply(root, args.plan_sha, args.confirm, args.file, args.section, today)
        _emit(m, args.json, [f"SPLIT {m['file']} \"{m['section']}\" -> {m['target']} tx={m['tx']} receipt={m['receipt']}",
                             "The old place keeps a pointer; merged view unchanged."])
        return 0
    if not args.tx:
        raise GovernanceError("split topic rollback needs --tx")
    m = topic_rollback(root, args.tx)
    _emit(m, args.json, [f"MERGED BACK {m['tx']}: {m['target']} -> {m['file']}; receipt={m['rollback_receipt']}"])
    return 0


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", default=".", help="project root, default: current directory")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create .memory config and copy this CLI without overwriting")
    impact = sub.add_parser("impact", help="map a change to surfaces and scan old terms")
    impact.add_argument("--event", required=True)
    impact.add_argument("--terms", action="append", required=True, help="old name/path/claim; repeat as needed")
    impact.add_argument("--record", action="store_true", help="append a pending impact receipt")
    verify = sub.add_parser("verify", help="verify an impact receipt after references are updated")
    verify.add_argument("--receipt", required=True)
    verify.add_argument("--allow", action="append", default=[], help="glob for intentional historical mentions; repeatable")
    premise = sub.add_parser("premise", help="evaluate active premise signals")
    premise.add_argument("action", choices=["check", "list"], nargs="?", default="check")
    contradiction = sub.add_parser("contradict", help="add, resolve, list, or check contradictions")
    contradiction.add_argument("action", choices=["add", "resolve", "list", "check"])
    contradiction.add_argument("--id")
    contradiction.add_argument("--old")
    contradiction.add_argument("--new")
    contradiction.add_argument("--evidence")
    contradiction.add_argument("--open", action="store_true")
    sub.add_parser("doctor", help="run all governance checks")
    upgrade = sub.add_parser("upgrade", help="preview or apply a lossless CLI-only upgrade")
    upgrade.add_argument("--source", help="newer memory_governance.py; defaults to the current source file")
    upgrade.add_argument("--apply", action="store_true", help="back up and replace the CLI after the preview")
    route = sub.add_parser("route", help="one compact card for a change: reuse, components, events, tier, premises")
    route.add_argument("intent", nargs="?", default="", help="the change in your own words")
    route.add_argument("--paths", nargs="*", default=[], help="paths the change touches")
    route.add_argument("--event", action="append", default=[], help="name an event type; repeatable")
    route.add_argument("--reversible", action="store_true", help="declare the change reversible inside the project")
    route.add_argument("--single-area", action="store_true", help="declare the change stays in one map area")
    route.add_argument("--detail", action="store_true", help="no 2 KB budget: every row, full text")
    route.add_argument("--json", action="store_true")
    lookup_p = sub.add_parser("lookup", help="read rows from CAPABILITIES.md or MAP.md")
    lookup_p.add_argument("--registry", choices=["capability", "map"], required=True)
    lookup_p.add_argument("--query", default="", help="words that must all appear in a row")
    lookup_p.add_argument("--status", help="capability state, e.g. active")
    lookup_p.add_argument("--limit", type=int, default=10)
    lookup_p.add_argument("--detail", action="store_true")
    lookup_p.add_argument("--json", action="store_true")
    audit = sub.add_parser("audit", help="unregistered capabilities, ghost entries, orphans, stubs, volumes")
    audit.add_argument("--json", action="store_true")
    map_p = sub.add_parser("map", help="keep the generated block in MAP.md current")
    map_p.add_argument("action", choices=["sync"])
    map_p.add_argument("--check", action="store_true", help="report drift (exit 1) without writing")
    map_p.add_argument("--json", action="store_true")
    split = sub.add_parser("split", help="month volumes and topic splits, with receipts and rollback")
    split_sub = split.add_subparsers(dest="split_kind", required=True)
    vol = split_sub.add_parser("volume", help="cut finished months of an append-only log into volumes")
    vol.add_argument("cmd", choices=["plan", "apply", "auto", "rollback", "verify"])
    vol.add_argument("--file", help=f"default {LOG_NAME}")
    vol.add_argument("--plan-sha")
    vol.add_argument("--tx")
    vol.add_argument("--dry-run", action="store_true", help="auto: print the plans, cut nothing")
    vol.add_argument("--threshold", type=int, help=f"bytes, default {VOLUME_THRESHOLD}")
    vol.add_argument("--today", help="YYYY-MM-DD; defaults to today (for tests and backfills)")
    vol.add_argument("--json", action="store_true")
    topic = split_sub.add_parser("topic", help="nominate and apply topic splits of MEMORY.md and INDEX.md")
    topic.add_argument("cmd", choices=["propose", "apply", "rollback"])
    topic.add_argument("--file", help="nominate one section of this file regardless of budget")
    topic.add_argument("--section", help="the heading text of that section")
    topic.add_argument("--plan-sha")
    topic.add_argument("--tx")
    topic.add_argument("--confirm", action="store_true", help="a person reviewed the nomination")
    topic.add_argument("--today", help="YYYY-MM-DD; defaults to today")
    topic.add_argument("--json", action="store_true")
    stub = split_sub.add_parser("stub", help="check that pointer stubs hold only their pointer")
    stub.add_argument("cmd", choices=["check"])
    stub.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "impact":
            return cmd_impact(args)
        if args.command == "verify":
            return cmd_verify(args)
        if args.command == "premise":
            return cmd_premise(args)
        if args.command == "contradict":
            if args.action == "add" and not all([args.old, args.new, args.evidence]):
                raise GovernanceError("contradict add needs --old, --new, and --evidence")
            if args.action == "resolve" and not all([args.id, args.evidence]):
                raise GovernanceError("contradict resolve needs --id and --evidence")
            return cmd_contradict(args)
        if args.command == "doctor":
            return cmd_doctor(args)
        if args.command == "upgrade":
            return cmd_upgrade(args)
        if args.command == "route":
            return cmd_route(args)
        if args.command == "lookup":
            return cmd_lookup(args)
        if args.command == "audit":
            return cmd_audit(args)
        if args.command == "map":
            return cmd_map(args)
        if args.command == "split":
            return cmd_split(args)
        return 2
    except GovernanceError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
