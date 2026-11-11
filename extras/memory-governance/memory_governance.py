#!/usr/bin/env python3
"""Memory governance CLI: conduction, premises, contradictions, and receipts.

Zero dependencies. Python 3.8+. The scanner is read-only; only explicit init,
impact --record, route --record, verify, contradiction mutations, map sync,
split, write, id take, and events adopt write.

1.4.3 closes the loop between the registries and the memory files:
  route   one compact card per change: what to reuse, which map components,
          events and surfaces, the tier, and only the premises the change touches
  lookup  read-only rows from CAPABILITIES.md or MAP.md (the MCP server calls it)
  audit   unregistered capabilities, ghost entries, orphans, pointer stubs, volumes
  map     map sync keeps a generated block in MAP.md; --check reports drift
  split   month volumes for LOG.md (automatic), topic splits for MEMORY.md and
          INDEX.md (nominated, applied only with --confirm), rollback, verify
  write   one checked way to add a line to LOG.md, NOW.md, MEMORY.md, INDEX.md,
          PROPOSALS.md, CAPABILITIES.md, MAP.md or FAILURES.md; existing lines
          are never rewritten
  events  an append-only log of what the CLI wrote and which agent asked
  id      one counter per ID series (R, C, P, F, D or your own); numbers never repeat
A change takes two commands: route --record before it, verify after it.
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
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone
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


LOCK_STALE_SECONDS = 120


class FileLock:
    """One writer at a time on one machine. A lock older than two minutes belongs to a run that died, so it is removed."""

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
                try:
                    if time.time() - self.path.stat().st_mtime > LOCK_STALE_SECONDS:
                        self.path.unlink()
                        continue
                except OSError:
                    pass
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
    st = rules_status(root)
    res = st["resident"]
    print(f"RULES baseline: {res['rules']} always-loaded rule(s) in {len(res['files'])} instruction file(s), "
          f"{res['bytes'] / 1024:.1f} KB; audit reports when this grows (report only)")
    unregistered = unregistered_files(root)
    if unregistered is not None and load_audit_baseline(root) is None:
        save_audit_baseline(root, unregistered)
        if unregistered:
            print(f"AUDIT baseline: {len(unregistered)} script, skill or workflow file(s) are not in CAPABILITIES.md yet; "
                  "audit reports only new ones, and map sync lists these")
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
        record_event(root, "receipt.open", ref=receipt["receipt"], summary=f"{args.event}: {', '.join(terms)}")
        print(f"RECEIPT {receipt['receipt']} pending; run verify after reviewing the surfaces")
    return 0


def next_receipt_id(root: Path):
    """Receipt IDs come from the shared counter, which starts above every number already in use."""
    return take_id(root, "R", record=False)


def pending_receipts(rows):
    verified = {r.get("receipt") for r in rows if r.get("type") == "verification"}
    return [r for r in rows if r.get("type") == "impact" and r.get("receipt") not in verified]


def _receipt_time(value):
    try:
        ts = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def surface_path(root: Path, name: str):
    return config_path(root, "premises.json") if name == "PREMISES" else root / name


def surface_hashes(root: Path, surfaces):
    """The content hash of every surface that exists as a file, taken when a receipt is opened."""
    out = OrderedDict()
    for name in surfaces or []:
        digest = file_sha(surface_path(root, name))
        if digest:
            out[name] = digest
    return out


def unchanged_surfaces(root: Path, impact):
    """Surfaces whose content is the same as when the receipt was opened."""
    return [name for name, digest in (impact.get("surface_sha256") or {}).items()
            if file_sha(surface_path(root, name)) == digest]


def cmd_verify(args):
    root = Path(args.target).resolve()
    rows = read_receipts(root)
    rid = args.receipt
    if not rid:
        pending = pending_receipts(rows)
        if not pending:
            print("No pending receipts.")
            return 0
        if len(pending) > 1:
            for r in pending:
                print(f"  {r.get('receipt')} {r.get('intent') or r.get('event') or ''}".rstrip())
            raise GovernanceError(f"{len(pending)} receipts are pending; name one with --receipt")
        rid = pending[0].get("receipt")
    impacts = [r for r in rows if r.get("type") == "impact" and r.get("receipt") == rid]
    if not impacts:
        raise GovernanceError(f"receipt {rid} not found")
    verified = any(r.get("type") == "verification" and r.get("receipt") == rid for r in rows)
    if verified:
        print(f"{rid} already verified")
        return 0
    impact = impacts[-1]
    terms = impact.get("terms") or []
    matches, truncated, skipped = scan(root, terms, args.allow) if terms else ([], False, [])
    blocked, notes = [], []
    if impact.get("source") == "route":   # receipts opened by route --record carry the rest of the check
        wanted = {p.get("id") for p in impact.get("premises") or []
                  if isinstance(p, dict) and (impact.get("premise_review") or p.get("scope") == "matched")}
        if wanted and config_path(root, "premises.json").exists():
            for premise, state, detail in premise_rows(root):
                if premise["id"] not in wanted:
                    continue
                line = f"PREMISE {premise['id']} {premise['level']} {state.upper()}: {detail}"
                if state == "failing" and premise["level"] in {"P0", "P1"}:
                    blocked.append(line)
                elif state != "ok":
                    notes.append(line)
        if (root / CAPS_NAME).is_file():
            caps_text = read_text(root / CAPS_NAME)
            for rel in impact.get("register") or []:
                if (root / rel).exists() and not registered_in(rel, caps_text):
                    blocked.append(f"REGISTER {rel} is not in {CAPS_NAME}")
        quiet = unchanged_surfaces(root, impact)
        if quiet:
            notes.append("REVIEW unchanged since the receipt was opened: " + ", ".join(quiet)
                         + " (confirm they need no change)")
    if matches or truncated or skipped or blocked:
        print(f"NOT VERIFIED {rid}: {len(matches)} unresolved and {len(skipped)} unread file(s)"
              + (f", {len(blocked)} other finding(s)" if blocked else ""))
        for row in matches:
            print(f"  {row['path']} ({row['count']})")
        if skipped:
            print(f"  unreadable or oversized: {skipped}")
        for line in blocked + notes:
            print(f"  {line}")
        if matches or truncated or skipped:
            print("Update the references or allow intentional historical mentions with --allow <glob>.")
        return 1
    for line in notes:
        print(line)
    evidence = "zero unresolved matches" if terms else "no old terms to scan"
    entry = {"type": "verification", "receipt": rid, "status": "verified", "evidence": evidence, "ts": now_iso()}
    if impact.get("source") == "route":
        entry["notes"] = notes
        if (root / MAP_NAME).is_file() and MAP_BEGIN in read_text(root / MAP_NAME):
            entry["map"] = refresh_map(root)["status"]
    append_receipt(root, entry)
    record_event(root, "receipt.verify", actor=getattr(args, "actor", None), ref=rid, summary=evidence)
    print(f"VERIFIED {rid}: {evidence}")
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
        cid = take_id(root, "C", record=False)
        row = {
            "id": cid, "old": args.old, "new": args.new, "evidence": args.evidence,
            "status": "open", "history": [{"ts": now_iso(), "status": "open", "evidence": args.evidence}],
        }
        rows.append(row)
        atomic_json(config_path(root, "contradictions.json"), data)
        record_event(root, "contradiction.add", ref=cid, summary=f"{args.old} -> {args.new}")
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
        record_event(root, "contradiction.resolve", ref=args.id, summary=args.evidence)
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
    pending = pending_receipts(read_receipts(root))
    print(f"CONTRADICTIONS open={len(open_rows)}")
    print(f"RECEIPTS pending={len(pending)}")
    if open_rows or pending:
        code = max(code, 1)
    report = audit_report(root)
    counts = " ".join(f"{k}={len(report[k])}" for k in AUDIT_KINDS)
    print(f"AUDIT {counts}" + (f" (skipped: {'; '.join(report['skipped'])})" if report["skipped"] else ""))
    for line in baseline_lines(report):   # report only
        print(line)
    map_state = map_sync(root, check=True)
    print(f"MAP {map_state['status']}" + (" (counts refresh on the next map sync)" if map_state.get("counts_stale") else ""))
    for line in rules_lines(rules_status(root)):   # report only: never changes the exit code
        print(line)
    stream = events_status(root)
    for line in events_lines(stream):
        print(line)
    dupes = id_duplicates(root)
    for line in dupes:
        print(f"IDS {line}")
    if any(report[k] for k in AUDIT_KINDS) or map_state["status"] == "drift" or stream["problems"] or dupes:
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
        nxt.append("repeat this command with --record to open a receipt (after a rename, add --terms \"<old name>\"); "
                   "when the change is done, run: python3 scripts/memory_governance.py verify")
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
    card["_full"] = {"register": list(register), "components": [c["component"] for c in components],
                     "capabilities": [r["capability"] for r in reuse],
                     "premises": [{"id": p["id"], "scope": p["scope"]} for p in premises]}
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
    if card.get("receipt"):
        r = card["receipt"]
        out.append(f"RECEIPT {r['id']} pending" + (f"; {r['matches']} file(s) still hold the old terms" if r.get("matches") else ""))
    elif card.get("receipt_note"):
        out.append(f"RECEIPT {card['receipt_note']}")
    for step in card["next"]:
        out.append(f"NEXT {step}")
    if card.get("more"):
        out.append("MORE " + ", ".join(f"{k}+{v}" for k, v in card["more"].items()) + " (use --detail)")
    text = "\n".join(out)
    if len(text.encode("utf-8")) > OUTPUT_BUDGET and not card.get("_detail"):
        cut = text.encode("utf-8")[:OUTPUT_BUDGET - 40].decode("utf-8", "ignore").rsplit("\n", 1)[0]
        text = cut + "\nMORE card cut at 2 KB (use --detail)"
    return text


def open_route_receipt(root: Path, card, full, terms, actor=None):
    """route --record: one pending receipt that verify can close without another command in between."""
    if not config_path(root, "impact.json").exists():
        raise GovernanceError("--record needs the governance files; run init first")
    terms = [t for t in terms if t and t.strip()]
    matches, truncated, skipped = scan(root, terms) if terms else ([], False, [])
    names = [e["event"] for e in card["events"]]
    receipt = OrderedDict(
        type="impact", receipt=next_receipt_id(root), event=names[0] if names else "route", events=names, terms=terms,
        matches=matches, truncated=truncated, skipped=skipped, surfaces=card["surfaces"], status="pending", ts=now_iso(),
        components=full["components"], capabilities=full["capabilities"], source="route", intent=card["intent"],
        paths=card["paths"], tier=card["tier"], premise_review=card["premise_review"], premises=full["premises"],
        register=full["register"], surface_sha256=surface_hashes(root, card["surfaces"]),
    )
    append_receipt(root, receipt)
    record_event(root, "receipt.open", actor=actor, ref=receipt["receipt"],
                 summary=card["intent"] or ", ".join(card["paths"]))
    return receipt


def cmd_route(args):
    root = Path(args.target).resolve()
    card = route_card(root, args.intent, args.paths, args.event, args.reversible, args.single_area, args.detail)
    full = card.pop("_full")
    if args.record or args.terms:
        if card["tier"] == "light" and not args.terms:
            card["receipt"], card["receipt_note"] = None, "not needed: the tier is light"
        else:
            receipt = open_route_receipt(root, card, full, args.terms, args.actor)
            card["receipt"] = {"id": receipt["receipt"], "matches": len(receipt["matches"])}
            card["next"] = [n for n in card["next"] if "--record" not in n and "premise check" not in n]
            card["next"].append(f"when the change is done: python3 scripts/memory_governance.py verify --receipt {receipt['receipt']}")
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
AUDIT_BASELINE = "audit_baseline.json"
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


def unregistered_files(root: Path):
    """Capability-like files that CAPABILITIES.md does not list; None when the project has no CAPABILITIES.md."""
    if not (root / CAPS_NAME).is_file():
        return None
    impact, _ = load_impact_or_default(root)
    globs, exempt = _audit_config(impact)
    caps_text = read_text(root / CAPS_NAME)
    return [rel for rel in walk_files(root) if capability_like(rel, globs, exempt) and not registered_in(rel, caps_text)]


def load_audit_baseline(root: Path):
    p = config_path(root, AUDIT_BASELINE)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data.get("missing"), list) else None


def save_audit_baseline(root: Path, unregistered):
    data = OrderedDict(recorded_at=now_iso(), missing=sorted(unregistered))
    atomic_json(config_path(root, AUDIT_BASELINE), data)
    return data


def audit_baseline(root: Path, unregistered, record=True):
    """The first audit records what was already unregistered; later audits report only what is new."""
    base = load_audit_baseline(root)
    if base is None and record and memory_dir(root).is_dir():
        base = save_audit_baseline(root, unregistered)
    return set(base["missing"]) if base else set()


def baseline_lines(report):
    n = len(report.get("baselined") or [])
    if not n:
        return []
    return [f"AUDIT baseline: {n} file(s) were unregistered before the first audit and are not counted; "
            "map sync lists them, audit --rebaseline resets (report only)"]


def audit_report(root: Path):
    report = OrderedDict((k, []) for k in AUDIT_KINDS)
    report["skipped"] = []
    report["baselined"] = []
    caps = load_caps(root)
    rows_map = load_map(root)
    if caps is None:
        report["skipped"].append("no CAPABILITIES.md: missing and orphan checks off")
    else:
        unregistered = unregistered_files(root) or []
        known = audit_baseline(root, unregistered)
        for rel in unregistered:
            if rel in known:
                report["baselined"].append(rel)
            else:
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
    if args.rules or args.rules_answer or args.rebaseline_rules:
        return cmd_audit_rules(args, root)
    if args.rebaseline:
        unregistered = unregistered_files(root)
        if unregistered is None:
            raise GovernanceError("no CAPABILITIES.md: there is nothing to baseline")
        data = save_audit_baseline(root, unregistered)
        print(f"AUDIT baseline reset: {len(data['missing'])} unregistered file(s) accepted as they are")
        return 0
    report = audit_report(root)
    total = sum(len(report[k]) for k in AUDIT_KINDS)
    if args.json:
        st = rules_status(root)
        summary = OrderedDict(resident=st["resident"], on_demand=st["on_demand"], over_baseline=st["over_baseline"],
                              duplicate_pairs=len(st["pairs"]))
        print(json.dumps(OrderedDict(report, total=total, rules=summary), ensure_ascii=False))
        return 1 if total else 0
    for k in AUDIT_KINDS:
        print(f"{k.upper()} {len(report[k])}")
        for f in report[k][:50]:
            print(f"  {f['item']}: {f['detail']}")
    for s in report["skipped"]:
        print(f"SKIPPED {s}")
    for line in baseline_lines(report):
        print(line)
    print("AUDIT OK" if not total else f"AUDIT FINDINGS {total}; run map sync for paste-ready rows")
    for line in rules_lines(rules_status(root)):
        print(line)
    return 1 if total else 0


# ---------------------------------------------------------------------------
# 1.4.3 · rules: the instructions agents load, against a baseline (report only)
# ---------------------------------------------------------------------------

RESIDENT_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursorrules", ".github/copilot-instructions.md")
NESTED_NAMES = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursorrules"}
SKILL_DIRS = (".claude/skills", ".agents/skills", "skills", ".github/skills")
RULE_DIRS = ((".cursor/rules", (".mdc", ".md")), (".claude/rules", (".md",)), (".github/instructions", (".md",)))
RULES_BASELINE = "rules_baseline.json"
RULE_WORDS = re.compile(r"(红线|必须|禁止|严禁|务必|一律|绝不|不许|不得|\bmust\b|\bnever\b|\balways\b|\bdo not\b"
                        r"|\bdon't\b|\brequired\b|\bforbidden\b)", re.I)
RULE_SPLIT = re.compile(r"[；;。|]")
DUP_MIN_GRAMS = 6
DUP_JACCARD = 0.85
DUP_SHOWN = 5
BASELINE_BYTES_SLACK = 0.10


def rule_files(root: Path):
    """Files agents load. Resident: the root entry files. On demand: nested entry files, skills, rule folders.
    Only the places agents read; a symlink or a second path to the same file counts once."""
    seen, resident, on_demand = set(), [], []

    def add(bucket, p: Path):
        try:
            if not p.is_file():
                return
            real = p.resolve()
        except OSError:
            return
        if real not in seen:
            seen.add(real)
            bucket.append(p.relative_to(root).as_posix())

    for name in RESIDENT_FILES:
        add(resident, root / name)
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        if Path(base) == root:
            continue
        for name in sorted(files):
            if name in NESTED_NAMES:
                add(on_demand, Path(base) / name)
    for d in SKILL_DIRS:
        if (root / d).is_dir():
            for p in sorted((root / d).glob("*/SKILL.md")):
                add(on_demand, p)
    for d, exts in RULE_DIRS:
        if (root / d).is_dir():
            for p in sorted((root / d).rglob("*")):
                if p.suffix in exts:
                    add(on_demand, p)
    return resident, on_demand


def _join_wrapped(lines):
    """Merge a paragraph's wrapped lines into one; list items, headings, tables, quotes and fences start new blocks."""
    out, buf, start = [], [], 0

    def flush():
        if buf:
            out.append((start, " ".join(x.strip() for x in buf)))

    for i, line in enumerate(lines, 1):
        s = line.strip()
        if (not s) or s.startswith(("#", "|", "```", ">")) or re.match(r"^([-*+]|\d+[.)])\s", s):
            flush()
            buf = []
            if s:
                buf, start = [line], i
                if s.startswith(("#", "|", "```")):
                    flush()
                    buf = []
        else:
            if not buf:
                start = i
            buf.append(line)
    flush()
    return out


def extract_rules(text: str):
    """(line, rule) pairs: sentences with a rule word, outside front matter, code fences and headings."""
    s = text.strip()
    if "\n" not in s and len(s) < 200 and s.endswith(".md"):
        return []   # a symlink checked out as a one-line text file
    lines = text.splitlines()
    fm_end = 0
    if lines and lines[0].strip() == "---":
        fm_end = next((i + 1 for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
    out, in_code = [], False
    for start, block in _join_wrapped(lines):
        b = block.strip()
        if start <= fm_end:
            continue
        if b.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not b or b.startswith("#") or (b.startswith("|") and _is_sep(_cells(b) or [])):
            continue
        if not RULE_WORDS.search(b):
            continue
        for chunk in RULE_SPLIT.split(b):
            c = chunk.strip(" -*>")
            if len(c) >= 4 and RULE_WORDS.search(c):
                out.append((start, c))
    return out


def _grams(s: str):
    s = s.replace("`", " ")
    cjk = re.findall(r"[一-鿿]", s)
    return {cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)} | {w.lower() for w in re.findall(r"[A-Za-z_][\w.-]{2,}", s)}


def duplicate_pairs(rules):
    """Near-verbatim pairs across files (Jaccard over words and CJK bigrams); same-file repeats are left alone."""
    grams = [_grams(r["text"]) for r in rules]
    index = defaultdict(list)
    for i, g in enumerate(grams):
        if len(g) >= DUP_MIN_GRAMS:
            for x in g:
                index[x].append(i)
    pairs = []
    for i, g in enumerate(grams):
        if len(g) < DUP_MIN_GRAMS:
            continue
        hits = Counter(j for x in g for j in index[x] if j > i)
        for j, inter in hits.items():
            if rules[i]["file"] == rules[j]["file"]:
                continue
            jac = inter / len(g | grams[j])
            if jac >= DUP_JACCARD:
                pairs.append((round(jac, 2), i, j))
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))
    return pairs


def rules_census(root: Path):
    t0 = time.time()
    resident, on_demand = rule_files(root)
    rules, sizes = [], {}
    for rel in resident + on_demand:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sizes[rel] = len(text.encode("utf-8"))
        kind = "resident" if rel in resident else "on_demand"
        rules.extend({"file": rel, "line": ln, "text": t, "kind": kind} for ln, t in extract_rules(text))
    pairs = duplicate_pairs(rules)
    return OrderedDict(
        resident=OrderedDict(files=resident, rules=sum(1 for r in rules if r["kind"] == "resident"),
                             bytes=sum(sizes.get(f, 0) for f in resident)),
        on_demand=OrderedDict(files=len(on_demand), bytes=sum(sizes.get(f, 0) for f in on_demand)),
        rules=rules, pairs=pairs, seconds=round(time.time() - t0, 2))


def rules_nominations(census):
    """Group duplicate pairs into clusters; each gets one paste-ready fix (keep one copy, point to it)."""
    rules, parent = census["rules"], {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, a, b in census["pairs"]:
        parent[find(a)] = find(b)
    groups = defaultdict(set)
    for _, a, b in census["pairs"]:
        groups[find(a)] |= {a, b}
    out = []
    for members in sorted(groups.values(), key=lambda m: (-len(m), min(m))):
        rows = sorted(members, key=lambda i: (rules[i]["kind"] != "resident", rules[i]["file"], rules[i]["line"]))
        keep = rules[rows[0]]
        target = keep["file"] if keep["kind"] == "resident" else "docs/shared-rules.md"
        words = keep["text"].split()
        quote = " ".join(words[:10]) + ("…" if len(words) > 10 else "")
        where = [f"{rules[i]['file']}:{rules[i]['line']}" for i in rows]
        replace = [w for w in where if not (target == keep["file"] and w == f"{keep['file']}:{keep['line']}")]
        out.append(OrderedDict(text=keep["text"][:200], places=where, keep_in=target,
                               fix=(f"keep this rule once in {target}; at {', '.join(replace)} replace it with: "
                                    f"See {target}: \"{quote}\"")))
    return out


def load_rules_baseline(root: Path):
    p = config_path(root, RULES_BASELINE)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_rules_baseline(root: Path, census, keep=None):
    data = OrderedDict(recorded_at=now_iso(), files=census["resident"]["files"], rules=census["resident"]["rules"],
                       bytes=census["resident"]["bytes"])
    if keep and keep.get("guardrails"):
        data["guardrails"] = keep["guardrails"]
    atomic_json(config_path(root, RULES_BASELINE), data)
    return data


def rules_status(root: Path, record=True):
    """Census plus baseline. The first run records the baseline silently; nothing here ever blocks."""
    census = rules_census(root)
    base = load_rules_baseline(root)
    recorded = False
    if base is None and record:
        base, recorded = save_rules_baseline(root, census), True
    res = census["resident"]
    over = bool(base) and (res["rules"] > base.get("rules", 0)
                           or res["bytes"] > base.get("bytes", 0) * (1 + BASELINE_BYTES_SLACK))
    census.update(baseline=base, over_baseline=over, recorded_now=recorded)
    return census


def rules_lines(status):
    """Text for audit and doctor: silent when the resident instructions are within baseline and nothing repeats."""
    out = []
    res, base = status["resident"], status.get("baseline") or {}
    if status["over_baseline"]:
        out.append(f"RULES over baseline: always-loaded instructions have {res['rules']} rules, {res['bytes'] / 1024:.1f} KB "
                   f"(baseline {base.get('rules', 0)}, {base.get('bytes', 0) / 1024:.1f} KB); merge or retire one "
                   "before adding another (report only)")
    noms = rules_nominations(status)
    if noms:
        out.append(f"RULES duplicates: {len(noms)} rule(s) repeat almost word for word across files; "
                   f"top {min(len(noms), DUP_SHOWN)}:")
        for n in noms[:DUP_SHOWN]:
            out.append(f"  {', '.join(n['places'])}: {n['fix']}")
    return out


def rules_json(status):
    return OrderedDict(
        resident=status["resident"], on_demand=status["on_demand"], baseline=status.get("baseline"),
        over_baseline=status["over_baseline"], duplicate_pairs=len(status["pairs"]),
        nominations=rules_nominations(status),
        guardrails=(status.get("baseline") or {}).get("guardrails"),
        rules=[OrderedDict(f=r["file"], l=r["line"], k=r["kind"][0], t=r["text"][:200]) for r in status["rules"]],
        seconds=status["seconds"])


def cmd_audit_rules(args, root: Path):
    if args.rules_answer:
        key, _, value = args.rules_answer.partition("=")
        if key != "guardrails" or value not in ("yes", "no"):
            raise GovernanceError("--rules-answer takes guardrails=yes or guardrails=no")
        status = rules_status(root)
        base = status["baseline"]
        base["guardrails"] = OrderedDict(answer=value, at=now_iso())
        atomic_json(config_path(root, RULES_BASELINE), base)
        print(f"RULES guardrails answer recorded: {value}; the weekly check will not ask again")
        return 0
    if args.rebaseline_rules:
        census = rules_census(root)
        data = save_rules_baseline(root, census, keep=load_rules_baseline(root))
        print(f"RULES baseline reset: {data['rules']} always-loaded rules, {data['bytes'] / 1024:.1f} KB")
        return 0
    print(json.dumps(rules_json(rules_status(root)), ensure_ascii=False))
    return 0


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


def _map_structure(region: str):
    """The part of the generated block that a person would call a change of structure: directories and split files."""
    out = []
    for line in region.splitlines():
        cells = _cells(line)
        if cells and len(cells) >= 6 and cells[0].startswith("`"):
            out.append((cells[0], cells[5]))
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
        if current is None:
            return {"status": "no_region", "missing": missing}
        if current == region:
            return {"status": "ok", "missing": missing}
        if _map_structure(current) == _map_structure(region):   # same directories and split files; only counts moved
            return {"status": "ok", "missing": missing, "counts_stale": True}
        return {"status": "drift", "missing": missing}
    if new_text == text:
        return {"status": "unchanged", "missing": missing}
    write_text_atomic(p, new_text)
    record_event(root, "map.sync", file=MAP_NAME, summary="generated block refreshed")
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
        print(json.dumps(OrderedDict(status=result["status"], reason=result.get("reason"),
                                     counts_stale=bool(result.get("counts_stale")), suggestions=sugg), ensure_ascii=False))
    else:
        print(f"MAP {result['status']}" + (f" ({result['reason']})" if result.get("reason") else "")
              + (" (counts refresh on the next map sync)" if result.get("counts_stale") else ""))
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
        record_files(root, "split.volume", sorted(set(created) | set(modified)), ref=rid, summary=f"{rel}: months {', '.join(sorted(moved))} cut")
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
        record_files(root, "split.volume.rollback", [rel] + sorted(new_vols), ref=rid, summary=f"{rel}: split {tx} rolled back")
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
        record_files(root, "split.topic", [target] + modified, ref=rid, summary=f"{rel}: \"{nom['section']}\" moved to {target}")
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
        record_files(root, "split.topic.rollback", [rel, target] + ([INDEX_NAME] if new_index is not None else []),
                     ref=rid, summary=f"{rel}: split {tx} merged back")
        return manifest


# ---------------------------------------------------------------------------
# 1.4.3 · events: an append-only log of what the CLI wrote and which agent asked
# ---------------------------------------------------------------------------

EVENTS_NAME = "events.jsonl"
ACTOR_ENV = "WALLABY_MEMORY_ACTOR"
TZ_ENV = "WALLABY_MEMORY_TZ_OFFSET"
_ACTOR_BAD = re.compile(r"[^A-Za-z0-9_.:@/-]")
_FENCE = re.compile(r"^\s*(```|~~~)")


def resolve_actor(value=None):
    """--actor, else $WALLABY_MEMORY_ACTOR, else "cli". The operating-system user name is never used."""
    raw = str(value or os.environ.get(ACTOR_ENV) or "").strip()
    return _ACTOR_BAD.sub("", raw)[:64] or "cli"


def events_path(root: Path):
    return config_path(root, EVENTS_NAME)


def file_sha(path: Path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _tail_line(path: Path):
    """The last non-empty line of a file, read from its end."""
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 65536))
            data = f.read()
    except OSError:
        return None
    lines = [ln for ln in data.split(b"\n") if ln.strip()]
    return lines[-1].decode("utf-8", "replace").rstrip("\r") if lines else None


def record_event(root: Path, event: str, actor=None, file=None, summary="", ref=None):
    """Append one event. A no-op in a project without .memory/: the pack is not installed there.

    seq is the line's position in the log. prev ties each line to the one before it, so a removed or edited line shows."""
    if not memory_dir(root).is_dir():
        return None
    path = events_path(root)
    with FileLock(Path(str(path) + ".lock")):
        seq, prev = 1, ""
        last = _tail_line(path) if path.is_file() else None
        if last:
            try:
                seq = int(json.loads(last)["seq"]) + 1
            except (KeyError, TypeError, ValueError):
                raise GovernanceError(".memory/events.jsonl does not end with a valid event; run events verify")
            prev = sha256_text(last)[:16]
        row = OrderedDict(seq=seq, ts=now_iso(), actor=resolve_actor(actor), event=event)
        if file:
            row["file"] = norm_path(file)
            sha = file_sha(root / row["file"])
            if sha:
                row["sha256"] = sha
        if ref:
            row["ref"] = ref
        if summary:
            row["summary"] = " ".join(str(summary).split())[:200]
        row["prev"] = prev
        with path.open("a", encoding="utf-8", newline="") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def record_files(root: Path, event: str, files, actor=None, ref=None, summary=""):
    """One event per file a command changed. It never raises: the change is already on disk."""
    out = []
    for rel in files:
        try:
            row = record_event(root, event, actor=actor, file=rel, ref=ref, summary=summary)
        except GovernanceError as e:
            print(f"WARNING event not recorded for {rel}: {e}", file=sys.stderr)
            continue
        if row:
            out.append(row)
    return out


def read_events(root: Path):
    path = events_path(root)
    if not path.is_file():
        return []
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for n, line in enumerate(f, 1):
            raw = line.rstrip("\r\n")
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
                if not isinstance(row, dict) or not isinstance(row.get("seq"), int):
                    row = {"_bad": True}
            except json.JSONDecodeError:
                row = {"_bad": True}
            row["_raw"], row["_line"] = raw, n
            rows.append(row)
    return rows


def events_status(root: Path):
    """Is the log whole, and which logged files changed without the CLI?"""
    rows = read_events(root)
    problems, expect, before = [], 1, None
    for r in rows:
        if r.get("_bad"):
            problems.append(f"line {r['_line']} is not a valid event")
            expect, before = None, r["_raw"]
            continue
        if expect is not None and r["seq"] != expect:
            problems.append(f"line {r['_line']} has seq {r['seq']}; expected {expect}")
        if r.get("prev", "") != (sha256_text(before)[:16] if before is not None else ""):
            problems.append(f"seq {r['seq']} does not follow the line above it (a line was edited, removed, or merged in)")
        expect, before = r["seq"] + 1, r["_raw"]
    good = [r for r in rows if not r.get("_bad")]
    latest = OrderedDict()
    for r in good:
        if r.get("file"):
            latest[r["file"]] = r
    outside = []
    for rel, r in latest.items():
        if not r.get("sha256"):
            continue  # the last event removed this file
        now = file_sha(root / rel)
        if now != r["sha256"]:
            outside.append({"file": rel, "seq": r["seq"], "state": "missing" if now is None else "changed"})
    return OrderedDict(events=len(good), last_seq=good[-1]["seq"] if good else 0, problems=problems[:20],
                       outside=outside, actors=dict(Counter(r.get("actor", "") for r in good)))


def events_lines(status):
    """Text for doctor and events verify. Silent until the log has its first event."""
    if not status["events"] and not status["problems"]:
        return []
    out = [f"EVENTS {status['events']} recorded, last seq {status['last_seq']}"]
    for p in status["problems"][:5]:
        out.append(f"  broken: {p}")
    if status["outside"]:
        names = ", ".join(o["file"] for o in status["outside"][:5])
        out.append(f"  {len(status['outside'])} logged file(s) changed outside the write command: {names} "
                   "(events adopt records them; report only)")
    return out


def cmd_events(args):
    root = Path(args.target).resolve()
    if args.action == "verify":
        st = events_status(root)
        if args.json:
            print(json.dumps(st, ensure_ascii=False))
        elif not st["events"] and not st["problems"]:
            print("No events yet. The log starts with the first write, id take, or receipt.")
        else:
            for line in events_lines(st):
                print(line)
            print("EVENTS OK" if not st["problems"] else f"EVENTS BROKEN {len(st['problems'])}")
        return 1 if st["problems"] else 0
    if args.action == "adopt":
        st = events_status(root)
        if st["problems"]:
            raise GovernanceError("the event log is broken; restore it from git or a backup before adopting changes")
        rows = []
        for o in st["outside"]:
            note = args.note or ("removed" if o["state"] == "missing" else "changed") + " outside the write command"
            rows.append(record_event(root, "adopt", actor=args.actor, file=o["file"], summary=note))
        _emit([{"seq": r["seq"], "file": r["file"]} for r in rows], args.json,
              [f"ADOPTED seq={r['seq']} {r['file']}" for r in rows] or ["Nothing to adopt: every logged file matches its last event."])
        return 0
    rows = [r for r in read_events(root) if not r.get("_bad")]
    if args.since is not None:
        rows = [r for r in rows if r["seq"] > args.since]
    if args.actor:
        rows = [r for r in rows if r.get("actor") == args.actor]
    if args.file:
        rows = [r for r in rows if r.get("file") == norm_path(args.file)]
    total, limit = len(rows), max(1, args.limit)
    rows = rows[:limit] if args.since is not None else rows[-limit:]
    clean_rows = [OrderedDict((k, v) for k, v in r.items() if not k.startswith("_")) for r in rows]
    lines = [f"{r['seq']}  {r.get('ts', '')}  {r.get('actor', '')}  {r.get('event', '')}"
             + (f"  {r['file']}" if r.get("file") else "") + (f"  {r['ref']}" if r.get("ref") else "")
             + (f"  {r['summary']}" if r.get("summary") else "") for r in clean_rows]
    if total > len(rows):
        lines.append(f"{total - len(rows)} more; raise --limit" + ("" if args.since is None else f" or continue with --since {rows[-1]['seq']}"))
    _emit(OrderedDict(total=total, events=clean_rows), args.json, lines or ["No events match."])
    return 0


# ---------------------------------------------------------------------------
# 1.4.3 · id: one counter per series, so two agents never hand out the same number
# ---------------------------------------------------------------------------

IDS_NAME = "ids.json"
DEFAULT_SERIES = OrderedDict([
    ("R", {"width": 6, "what": "receipts"}),
    ("C", {"width": 3, "what": "contradictions"}),
    ("P", {"width": 3, "what": "premises"}),
    ("F", {"width": 3, "what": "failures"}),
    ("D", {"width": 3, "what": "decisions"}),
])
SERIES_RE = re.compile(r"^[A-Z]{1,4}$")
ID_HOME_FILES = (MEMORY_NAME, "NOW.md", LOG_NAME, "PROPOSALS.md", "FAILURES.md")
ID_HOME_CONFIG = ("receipts.jsonl", "contradictions.json", "premises.json")
UNUSED_ID_DAYS = 7


def _hidden_lines(lines):
    """Indices of lines inside an HTML comment or a fenced code block: examples, not entries."""
    out, fence, comment = set(), False, False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if comment:
            out.add(i)
            if "-->" in s:
                comment = False
            continue
        if _FENCE.match(ln):
            out.add(i)
            fence = not fence
            continue
        if fence:
            out.add(i)
            continue
        if s.startswith("<!--"):
            out.add(i)
            if "-->" not in s:
                comment = True
    return out


def _visible_text(text: str):
    lines = text.splitlines(keepends=True)
    hidden = _hidden_lines(lines)
    return "".join(ln for i, ln in enumerate(lines) if i not in hidden)


def _id_numbers(text: str, series: str):
    return [int(n) for n in re.findall(r"(?<![A-Za-z0-9-])" + re.escape(series) + r"-(\d{1,9})(?![0-9])", text)]


def id_home_files(root: Path):
    """Where an ID may already be written: the memory files, their volumes and topic files, and the pack's own records."""
    files = [root / n for n in ID_HOME_FILES] + volume_files(root / LOG_NAME)
    topics = root / "MEMORY"
    if topics.is_dir():
        files += sorted(p for p in topics.iterdir() if p.suffix == ".md")
    return [(p, True) for p in files if p.is_file()] + [(config_path(root, n), False) for n in ID_HOME_CONFIG
                                                        if config_path(root, n).is_file()]


def highest_in_use(root: Path, series: str):
    high = 0
    for p, markdown in id_home_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        nums = _id_numbers(_visible_text(text) if markdown else text, series)
        if nums:
            high = max(high, max(nums))
    return high


def load_ids(root: Path):
    p = config_path(root, IDS_NAME)
    if not p.is_file():
        return {"version": 1, "series": {}}
    data = load_json(p)
    if data.get("version") != 1 or not isinstance(data.get("series"), dict):
        raise GovernanceError("ids.json needs version=1 and a series object")
    return data


def _series_name(series):
    series = str(series or "").strip().upper()
    if not SERIES_RE.match(series):
        raise GovernanceError("a series is one to four capital letters, for example D")
    return series


def take_id(root: Path, series: str, actor=None, note="", record=True):
    """The next free ID of a series: above the counter and above every number already written in the memory files."""
    series = _series_name(series)
    if not memory_dir(root).is_dir():
        raise GovernanceError("no .memory/ directory here; run init first")
    with FileLock(config_path(root, "ids.lock")):
        data = load_ids(root)
        cfg = data["series"].get(series)
        if cfg is None:
            cfg = data["series"][series] = dict(DEFAULT_SERIES.get(series, {"width": 3, "what": ""}))
        number = max(int(cfg.get("next", 1)), highest_in_use(root, series) + 1)
        cfg["next"] = number + 1
        atomic_json(config_path(root, IDS_NAME), data)
    ident = f"{series}-{number:0{int(cfg.get('width', 3))}d}"
    if record:
        record_event(root, "id.take", actor=actor, ref=ident, summary=note)
    return ident


def id_duplicates(root: Path):
    """IDs defined twice where each ID has one definition. Receipts written by 1.4.0 to 1.4.2 are listed by id audit, not here."""
    out = []

    def dup(items, where):
        for ident, n in sorted(Counter(i for i in items if i).items()):
            if n > 1:
                out.append(f"duplicate {ident}: defined {n} times in {where}")

    for name, key in (("contradictions.json", "contradictions"), ("premises.json", "premises")):
        p = config_path(root, name)
        if not p.is_file():
            continue
        try:
            rows = json.loads(p.read_text(encoding="utf-8")).get(key) or []
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        dup([r.get("id") for r in rows if isinstance(r, dict)], f".memory/{name}")
    failures = root / "FAILURES.md"
    if failures.is_file():
        heads = _headings(read_text(failures).splitlines(keepends=True))
        dup([t.split(" ")[0] for _, level, t in heads if level == 3 and re.match(r"^F-\d+", t)], "FAILURES.md")
    return out


def unused_ids(root: Path):
    """IDs taken more than a week ago that no memory file mentions."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=UNUSED_ID_DAYS)
    taken = [(r["ref"], _receipt_time(r.get("ts"))) for r in read_events(root)
             if r.get("event") == "id.take" and r.get("ref")]
    old = [ref for ref, ts in taken if ts and ts < cutoff]
    if not old:
        return []
    blob = ""
    for p, _ in id_home_files(root):
        try:
            blob += p.read_text(encoding="utf-8", errors="replace") + "\n"
        except OSError:
            continue
    return [ref for ref in old if ref not in blob]


def cmd_id(args):
    root = Path(args.target).resolve()
    if args.action == "take":
        if not args.series:
            raise GovernanceError("id take needs a series, for example: id take D")
        ident = take_id(root, args.series, actor=args.actor, note=args.note or "")
        _emit({"id": ident}, args.json, [ident])
        return 0
    data = load_ids(root)
    if args.action == "list":
        rows = []
        for s in list(OrderedDict.fromkeys(list(DEFAULT_SERIES) + sorted(data["series"]))):
            cfg = data["series"].get(s) or DEFAULT_SERIES.get(s, {})
            high = highest_in_use(root, s)
            nxt = max(int(cfg.get("next", 1)), high + 1)
            rows.append(OrderedDict(series=s, what=cfg.get("what", ""), next=f"{s}-{nxt:0{int(cfg.get('width', 3))}d}",
                                    highest_in_files=high))
        _emit(rows, args.json, [f"{r['series']}  next {r['next']}  {r['what']}".rstrip() for r in rows])
        return 0
    dupes = id_duplicates(root)
    repeated = Counter(r.get("receipt") for r in read_receipts(root) if r.get("type") == "impact")
    legacy = sorted(k for k, n in repeated.items() if k and n > 1)
    unused = unused_ids(root)
    lines = [f"DUPLICATE {d}" for d in dupes]
    if legacy:
        lines.append(f"NOTE {len(legacy)} receipt ID(s) were issued more than once by 1.4.0 to 1.4.2 and stay as they are: "
                     + ", ".join(legacy[:5]) + "; new receipts start above them")
    if unused:
        lines.append(f"NOTE taken more than {UNUSED_ID_DAYS} days ago and not written anywhere: " + ", ".join(unused[:10]))
    lines.append("IDS OK" if not dupes else f"IDS FINDINGS {len(dupes)}")
    _emit(OrderedDict(duplicates=dupes, repeated_receipts=legacy, unused=unused), args.json, lines)
    return 1 if dupes else 0


# ---------------------------------------------------------------------------
# 1.4.3 · write: one checked way to add a line to a memory file
# ---------------------------------------------------------------------------

REDACT_RULES = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "[REDACTED_KEY]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{10,}"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(token|apikey|api_key|secret|password)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[REDACTED_IP]"),
    (re.compile(r"/(?:Users|home)/[A-Za-z0-9_\-]+/"), "~/"),
]
DATED_LINE = re.compile(r"^- \[(\d{4}-\d{2}-\d{2})\]\s+(.*)$")
LOG_HEADER = "# LOG.md — dated log\n\n> Append-only. Newest entry on top. One line per thing that happened.\n\n"
PROPOSALS_HEADER = ("# PROPOSALS.md — trust-building queue\n\n> New durable facts wait here until a human (or an approving tool) moves them\n"
                    "> into MEMORY.md. One dated, sourced line per proposal.\n\n")
FAILURE_FIELDS = (("trigger", "Trigger"), ("observed", "Observed"), ("expected", "Expected"),
                  ("root_cause", "Root cause"), ("fix", "Fix"), ("check", "Regression check"))
INDEX_HEAD_WORDS = ("file", "path", "文件", "路径")
WRITE_FACES = ("log", "now", "close", "propose", "promote", "reject", "fact", "index", "capability", "map", "failure")


def redact(text):
    text = str(text)
    for rx, repl in REDACT_RULES:
        text = rx.sub(repl, text)
    return text


def one_line(text, limit=500):
    return " ".join(str(text or "").split())[:limit]


def local_today(value=None):
    if value:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            raise GovernanceError(f"--date needs YYYY-MM-DD, got {value!r}")
    tz = os.environ.get(TZ_ENV)
    try:
        now = datetime.now(timezone(timedelta(hours=float(tz)))) if tz else datetime.now()
    except ValueError:
        raise GovernanceError(f"${TZ_ENV} needs a number of hours, got {tz!r}")
    return now.strftime("%Y-%m-%d")


class Edit:
    """A pending change to one text file. It keeps every existing line as it is and can prove it."""

    def __init__(self, root: Path, rel: str, header=""):
        self.root, self.rel = root, norm_path(rel)
        self.path = root / self.rel
        self.existed = self.path.is_file()
        self.old_text = read_text(self.path) if self.existed else header
        self.nl = "\r\n" if "\r\n" in self.old_text else "\n"
        self.old = self.old_text.splitlines(keepends=True)
        self.lines = list(self.old)
        self.origin = list(range(len(self.old)))   # index in the old file, or None for a new line
        self.gone = []                               # old indices that leave
        self.added, self.removed = [], []            # what the report shows

    def add(self, pos, texts, show=True):
        """Insert whole lines at pos. Returns the 1-based number of the first one."""
        if pos > 0 and not self.lines[pos - 1].endswith(("\n", "\r")):
            self.lines[pos - 1] += self.nl          # the file had no final newline
        self.lines[pos:pos] = [t + self.nl for t in texts]
        self.origin[pos:pos] = [None] * len(texts)
        if show:
            self.added += [{"line": pos + 1 + i, "text": t} for i, t in enumerate(texts) if t]
        return pos + 1

    def remove(self, idx):
        self.removed.append(self.lines[idx].rstrip("\r\n"))
        if self.origin[idx] is not None:
            self.gone.append(self.origin[idx])
        del self.lines[idx]
        del self.origin[idx]

    def text(self):
        return "".join(self.lines)

    def changed(self):
        return self.text() != self.old_text or not self.existed

    def check(self):
        """Every old line that was not removed is still there, byte for byte and in order."""
        gone = set(self.gone)
        kept_old = "".join(ln for i, ln in enumerate(self.old) if i not in gone)
        kept_new = "".join(ln for ln, o in zip(self.lines, self.origin) if o is not None)
        if kept_new != kept_old and kept_new != kept_old + self.nl:   # the one allowance: a missing final newline
            raise GovernanceError(f"self-check failed for {self.rel}: the edit would change existing lines; nothing was written")

    def report(self):
        return OrderedDict(file=self.rel, created=not self.existed, added=self.added, removed=self.removed)


def _headings(lines):
    """(index, level, title) of every Markdown heading outside comments and fenced code."""
    hidden = _hidden_lines(lines)
    out = []
    for i, ln in enumerate(lines):
        if i in hidden:
            continue
        m = _HEADING.match(ln.rstrip("\r\n"))
        if m:
            out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def _section_span(lines, head, level):
    return next((j for j, lvl, _ in _headings(lines) if j > head and lvl <= level), len(lines))


def _find_section(lines, title, rel):
    """(heading index, end index) of the one section the title names. Anything else is a clear error, not a guess."""
    want = str(title).strip().lstrip("#").strip().lower()
    heads = _headings(lines)
    cand = [h for h in heads if h[2].lower() == want] or [h for h in heads if want and want in h[2].lower()]
    if len(cand) != 1:
        names = ", ".join(f'"{h[2]}"' for h in heads if h[1] >= 2) or "none"
        why = "no heading matches" if not cand else f"{len(cand)} headings match"
        raise GovernanceError(f"{rel}: {why} \"{title}\"; headings here: {names}")
    return cand[0][0], _section_span(lines, cand[0][0], cand[0][1])


def _content_start(lines, head, end, skip_comment=True):
    """Where a new entry goes under a heading: after blank lines and one leading comment block, above older entries."""
    pos = head + 1
    while pos < end and not lines[pos].strip():
        pos += 1
    if skip_comment and pos < end and lines[pos].lstrip().startswith("<!--"):
        while pos < end and "-->" not in lines[pos]:
            pos += 1
        pos = min(pos + 1, end)
    return pos


def _add_entry(ed: Edit, pos, texts):
    """Insert entry lines; keep a blank line between them and a heading that follows directly."""
    block = list(texts)
    nxt = ed.lines[pos] if pos < len(ed.lines) else ""
    if nxt.strip() and _HEADING.match(nxt.rstrip("\r\n")):
        block.append("")
    if pos > 0 and ed.lines[pos - 1].strip() and _HEADING.match(block[0]):
        block.insert(0, "")
    first = ed.add(pos, block, show=False)
    offset = 1 if block[0] == "" else 0
    ed.added += [{"line": first + offset + i, "text": t} for i, t in enumerate(texts) if t]
    return first + offset


def _tables(lines):
    """Markdown tables outside fenced code: header, rows, end, and the `## ` area above each."""
    out, area, i, hidden = [], "", 0, _hidden_lines(lines)
    while i < len(lines):
        ln = lines[i]
        if i in hidden:
            i += 1
            continue
        if ln.startswith("## "):
            area = ln[3:].strip()
        head = _cells(ln)
        nxt = _cells(lines[i + 1]) if i + 1 < len(lines) else None
        if head and nxt and _is_sep(nxt):
            j, rows = i + 2, []
            while j < len(lines) and _cells(lines[j]) is not None:
                rows.append(j)
                j += 1
            out.append({"head": i, "cells": head, "rows": rows, "end": j, "area": area})
            i = j
            continue
        i += 1
    return out


def _row(cells):
    return "| " + " | ".join(cells) + " |"


def _cell(value, what):
    value = redact(one_line(value, 400))
    if "|" in value:
        raise GovernanceError(f"{what} cannot contain a | character: it would break the table")
    return value


def _log_edit(root: Path, line: str, day: str, rel=LOG_NAME):
    """Put one line on top of its month in a newest-first log (at the end of its month in an oldest-first one)."""
    ed = Edit(root, rel, header=LOG_HEADER)
    month = day[:7]
    months = [(i, t[:7]) for i, level, t in _headings(ed.lines) if level == 2 and re.match(r"^\d{4}-\d{2}(?![0-9])", t)]
    order = toc_order(ed.old_text)
    if order is None:
        keys = [k for _, k in months]
        order = "asc" if len(set(keys)) > 1 and keys == sorted(keys) else "desc"
    found = next((i for i, k in months if k == month), None)
    if found is not None:
        end = _section_span(ed.lines, found, 2)
        if order == "desc":
            pos = _content_start(ed.lines, found, end)
        else:
            pos = end
            while pos > found + 1 and not ed.lines[pos - 1].strip():
                pos -= 1
        _add_entry(ed, pos, [line])
        return ed
    if any(p.stem == month for p in volume_files(root / rel)):
        raise GovernanceError(f"{month} is a closed volume of {rel}; date the entry in a month that is still in {rel}")
    if order == "desc":
        pos = next((i for i, k in months if k < month), len(ed.lines))
    else:
        pos = next((i for i, k in months if k > month), len(ed.lines))
    block = [f"## {month}", "", line] + ([""] if pos < len(ed.lines) else [])
    if pos > 0 and ed.lines[pos - 1].strip():
        block.insert(0, "")
    first = ed.add(pos, block, show=False)
    ed.added.append({"line": first + block.index(line), "text": line})
    return ed


def _section_edit(root: Path, rel: str, line: str, section, default_section=None, create_section=False):
    """Add one dated line on top of a section of NOW.md, MEMORY.md, or a topic file."""
    ed = Edit(root, rel)
    if not ed.existed:
        raise GovernanceError(f"{rel} does not exist; install the memory files first (see PROMPT.md)")
    twos = [h for h in _headings(ed.lines) if h[1] == 2]
    if section:
        head, end = _find_section(ed.lines, section, rel)
    elif default_section and any(h[2].lower() == default_section.lower() for h in twos):
        head, end = _find_section(ed.lines, default_section, rel)
    elif default_section and create_section:
        block = ([""] if ed.lines and ed.lines[-1].strip() else []) + [f"## {default_section}", "", line]
        first = ed.add(len(ed.lines), block, show=False)
        ed.added.append({"line": first + block.index(line), "text": line})
        return ed
    elif len(twos) == 1:
        head, end = twos[0][0], len(ed.lines)
    elif not twos:
        _add_entry(ed, len(ed.lines), [line])
        return ed
    else:
        raise GovernanceError(f"{rel} has {len(twos)} sections; name one with --section: " + ", ".join(f'"{t}"' for _, _, t in twos))
    body = "".join(ed.lines[head:end])
    if STUB_MARK in body:
        moved = re.search(r"Moved to `([^`]+)`", body)
        where = moved.group(1) if moved else "a topic file"
        raise GovernanceError(f"that section of {rel} moved to {where}; write there with --file {where}")
    _add_entry(ed, _content_start(ed.lines, head, end), [line])
    return ed


def _dated_texts(root: Path, rel: str):
    path = root / rel
    if not path.is_file():
        return []
    lines = read_text(path).splitlines(keepends=True)
    hidden = _hidden_lines(lines)
    return [m.group(2) for i, ln in enumerate(lines) if i not in hidden for m in [DATED_LINE.match(ln.strip())] if m]


def _one_match(ed: Edit, lo, hi, match, what):
    """The index of the single entry line in [lo, hi) that contains the words; anything else is an error that lists the candidates."""
    hidden = _hidden_lines(ed.lines)
    entries = [i for i in range(lo, hi) if i not in hidden and ed.lines[i].lstrip().startswith("- ")]
    hits = [i for i in entries if match in ed.lines[i].lower()]
    if len(hits) != 1:
        listed = "; ".join(ed.lines[i].strip() for i in entries[:8]) or "nothing"
        raise GovernanceError(f"{'no' if not hits else len(hits)} line(s) {what} match \"{match}\"; there now: {listed}")
    return hits[0]


def _build(root: Path, face: str, a, day: str, ident):
    """The edits one face makes. Nothing is written here."""
    tag = f"{ident} · " if ident else ""
    text = redact(one_line(a.get("text")))
    if face == "log":
        if not text:
            raise GovernanceError("log needs the text of what happened")
        source = redact(one_line(a.get("source"), 200))
        return [_log_edit(root, f"- [{day}] {tag}{text}" + (f" — {source}" if source else ""), day)]
    if face == "now":
        pointer = redact(one_line(a.get("pointer"), 200))
        if not text:
            raise GovernanceError("now needs the item that moved")
        if not pointer:
            raise GovernanceError("now needs --pointer: where the detail lives (a path or a link)")
        return [_section_edit(root, "NOW.md", f"- [{day}] {tag}{text}; details: {pointer}", a.get("section"),
                              default_section="In flight", create_section=True)]
    if face == "close":
        match = one_line(a.get("match"), 200).lower()
        if not match or not text:
            raise GovernanceError("close needs --match (words from the NOW.md line) and the text of what happened")
        now = Edit(root, "NOW.md")
        if not now.existed:
            raise GovernanceError("NOW.md does not exist; install the memory files first (see PROMPT.md)")
        head, end = _find_section(now.lines, a.get("section") or "In flight", "NOW.md")
        now.remove(_one_match(now, head + 1, end, match, "in flight"))
        twos = [h for h in _headings(now.lines) if h[1] == 2 and h[2].lower().startswith("recently")]
        if twos:
            h2 = twos[0][0]
            _add_entry(now, _content_start(now.lines, h2, _section_span(now.lines, h2, 2)), [f"- [{day}] {text} → LOG.md"])
        pointer = redact(one_line(a.get("pointer"), 200))
        return [_log_edit(root, f"- [{day}] {tag}{text}" + (f" — {pointer}" if pointer else ""), day), now]
    if face == "propose":
        source = redact(one_line(a.get("source"), 200))
        if not text:
            raise GovernanceError("propose needs the fact")
        if not source:
            raise GovernanceError("propose needs --source: where the fact comes from (a path, a commit, the user's words)")
        for rel in (MEMORY_NAME, "PROPOSALS.md"):
            if any(text.lower() == t.split(" — source:")[0].strip().lower() for t in _dated_texts(root, rel)):
                return f"already in {rel}: nothing added"
        origin = re.sub(r"[^A-Za-z0-9_.:-]", "", str(a.get("origin") or ""))[:64]
        ed = Edit(root, "PROPOSALS.md", header=PROPOSALS_HEADER)
        ed.add(len(ed.lines), [f"- [{day}] {text} — source: {source} (proposed" + (f" · from {origin}" if origin else "") + ")"])
        return [ed]
    if face in ("promote", "reject"):
        match = one_line(a.get("match"), 200).lower()
        if not match:
            raise GovernanceError(f"{face} needs --match: words from the proposal")
        queue = Edit(root, "PROPOSALS.md")
        if not queue.existed:
            raise GovernanceError("PROPOSALS.md does not exist: nothing is waiting")
        idx = _one_match(queue, 0, len(queue.lines), match, "in PROPOSALS.md")
        m = DATED_LINE.match(queue.lines[idx].strip())
        if not m:
            raise GovernanceError("that line is not a dated proposal; edit PROPOSALS.md by hand")
        fact = re.sub(r"\s*\(proposed[^)]*\)\s*$", "", m.group(2))
        queue.remove(idx)
        if face == "promote":
            return [_section_edit(root, a.get("file") or MEMORY_NAME, f"- [{m.group(1)}] {fact}", a.get("section")), queue]
        reason = redact(one_line(a.get("reason"), 200))
        return [_log_edit(root, f"- [{day}] Rejected proposal: {fact}" + (f" — {reason}" if reason else ""), day), queue]
    if face == "fact":
        source = redact(one_line(a.get("source"), 200))
        if not text:
            raise GovernanceError("fact needs the fact")
        if not source:
            raise GovernanceError("fact needs --source: where the fact comes from (a path, a commit, the user's words)")
        rel = a.get("file") or MEMORY_NAME
        if any(text.lower() == t.split(" — source:")[0].strip().lower() for t in _dated_texts(root, rel)):
            return f"already in {rel}: nothing added"
        return [_section_edit(root, rel, f"- [{day}] {tag}{text} — source: {source}", a.get("section"))]
    if face == "index":
        rel = norm_path(one_line(a.get("path"), 300))
        note = _cell(a.get("text"), "the note")
        if not rel or not note:
            raise GovernanceError("index needs --path and a few words on what the file is")
        for name, body in index_texts(root):
            for n, ln in enumerate(body.splitlines(keepends=True)):
                s = ln.strip()
                if not (s.startswith("|") or s.startswith("- ")) or _is_sep(_cells(s) or []):
                    continue
                found = cell_paths(s.split("|")[1] if s.startswith("|") else s)
                if not found or norm_path(found[0]) != rel:
                    continue
                if not a.get("update"):
                    raise GovernanceError(f"{rel} is already registered at {name}:{n + 1}; pass --update to change its note")
                ed = Edit(root, name)
                cells = _cells(ed.lines[n])
                if cells is None or len(cells) < 2:
                    raise GovernanceError(f"{name}:{n + 1} is not a table row; edit that line by hand")
                cells[1] = note
                ed.remove(n)
                ed.add(n, [_row(cells)])
                return [ed]
        ed = Edit(root, INDEX_NAME)
        if not ed.existed:
            raise GovernanceError("INDEX.md does not exist; install the memory files first (see PROMPT.md)")
        tables = [t for t in _tables(ed.lines) if any(w in t["cells"][0].lower() for w in INDEX_HEAD_WORDS)] or _tables(ed.lines)
        if a.get("section"):
            want = str(a["section"]).strip().lstrip("#").strip().lower()
            tables = [t for t in tables if want in t["area"].lower()]
            if not tables:
                raise GovernanceError(f"INDEX.md has no table under a heading that matches \"{a['section']}\"")
        if tables:
            top = rel.split("/", 1)[0] if "/" in rel else ""

            def same_top(t):
                paths = [p for i in t["rows"] for p in cell_paths((_cells(ed.lines[i]) or [""])[0])]
                return sum(1 for p in paths if (p.split("/", 1)[0] if "/" in p else "") == top)

            table = max(tables, key=same_top)
            ed.add(table["end"], [_row([f"`{rel}`", note] + [""] * max(0, len(table["cells"]) - 2))])
        else:
            hidden = _hidden_lines(ed.lines)
            rows = [i for i, ln in enumerate(ed.lines) if i not in hidden and ln.startswith("- ") and cell_paths(ln[2:].split("|")[0])]
            ed.add(rows[-1] + 1 if rows else len(ed.lines), [f"- `{rel}` | {note}"])
        return [ed]
    if face in ("capability", "map"):
        rel, columns, first = (CAPS_NAME, CAP_COLUMNS, "name") if face == "capability" else (MAP_NAME, MAP_COLUMNS, "component")
        name = _cell(a.get("text"), "the name")
        if not name:
            raise GovernanceError(f"{face} needs a name")
        if face == "capability":
            entry = norm_path(_cell(a.get("entry"), "--entry"))
            if not entry:
                raise GovernanceError("capability needs --entry: the path to start from")
            values = {"name": f"`{name}`", "form": _cell(a.get("form"), "--form"), "entry": f"`{entry}`",
                      "triggers": _cell(a.get("triggers"), "--triggers"), "state": _cell(a.get("state"), "--state") or "incubating",
                      "call": _cell(a.get("call"), "--call")}
            for row in load_caps(root) or []:
                if clean(row["name"]).lower() == name.lower() or entry in cell_paths(row["entry"]):
                    raise GovernanceError(f"{name} is already registered at {CAPS_NAME}:{row['line']}")
            required = ("name", "entry")
        else:
            keywords_cell = _cell(a.get("keywords"), "--keywords")
            if not keywords_cell:
                raise GovernanceError("map needs --keywords: the words that should lead to this component")
            details = norm_path(_cell(a.get("details"), "--details"))
            values = {"component": f"`{name}`", "job": _cell(a.get("job"), "--job"), "keywords": keywords_cell,
                      "details": f"`{details}`" if details else ""}
            for row in load_map(root) or []:
                if clean(row["component"]).lower() == name.lower():
                    raise GovernanceError(f"{name} is already on the map at {MAP_NAME}:{row['line']}")
            required = ("component", "keywords")
        ed = Edit(root, rel)
        if not ed.existed:
            raise GovernanceError(f"{rel} does not exist; copy templates/{rel} from wallaby-agent-rules first")
        found = []
        for t in _tables(ed.lines):
            keys = {}
            for idx, cell in enumerate(t["cells"]):
                low = cell.lower()
                for key, aliases in columns:
                    if key not in keys and any(alias in low for alias in aliases):
                        keys[key] = idx
                        break
            if all(k in keys for k in required):
                t["keys"] = keys
                found.append(t)
        if a.get("area"):
            want = str(a["area"]).strip().lstrip("#").strip().lower()
            found = [t for t in found if want in t["area"].lower()]
        if not found:
            raise GovernanceError(f"{rel} has no table with the expected columns" + (f" under \"{a['area']}\"" if a.get("area") else ""))
        if len(found) > 1:
            raise GovernanceError(f"{rel} has {len(found)} such tables; name one with --area: " + ", ".join(f'"{t["area"]}"' for t in found))
        table = found[0]
        cells = [""] * len(table["cells"])
        for key, value in values.items():
            if key in table["keys"]:
                cells[table["keys"][key]] = value
        pos = table["end"]
        for i in table["rows"]:
            existing = _cells(ed.lines[i]) or []
            k = table["keys"][first]
            if k < len(existing) and _placeholder(existing[k]):
                pos = i   # keep the template's placeholder row last
                break
        ed.add(pos, [_row(cells)])
        return [ed]
    if face == "failure":
        kind = one_line(a.get("kind"), 40) or "missing"
        vals = {k: redact(one_line(a.get(k), 600)) for k, _ in FAILURE_FIELDS}
        if not (vals["observed"] and vals["expected"]):
            raise GovernanceError("failure needs --observed (what happened) and --expected (what should have happened)")
        block = [f"### {ident} · {day} · {kind}"] + [f"- **{label}**: {vals[k]}" for k, label in FAILURE_FIELDS if vals[k]]
        block += ["- **Status**: open", ""]
        ed = Edit(root, "FAILURES.md")
        if not ed.existed:
            raise GovernanceError("FAILURES.md does not exist; copy templates/FAILURES.md from wallaby-agent-rules first")
        heads = [h for h in _headings(ed.lines) if h[2].lower() == "regression entries"]
        pos = _content_start(ed.lines, heads[0][0], _section_span(ed.lines, heads[0][0], heads[0][1]), skip_comment=False) \
            if heads else len(ed.lines)
        if pos > 0 and ed.lines[pos - 1].strip():
            block.insert(0, "")
        first = ed.add(pos, block, show=False)
        ed.added.append({"line": first + (1 if block[0] == "" else 0), "text": block[1] if block[0] == "" else block[0]})
        return [ed]
    raise GovernanceError(f"unknown write face {face!r}; choose from {', '.join(WRITE_FACES)}")


def write_entry(root: Path, face: str, a, actor=None, dry_run=False):
    """Check, write, and log one entry. Either every file of the entry is written or none is."""
    day = local_today(a.get("date"))
    series = a.get("take") or ("F" if face == "failure" else None)
    result = OrderedDict(face=face, id=None, dry_run=bool(dry_run), files=[], events=[])
    lock = FileLock(config_path(root, "write.lock")) if memory_dir(root).is_dir() else None
    if lock:
        lock.__enter__()
    try:
        placeholder = f"{_series_name(series)}-?" if series else None
        edits = _build(root, face, a, day, placeholder)          # every error surfaces before an ID is taken
        if isinstance(edits, str):
            result["skipped"] = edits
            return result
        if series and not dry_run:
            result["id"] = take_id(root, series, actor=actor, record=False)
            edits = _build(root, face, a, day, result["id"])
        elif series:
            result["id"] = placeholder
        for ed in edits:
            ed.check()
        result["files"] = [ed.report() for ed in edits]
        if dry_run:
            return result
        done = []
        try:
            for ed in edits:
                write_text_atomic(ed.path, ed.text())
                done.append(ed)
        except OSError as e:
            for ed in done:   # put back what this entry already wrote
                if ed.existed:
                    write_text_atomic(ed.path, ed.old_text)
                else:
                    ed.path.unlink()
            raise GovernanceError(f"write failed and was undone: {e}")
    finally:
        if lock:
            lock.__exit__(None, None, None)
    for ed in edits:
        summary = ed.added[0]["text"] if ed.added else "removed: " + (ed.removed[0] if ed.removed else "")
        result["events"] += [r["seq"] for r in record_files(root, f"write.{face}", [ed.rel], actor=actor, ref=result["id"], summary=summary)]
    if not memory_dir(root).is_dir():
        result["note"] = "event log off: this project has no .memory/ directory (init turns it on)"
    elif face in ("fact", "promote"):
        memory = root / MEMORY_NAME
        if memory.is_file():
            body = read_text(memory)
            dated = len(_dated_texts(root, MEMORY_NAME))
            if dated > MEMORY_SOFT_LINES or est_tokens(body) > MEMORY_MAX_TOKENS:
                result["note"] = (f"MEMORY.md is past its soft wall ({dated} dated lines, about {est_tokens(body)} tokens); "
                                  "at the next closeout, move facts idle 30+ days to LOG.md")
    return result


def write_lines(result):
    verb = "WOULD WRITE" if result["dry_run"] else "WROTE"
    out = []
    if result.get("skipped"):
        return [f"SKIPPED {result['skipped']}"]
    for f in result["files"]:
        for row in f["added"]:
            out.append(f"{verb} {f['file']}:{row['line']}  {row['text']}")
        for text in f["removed"]:
            out.append(f"{'WOULD REMOVE' if result['dry_run'] else 'REMOVED'} {f['file']}  {text}")
    if result.get("id"):
        out.append(f"ID {result['id']}")
    if result["events"]:
        out.append("EVENT seq=" + ",".join(str(s) for s in result["events"]))
    if result.get("note"):
        out.append(f"NOTE {result['note']}")
    return out


def cmd_write(args):
    root = Path(args.target).resolve()
    if args.face == "batch":
        try:
            raw = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
        except OSError as e:
            raise GovernanceError(f"cannot read {args.file}: {e}")
        results = []
        for n, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                face = item.pop("face")
            except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
                raise GovernanceError(f"batch line {n} needs a JSON object with a \"face\"; {len(results)} entry(ies) before it were written")
            try:
                results.append(write_entry(root, face, item, actor=args.actor, dry_run=args.dry_run))
            except GovernanceError as e:
                raise GovernanceError(f"batch line {n} ({face}): {e}; {len(results)} entry(ies) before it were written")
        _emit(results, args.json, [ln for r in results for ln in write_lines(r)] or ["Nothing to write."])
        return 0
    keys = ("text", "source", "pointer", "match", "reason", "section", "file", "date", "take", "origin", "path", "update",
            "entry", "form", "triggers", "state", "call", "job", "keywords", "details", "area", "kind", "trigger",
            "observed", "expected", "root_cause", "fix", "check")
    a = {k: getattr(args, k) for k in keys if getattr(args, k, None) not in (None, "", False)}
    if not a.get("text") and getattr(args, "words", None):
        a["text"] = " ".join(args.words)
    result = write_entry(root, args.face, a, actor=args.actor, dry_run=args.dry_run)
    _emit(result, args.json, write_lines(result))
    return 0


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


# ---------------------------------------------------------------------------
# 1.4.4 · harvest: the user's own words, gathered from what was already written down
# ---------------------------------------------------------------------------
# Preferences should not depend on one model noticing them mid-session. Any agent that records the
# user's exact words — `source: user: "..."` on a log line, a FAILURES.md entry — leaves material
# this command can read later. It lists candidates only; nothing is written. An agent turns the
# good ones into `write propose` lines, and the person approves each with `write promote` or
# `write reject`. A pick between options the agent offered is an approval, not the user's own
# view, so short approvals and replies marked `(answering "...")` are left out by default.

HARVEST_SPEAKERS = ("user", "the user", "用户")
HARVEST_SOURCES = ("LOG.md", "FAILURES.md")
HARVEST_CURSOR = "harvest_cursor.json"
_H_OPEN, _H_CLOSE = "\"“「", "\"”」"
_H_APPROVE = re.compile(
    r"^(ok(ay)?|yes|yep|yeah|y|sure|fine|go|go ahead|do it|ship it|lgtm|sounds good|approved?|agreed?|proceed|"
    r"continue|option\s*\w|\w|\d+|好|好的|行|可以|做吧|开工|同意|没问题|继续|就这样)[\s.!。！,，]*$", re.I)
_H_ANSWER = re.compile(r"\s*[（(]\s*(?:answering|answered|in reply to|答)\s*[:：]?\s*[\"“「]([^\"”」\n]{0,300})[\"”」]\s*[)）]", re.I)
_H_CHAIN = re.compile(r"([^\"“「」”\n。]{0,8}?)[\"“「]([^\"”」\n]{2,400})[\"”」]")
_H_CHAIN_STOP = re.compile(r"answer|asked|question|suggest|propos|答|问|建议|提议", re.I)
_H_CJK = re.compile(r"[㐀-鿿]")
HARVEST_SIGNALS = {
    "rule": r"\b(always|never|every time|from now on|by default|in general)\b|以后|一律|每次|永远|默认|原则|一定要|必须|不能|别再|不要再",
    "correction": r"\b(wrong|not what|that's not|stop|don't|instead|too (much|many|slow|long))\b|不对|错了|不是这样|重做|不够|没必要|多余|不该",
    "standard": r"\b(should|must|need to|prefer|rather|keep it|make sure)\b|应该|需要|希望|尽量|优先|简单|清楚|成本|速度",
}


def _h_norm(text):
    return re.sub(r"\s+", "", str(text or "")).lower()


def _h_quotes(text, speakers):
    """(quote, end) for each quote attributed to a speaker, plus quotes chained right after it
    ('user: "A", then "B"'). A chained quote whose connector mentions an answer or a suggestion
    belongs to someone else and stops the chain."""
    names = "|".join(re.escape(s) for s in sorted(speakers, key=len, reverse=True))
    head = re.compile(rf"(?<![A-Za-z])(?:{names})(?![A-Za-z])[^{_H_OPEN}\n]{{0,30}}?[{_H_OPEN}]([^{_H_CLOSE}\n]{{2,400}})[{_H_CLOSE}]", re.I)
    for m in head.finditer(text):
        yield m.group(1), m.end()
        pos = m.end()
        while True:
            c = _H_CHAIN.match(text, pos)
            if not c or _H_CHAIN_STOP.search(c.group(1)):
                break
            yield c.group(2), c.end()
            pos = c.end()


def _h_is_approval(quote, after):
    q = quote.strip()
    short = len(q) <= 12 if _H_CJK.search(q) else len(q.split()) <= 3
    return bool(short or _H_APPROVE.match(q) or _H_ANSWER.match(after))


def harvest(root: Path, since=None, speakers=None, sources=None, include_approvals=False, show_all=False):
    root = Path(root)
    speakers = tuple(speakers or HARVEST_SPEAKERS)
    cursor = config_path(root, HARVEST_CURSOR)
    if since is None and cursor.is_file():
        since = (load_json(cursor) or {}).get("since")
    files = []
    for rel in sources or HARVEST_SOURCES:
        path = root / rel
        if path.is_file():
            files += [path] + volume_files(path)
    found = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        lines = read_text(path).splitlines()
        hidden = _hidden_lines([ln + "\n" for ln in lines])
        month = ""
        for n, ln in enumerate(lines, 1):
            if n - 1 in hidden:
                continue
            mh = re.match(r"^#{1,4}\s.*?(\d{4}-\d{2})(-\d{2})?", ln)
            if mh:
                month = mh.group(1) + (mh.group(2) or "")
            md = DATED_LINE.match(ln.strip())
            if md and md.group(2).startswith("Rejected proposal:"):
                continue                                  # the review trail, not new words
            day = md.group(1) if md else month
            for q, end in _h_quotes(ln, speakers):
                q = q.strip()
                key = _h_norm(q)
                if not key or key in found or (since and day and day < since):
                    continue
                after = ln[end:end + 320]
                ans = _H_ANSWER.match(after)
                found[key] = {"quote": q, "date": day, "file": rel, "line": n,
                              "approval": _h_is_approval(q, after), "answering": ans.group(1) if ans else ""}
    known_texts = []
    for rel in ("PROPOSALS.md", MEMORY_NAME):
        known_texts += _dated_texts(root, rel)
    topic_dir = root / "MEMORY"
    if topic_dir.is_dir():
        for path in sorted(topic_dir.glob("*.md")):
            known_texts += _dated_texts(root, path.relative_to(root).as_posix())
    for path in [root / LOG_NAME] + volume_files(root / LOG_NAME):
        if path.is_file():
            known_texts += [t for t in _dated_texts(root, path.relative_to(root).as_posix()) if t.startswith("Rejected proposal:")]
    known_blob = "\n".join(_h_norm(t) for t in known_texts)
    rows, approvals, known = [], 0, 0
    for key, r in found.items():
        if key[:40] in known_blob:
            known += 1
            continue
        if r["approval"]:
            approvals += 1
            if not include_approvals:
                continue
        signals = [k for k, rx in HARVEST_SIGNALS.items() if re.search(rx, r["quote"], re.I)]
        score = 2 * len(signals) + (1 if 15 <= len(r["quote"]) <= 200 else 0)
        if show_all or score >= 3 or r["approval"]:
            rows.append({**r, "signals": signals, "score": score})
    rows.sort(key=lambda r: (-r["score"], r["date"] or "", r["file"], r["line"]))
    return {"version": 1, "since": since, "speakers": list(speakers), "sources": [f.relative_to(root).as_posix() for f in files],
            "total": len(found), "approvals": approvals, "known": known, "candidates": rows}


def harvest_advance(root: Path, day=None):
    day = local_today(day)
    path = config_path(Path(root), HARVEST_CURSOR)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps({"since": day}) + "\n")
    return day


def cmd_harvest(args):
    root = Path(args.target).resolve()
    res = harvest(root, args.since, args.speaker, args.source, args.include_approvals, args.all)
    if args.advance:
        res["advanced_to"] = harvest_advance(root, args.today)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
        return 0
    print(f"since {res['since'] or 'the beginning'}: {res['total']} quote(s) from {', '.join(res['speakers'])}; "
          f"{res['approvals']} approval(s) or pick(s); {res['known']} already proposed, kept, or rejected; "
          f"{len(res['candidates'])} candidate(s)")
    for r in res["candidates"]:
        tag = " [approval]" if r["approval"] else ""
        print(f"  {r['file']}:{r['line']} [{r['date'] or '?'}] {'/'.join(r['signals']) or '-'}{tag}  {r['quote'][:160]}")
        if r["answering"]:
            print(f"      answering: {r['answering'][:160]}")
    if res["candidates"]:
        print("next: write propose --text \"<the rule, in a sentence>\" --source 'user: \"<their words>\" (<file> <date>)' --origin harvest;"
              " the person approves each with write promote or write reject")
    if res.get("advanced_to"):
        print(f"cursor moved to {res['advanced_to']}")
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
    verify = sub.add_parser("verify", help="close a receipt after the change: old terms, premises, registrations, surfaces")
    verify.add_argument("--receipt", help="defaults to the one pending receipt")
    verify.add_argument("--allow", action="append", default=[], help="glob for intentional historical mentions; repeatable")
    verify.add_argument("--actor", help=f"who is asking; defaults to ${ACTOR_ENV}, then cli")
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
    route.add_argument("--record", action="store_true", help="open a pending receipt for a heavy change; verify closes it")
    route.add_argument("--terms", action="append", default=[], help="an old name or path that should disappear; implies --record")
    route.add_argument("--actor", help=f"who is asking; defaults to ${ACTOR_ENV}, then cli")
    route.add_argument("--json", action="store_true")
    harvest_p = sub.add_parser("harvest", help="list the user's own words from LOG.md and FAILURES.md as profile candidates (reads only)")
    harvest_p.add_argument("--since", help="YYYY-MM-DD; defaults to the saved cursor, else everything")
    harvest_p.add_argument("--speaker", action="append", help="who counts as the user in the records (repeatable); default: user, the user, 用户")
    harvest_p.add_argument("--source", action="append", help="a file to read, with its month volumes (repeatable); default: LOG.md, FAILURES.md")
    harvest_p.add_argument("--include-approvals", action="store_true", help="also list short approvals and answers to the agent's questions")
    harvest_p.add_argument("--all", action="store_true", help="list every quote, not only the likely ones")
    harvest_p.add_argument("--advance", action="store_true", help="after listing, move the cursor to today")
    harvest_p.add_argument("--today", help="YYYY-MM-DD for --advance; defaults to today")
    harvest_p.add_argument("--json", action="store_true")
    lookup_p = sub.add_parser("lookup", help="read rows from CAPABILITIES.md or MAP.md")
    lookup_p.add_argument("--registry", choices=["capability", "map"], required=True)
    lookup_p.add_argument("--query", default="", help="words that must all appear in a row")
    lookup_p.add_argument("--status", help="capability state, e.g. active")
    lookup_p.add_argument("--limit", type=int, default=10)
    lookup_p.add_argument("--detail", action="store_true")
    lookup_p.add_argument("--json", action="store_true")
    audit = sub.add_parser("audit", help="unregistered capabilities, ghost entries, orphans, stubs, volumes, rules")
    audit.add_argument("--json", action="store_true")
    audit.add_argument("--rules", action="store_true", help="JSON for the agent: instruction files, baseline, "
                       "duplicates, and a compact list of every rule")
    audit.add_argument("--rebaseline-rules", action="store_true", help="accept the current always-loaded instructions as the baseline")
    audit.add_argument("--rules-answer", help="record the user's answer once, e.g. guardrails=no")
    audit.add_argument("--rebaseline", action="store_true", help="accept the files that are unregistered today; report only new ones")
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
    events = sub.add_parser("events", help="the log of what the CLI wrote: list, verify, adopt")
    events.add_argument("action", choices=["list", "verify", "adopt"], nargs="?", default="list")
    events.add_argument("--since", type=int, help="list events after this seq, oldest first")
    events.add_argument("--actor", help="list: only this actor; adopt: who records the change")
    events.add_argument("--file", help="list: only events for this file")
    events.add_argument("--limit", type=int, default=20)
    events.add_argument("--note", help="adopt: why the file changed outside the write command")
    events.add_argument("--json", action="store_true")
    ids = sub.add_parser("id", help="one counter per ID series: take, list, audit")
    ids.add_argument("action", choices=["take", "list", "audit"])
    ids.add_argument("series", nargs="?", help="one to four capital letters, e.g. D for decisions")
    ids.add_argument("--note", help="take: what the ID is for")
    ids.add_argument("--actor", help=f"who is asking; defaults to ${ACTOR_ENV}, then cli")
    ids.add_argument("--json", action="store_true")
    write = sub.add_parser("write", help="add one checked line to a memory file; existing lines are never rewritten")
    faces = write.add_subparsers(dest="face", required=True)

    def face(name, help_text, text=None, **options):
        fp = faces.add_parser(name, help=help_text)
        if text:
            fp.add_argument("words", nargs="*", help=text)
            fp.add_argument("--text", help="the same text as an option, for text that starts with a dash")
        for opt, opt_help in options.items():
            flag = "--" + opt.replace("_", "-")
            if opt == "update":
                fp.add_argument(flag, action="store_true", help=opt_help)
            else:
                fp.add_argument(flag, help=opt_help)
        fp.add_argument("--actor", help=f"who is asking; defaults to ${ACTOR_ENV}, then cli")
        fp.add_argument("--dry-run", action="store_true", help="show the line and where it would go; write nothing")
        fp.add_argument("--json", action="store_true")
        return fp

    day, take = "YYYY-MM-DD; defaults to today", "take the next ID of this series and put it in front, e.g. D"
    face("log", "LOG.md: one dated line on top of its month", text="what happened",
         source='a pointer, or who says so; the user\'s exact words as user: "..." (add (answering "...") when they picked your option)',
         date=day, take=take)
    face("now", "NOW.md: one dated line under In flight", text="the item that moved",
         pointer="where the detail lives (required)", section="a heading other than In flight", date=day, take=take)
    face("close", "finish tracked work in one action: the NOW.md line leaves, LOG.md gets the entry", text="what happened",
         match="words from the NOW.md line (required)", pointer="where the detail lives", date=day, take=take)
    face("propose", "PROPOSALS.md: queue a fact for a person to approve", text="the fact",
         source='where it comes from (required); the user\'s exact words as user: "..."',
         origin="the work that produced it, e.g. a task id, or harvest", date=day)
    face("promote", "move one approved proposal from PROPOSALS.md into MEMORY.md",
         match="words from the proposal (required)", section="the MEMORY.md heading to put it under",
         file="a MEMORY/ topic file instead of MEMORY.md")
    face("reject", "remove one proposal from PROPOSALS.md and log why",
         match="words from the proposal (required)", reason="why it was turned down", date=day)
    face("fact", "MEMORY.md: one dated, sourced line", text="the fact",
         source='where it comes from (required); the user\'s exact words as user: "..."',
         section="the heading to put it under", file="a MEMORY/ topic file instead of MEMORY.md", date=day, take=take)
    face("index", "INDEX.md: register a file", text="what the file is, in a few words", path="the file (required)",
         section="the heading whose table gets the row", update="replace the note of a file that is already registered")
    face("capability", "CAPABILITIES.md: register a script, skill, template, or job", text="its name",
         entry="the path to start from (required)", form="script, skill, template, job",
         triggers="the words someone would search for", state="incubating (default), active, or retired",
         call="the shortest call and what it returns")
    face("map", "MAP.md: add a component", text="its name", keywords="words that should lead here (required)",
         job="what it does, in one sentence", details="the file that holds the detail", area="the heading whose table gets the row")
    face("failure", "FAILURES.md: record a memory failure as a regression case (takes the next F ID)",
         kind="stale, invented, missing, or not-loaded", trigger="what exposed it", observed="what happened (required)",
         expected="what should have happened (required)", root_cause="where the chain failed", fix="the change that prevents it",
         check="the next similar situation and its pass condition", date=day)
    batch = faces.add_parser("batch", help="several entries from a JSON Lines file; each line names its face")
    batch.add_argument("--file", required=True, help="path to the file, or - for standard input")
    batch.add_argument("--actor", help=f"who is asking; defaults to ${ACTOR_ENV}, then cli")
    batch.add_argument("--dry-run", action="store_true")
    batch.add_argument("--json", action="store_true")
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
        if args.command == "harvest":
            return cmd_harvest(args)
        if args.command == "lookup":
            return cmd_lookup(args)
        if args.command == "audit":
            return cmd_audit(args)
        if args.command == "map":
            return cmd_map(args)
        if args.command == "split":
            return cmd_split(args)
        if args.command == "events":
            return cmd_events(args)
        if args.command == "id":
            return cmd_id(args)
        if args.command == "write":
            return cmd_write(args)
        return 2
    except GovernanceError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
