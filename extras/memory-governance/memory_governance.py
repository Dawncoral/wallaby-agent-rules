#!/usr/bin/env python3
"""Memory governance CLI: conduction, premises, contradictions, and receipts.

Zero dependencies. Python 3.8+. The scanner is read-only; only explicit init,
impact --record, verify, and contradiction mutations write governance data.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.4.0"
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
    if truncated:
        print(f"WARNING scan stopped after {MAX_MATCHES} matching files; narrow the terms", file=sys.stderr)
    if skipped:
        print(f"WARNING skipped {len(skipped)} unreadable or oversized file(s): {skipped}", file=sys.stderr)
    if args.record:
        receipt = {
            "type": "impact", "receipt": next_receipt_id(root), "event": args.event,
            "terms": terms, "matches": matches, "truncated": truncated, "skipped": skipped,
            "surfaces": rule["surfaces"], "status": "pending", "ts": now_iso(),
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
                highest = max(highest, int(rid[1:]))
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
    if code == 0:
        print("DOCTOR OK")
    else:
        print(f"DOCTOR FINDINGS exit={code}")
    return code


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
        return 2
    except GovernanceError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
