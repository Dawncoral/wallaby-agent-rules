#!/usr/bin/env python3
# wallaby-agent-rules 1.1.0
"""health_check.py — weekly tidy-up check for projects using the memory system.

Zero dependencies, Python 3.8+. Ten scans:

  1. Stray files in the project root beyond a whitelist.
  2. Generated artifacts (.zip/.tmp/.pyc/.log) at the top level of subdirectories.
  3. .md files not registered in INDEX.md.
  4. NOW.md entries idle past the stale threshold (default: 30 days).
  5. INDEX.md registrations pointing at files that no longer exist.
     (Scans 3 + 5 together cover index drift in both directions.)
  6. Entry files (AGENTS.md / CLAUDE.md / .cursorrules) past the size wall —
     three budgets, whichever bursts first: ~32 KiB bytes (hard tool
     truncation), ~500 lines, ~8k estimated tokens (attention budget).
     CJK text fills byte budgets ~3x faster per character than Latin text,
     so for CJK-heavy files the token estimate is the truer gauge.
  7. MEMORY.md bullet lines with no date — without one, "idle for 30 days"
     is unfalsifiable and nothing ever moves. (Heuristic; tune to taste.)
  8. MEMORY.md past its budget — soft/hard line walls plus the same ~8k
     token attention budget as entry files. Only reports when over the soft
     wall, and lists the facts idle 30+ days that should demote to LOG.md
     at the next closeout. Below the wall it stays silent.
  9. Secrets hygiene: credential files (.env, .credentials/) tracked by git,
     and common key patterns (sk-…, AKIA…, private-key blocks, ghp_…,
     xox…-…) sitting in tracked text files. Placeholders and examples are
     whitelisted. (Needs git for the tracked-files view; without .git it
     pattern-scans all text files instead.)
 10. Commit silence: the last git commit is newer than the newest dated
     entry in NOW.md / LOG.md — work happened but nothing was recorded.
     Skipped when there is no .git (fail-open).

Usage:
  python3 health_check.py [target_dir]   # default: current directory

Exit code: 0 when clean, 1 when any scan reports findings.
Tune the constants below to your project — they are configuration, not law.
"""

import datetime
import os
import re
import sys

# --- Configuration -----------------------------------------------------------

# Files allowed to live loose in the project root.
ROOT_WHITELIST = {
    "README.md", "AGENTS.md", "CLAUDE.md", ".cursorrules",
    "MEMORY.md", "NOW.md", "INDEX.md", "LOG.md", "CHANGELOG.md",
    "LICENSE", "LICENCE", "LICENSE.md", "LICENSE.txt",
    "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
    "Makefile", "Dockerfile", "docker-compose.yml",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "Gemfile",
    "tsconfig.json", ".gitignore", ".gitattributes", ".editorconfig",
    ".DS_Store",
}

# Directories never scanned (vendor, VCS, caches, build output).
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", ".next", ".nuxt", "out", "target", ".idea", ".vscode",
}

# Generated-artifact extensions that should not sit loose inside the project.
ARTIFACT_EXTS = {".zip", ".tmp", ".pyc", ".log"}

# .md files exempt from the INDEX.md registration check.
INDEX_EXEMPT = {"INDEX.md", "CHANGELOG.md", "LICENSE.md"}

# Scan 4: NOW.md entries idle longer than this are stale.
STALE_DAYS = 30

# Scan 6: entry-file budget — three walls, whichever bursts first.
#   bytes:  several agent tools truncate at ~32 KiB (a hard byte limit)
#   lines:  instruction-following degrades past ~500 lines
#   tokens: ~8k tokens of standing instructions is an attention budget,
#           even where no hard truncation exists
# CJK text fills byte budgets roughly 3x faster per character than Latin
# text, so for CJK-heavy files the token estimate is the truer gauge.
ENTRY_FILES = ("AGENTS.md", "CLAUDE.md", ".cursorrules")
ENTRY_MAX_BYTES = 32 * 1024
ENTRY_MAX_LINES = 500
ENTRY_MAX_TOKENS = 8192
CJK_NOTE_THRESHOLD = 0.15  # share of CJK chars that triggers the density note

# Scan 8: MEMORY.md budget — soft wall triggers demotion of idle facts,
# hard wall means the memory file itself has become the attention problem.
MEMORY_SOFT_LINES = 150
MEMORY_HARD_LINES = 200
MEMORY_MAX_TOKENS = 8192
MEMORY_AGE_DAYS = 30  # facts untouched longer than this are demote candidates

# Scan 9: secrets hygiene — credential filenames that must never be tracked,
# and common key patterns that must never land in tracked files.
SECRET_PATH_RX = re.compile(r"(^|/)(\.credentials/|\.env(\.|$)|.*\.pem$|.*\.key$)")
SECRET_PATTERNS = [
    ("generic API key (sk-…)", re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_\-]{15,}")),
    ("AWS access key (AKIA…)", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("GitHub token (ghp_…)", re.compile(r"\bghp_[A-Za-z0-9]{30,}")),
    ("Slack token (xox…-…)", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
]
# Lines that are clearly placeholders/examples, not real secrets.
SECRET_PLACEHOLDER_RX = re.compile(
    r"(x{3,}|your[-_ ]|example|placeholder|dummy|sample|<[a-z\-]+>|\.\.\.)", re.I)
SECRET_MAX_FILE_BYTES = 512 * 1024  # skip very large files

# Scan 10: commit silence — commits this much newer than the newest dated
# NOW.md/LOG.md entry mean work happened with no record.
SILENCE_GRACE_DAYS = 1


# --- Scans -------------------------------------------------------------------

def scan_root_stray(root):
    """Scan 1: files in the project root beyond the whitelist."""
    findings = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        if name.startswith(".") and name not in {".cursorrules"}:
            continue  # dotfiles are config by convention
        if name not in ROOT_WHITELIST:
            findings.append(name)
    return findings


def scan_artifacts(root):
    """Scan 2: generated artifacts at the top level of subdirectories."""
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if dirpath == root:
            # Only subdirectories are checked; root clutter is scan 1's job.
            continue
        for name in sorted(filenames):
            ext = os.path.splitext(name)[1].lower()
            if ext in ARTIFACT_EXTS:
                findings.append(os.path.relpath(os.path.join(dirpath, name), root))
    return findings


def scan_unregistered_md(root):
    """Scan 3: .md files not mentioned in INDEX.md."""
    index_path = os.path.join(root, "INDEX.md")
    if not os.path.isfile(index_path):
        return None  # no index — reported separately by the caller
    with open(index_path, "r", encoding="utf-8", errors="replace") as f:
        index_text = f.read()
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            if not name.lower().endswith(".md") or name in INDEX_EXEMPT:
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            # Registered if the index mentions the filename or the full path.
            if name not in index_text and rel not in index_text:
                findings.append(rel)
    return findings


_DATE_RX = re.compile(r"^\s*[-*]\s*\[(\d{4})-(\d{2})-(\d{2})\]\s*(.*)")


def scan_stale_now(root, today=None):
    """Scan 4: dated NOW.md entries idle past STALE_DAYS."""
    now_path = os.path.join(root, "NOW.md")
    if not os.path.isfile(now_path):
        return None
    today = today or datetime.date.today()
    findings = []
    with open(now_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _DATE_RX.match(line)
            if not m:
                continue
            try:
                d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            age = (today - d).days
            if age > STALE_DAYS:
                findings.append((age, m.group(4).strip()))
    return sorted(findings, reverse=True)


_TOKEN_RX = re.compile(r"`([^`\s]+)`")


def scan_broken_index_entries(root):
    """Scan 5: INDEX.md registrations whose files no longer exist."""
    index_path = os.path.join(root, "INDEX.md")
    if not os.path.isfile(index_path):
        return None
    findings = []
    with open(index_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.lstrip().startswith("#"):
                continue
            for token in _TOKEN_RX.findall(line):
                cand = token.strip()
                if not cand or cand.startswith(("http://", "https://", "#", "<")):
                    continue
                if "/" not in cand and "." not in os.path.basename(cand):
                    continue  # plain word, not a path
                if not os.path.exists(os.path.join(root, cand)):
                    findings.append(cand)
    return findings


def _entry_stats(path):
    """Bytes, lines, rough token estimate, CJK share for one file."""
    with open(path, "rb") as f:
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    nbytes = len(data)
    lines = text.count("\n") + 1
    cjk = sum(1 for ch in text
              if "一" <= ch <= "鿿"
              or "　" <= ch <= "〿"
              or "＀" <= ch <= "￯")
    est_tokens = cjk + (len(text) - cjk) // 4
    return nbytes, lines, est_tokens, cjk / max(1, len(text))


def scan_entry_size(root):
    """Scan 6: entry files past the size wall — bytes, lines, or tokens.

    Three budgets, whichever bursts first: tools truncate on bytes,
    attention degrades on lines and tokens. CJK text fills byte budgets
    roughly 3x faster per character than Latin text, so for CJK-heavy
    files the token estimate is the truer gauge.
    """
    findings = []
    for name in ENTRY_FILES:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        nbytes, lines, tokens, cjk_ratio = _entry_stats(path)
        over = []
        if nbytes > ENTRY_MAX_BYTES:
            over.append("%d bytes > %d" % (nbytes, ENTRY_MAX_BYTES))
        if lines > ENTRY_MAX_LINES:
            over.append("%d lines > %d" % (lines, ENTRY_MAX_LINES))
        if tokens > ENTRY_MAX_TOKENS:
            over.append("~%d est. tokens > %d" % (tokens, ENTRY_MAX_TOKENS))
        if over:
            note = ""
            if cjk_ratio >= CJK_NOTE_THRESHOLD:
                note = (" — CJK-dense (%.0f%%): byte budgets fill ~3x "
                        "faster than English" % (cjk_ratio * 100))
            findings.append("%s (%s)%s" % (name, ", ".join(over), note))
    return findings


def scan_undated_memory(root):
    """Scan 7: MEMORY.md bullet lines with no date (heuristic)."""
    mem_path = os.path.join(root, "MEMORY.md")
    if not os.path.isfile(mem_path):
        return None
    date_rx = re.compile(r"\d{4}-\d{2}-\d{2}")
    findings = []
    in_comment = False
    with open(mem_path, "r", encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            s = line.strip()
            if "<!--" in s:
                in_comment = True
            if in_comment:
                if "-->" in s:
                    in_comment = False
                continue
            if s.startswith(("- ", "* ")) and not date_rx.search(s):
                findings.append("line %d: %s" % (n, s[:80]))
    return findings


def scan_memory_budget(root, today=None):
    """Scan 8: MEMORY.md past its budget, with demote candidates.

    Silent below the soft wall — a small memory file needs no ceremony.
    Over the soft wall, list dated facts idle past MEMORY_AGE_DAYS: those
    move to LOG.md at the next closeout. Git keeps the history.
    The token estimate is CJK-weighted (see _entry_stats), so a Chinese
    MEMORY.md hits the same wall at the same real size.
    """
    mem_path = os.path.join(root, "MEMORY.md")
    if not os.path.isfile(mem_path):
        return None
    nbytes, lines, tokens, _ = _entry_stats(mem_path)
    over_soft = lines > MEMORY_SOFT_LINES or tokens > MEMORY_MAX_TOKENS
    if not over_soft:
        return {"over": False, "lines": lines, "tokens": tokens}
    today = today or datetime.date.today()
    candidates = []
    with open(mem_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _DATE_RX.match(line)
            if not m:
                continue
            try:
                d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            age = (today - d).days
            if age > MEMORY_AGE_DAYS:
                candidates.append((age, m.group(4).strip()))
    candidates.sort(reverse=True)
    return {
        "over": True, "hard": lines > MEMORY_HARD_LINES,
        "lines": lines, "tokens": tokens, "candidates": candidates,
    }


def _git_tracked_files(root):
    """Relative paths tracked by git, or None when git/.git is unavailable."""
    if not os.path.isdir(os.path.join(root, ".git")):
        return None
    try:
        import subprocess
        out = subprocess.run(
            ["git", "-C", root, "ls-files"],
            capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            return None
        return set(p for p in out.stdout.splitlines() if p)
    except Exception:
        return None


def scan_secrets(root):
    """Scan 9: secrets hygiene.

    Two checks: credential files tracked by git, and common key patterns in
    text files (tracked files when git is available, all text files
    otherwise). Placeholders/examples are whitelisted; .credentials/ is
    never scanned — it is allowed to exist, just never to be committed.
    This scan is a reminder, not a safety net; the real defense is the
    habit of keeping keys out of git.
    """
    tracked = _git_tracked_files(root)
    findings = []
    if tracked is not None:
        for rel in sorted(tracked):
            if SECRET_PATH_RX.search(rel.replace(os.sep, "/")):
                findings.append("tracked credential file: %s" % rel)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and d != ".credentials"]
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            if SECRET_PATH_RX.search(rel.replace(os.sep, "/")):
                continue  # the file itself is finding material, not its contents
            if tracked is not None and rel not in tracked:
                continue
            try:
                if os.path.getsize(path) > SECRET_MAX_FILE_BYTES:
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if SECRET_PLACEHOLDER_RX.search(line):
                    continue
                for label, rx in SECRET_PATTERNS:
                    if rx.search(line):
                        findings.append("%s:%d: possible %s" % (rel, n, label))
                        break
    return findings, tracked is not None


def scan_commit_silence(root):
    """Scan 10: last git commit newer than the newest NOW.md/LOG.md entry.

    Detection, not enforcement: it cannot prove what was written, only that
    *nothing* was. Returns None when there is no git repo (fail-open).
    """
    if not os.path.isdir(os.path.join(root, ".git")):
        return None
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", root, "log", "-1", "--format=%cs"],
            capture_output=True, text=True, timeout=20)
        if out.returncode != 0 or not out.stdout.strip():
            return None
        last_commit = datetime.date.fromisoformat(out.stdout.strip())
    except Exception:
        return None
    any_date = re.compile(r"(\d{4}-\d{2}-\d{2})")
    latest = None
    for name in ("NOW.md", "LOG.md"):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for m in any_date.finditer(f.read()):
                try:
                    d = datetime.date.fromisoformat(m.group(1))
                except ValueError:
                    continue
                if latest is None or d > latest:
                    latest = d
    if latest is None:
        return {"last_commit": last_commit, "latest_entry": None, "silent": True}
    gap = (last_commit - latest).days
    return {"last_commit": last_commit, "latest_entry": latest, "gap": gap,
            "silent": gap > SILENCE_GRACE_DAYS}


# --- Main --------------------------------------------------------------------

def main(argv):
    root = os.path.abspath(argv[1] if len(argv) > 1 else os.getcwd())
    if not os.path.isdir(root):
        print("error: not a directory: %s" % root)
        return 2

    print("health_check: %s\n" % root)
    problems = 0

    stray = scan_root_stray(root)
    if stray:
        problems += len(stray)
        print("[1] Stray files in project root (%d):" % len(stray))
        for f in stray:
            print("      %s" % f)
        print("      -> move them into a subdirectory, or add to ROOT_WHITELIST\n")
    else:
        print("[1] Root is clean.\n")

    artifacts = scan_artifacts(root)
    if artifacts:
        problems += len(artifacts)
        print("[2] Generated artifacts inside the project (%d):" % len(artifacts))
        for f in artifacts:
            print("      %s" % f)
        print("      -> delete or move to an ignored output directory\n")
    else:
        print("[2] No generated artifacts found.\n")

    unregistered = scan_unregistered_md(root)
    if unregistered is None:
        problems += 1
        print("[3] INDEX.md not found — create one (see templates/INDEX.md).\n")
    elif unregistered:
        problems += len(unregistered)
        print("[3] .md files not registered in INDEX.md (%d):" % len(unregistered))
        for f in unregistered:
            print("      %s" % f)
        print("      -> add one line per file to INDEX.md\n")
    else:
        print("[3] Every .md file is registered in INDEX.md.\n")

    stale = scan_stale_now(root)
    if stale is None:
        print("[4] NOW.md not found — skipping staleness scan.\n")
    elif stale:
        problems += len(stale)
        print("[4] NOW.md entries idle over %d days (%d):" % (STALE_DAYS, len(stale)))
        for age, text in stale:
            print("      %dd idle: %s" % (age, text))
        print("      -> archive them at the next closeout; git keeps the history\n")
    else:
        print("[4] NOW.md entries all fresh.\n")

    broken = scan_broken_index_entries(root)
    if broken is None:
        print("[5] INDEX.md not found — skipping broken-registration scan.\n")
    elif broken:
        problems += len(broken)
        print("[5] INDEX.md registrations pointing at missing files (%d):" % len(broken))
        for f in broken:
            print("      %s" % f)
        print("      -> remove the line, or fix the path\n")
    else:
        print("[5] Every INDEX.md registration resolves to a real file.\n")

    oversized = scan_entry_size(root)
    if oversized:
        problems += len(oversized)
        print("[6] Entry files past the size wall (%d):" % len(oversized))
        for f in oversized:
            print("      %s" % f)
        print("      -> move detail into linked files; bytes, lines, and tokens are three separate budgets\n")
    else:
        print("[6] Entry files within budget.\n")

    undated = scan_undated_memory(root)
    if undated is None:
        print("[7] MEMORY.md not found — skipping undated-fact scan.\n")
    elif undated:
        problems += len(undated)
        print("[7] MEMORY.md bullet lines with no date (%d):" % len(undated))
        for f in undated:
            print("      %s" % f)
        print("      -> add a [YYYY-MM-DD] date (and a source); undated facts never age out\n")
    else:
        print("[7] Every MEMORY.md entry is dated.\n")

    budget = scan_memory_budget(root)
    if budget is None:
        print("[8] MEMORY.md not found — skipping memory-budget scan.\n")
    elif not budget["over"]:
        print("[8] MEMORY.md within budget (%d lines, ~%d est. tokens; soft wall %d lines).\n"
              % (budget["lines"], budget["tokens"], MEMORY_SOFT_LINES))
    else:
        cands = budget["candidates"]
        problems += 1 + len(cands)
        level = "HARD wall" if budget["hard"] else "soft wall"
        print("[8] MEMORY.md past its %s (%d lines > %d, ~%d est. tokens):"
              % (level, budget["lines"],
                 MEMORY_HARD_LINES if budget["hard"] else MEMORY_SOFT_LINES,
                 budget["tokens"]))
        if cands:
            print("      demote these facts idle over %d days into LOG.md at the next closeout:"
                  % MEMORY_AGE_DAYS)
            for age, text in cands:
                print("      %dd idle: %s" % (age, text))
        else:
            print("      no dated facts idle over %d days — tighten wording or split detail into linked files"
                  % MEMORY_AGE_DAYS)
        print("      -> git keeps the history; MEMORY.md is for permanent facts only\n")

    secrets, used_git = scan_secrets(root)
    if secrets:
        problems += len(secrets)
        print("[9] Secrets hygiene (%d):" % len(secrets))
        for f in secrets:
            print("      %s" % f)
        print("      -> move credentials into .credentials/ or a .env file, and keep both out of git")
        print("      -> this scan is a reminder, not a safety net — keeping keys out of git is a habit\n")
    else:
        scope = "tracked files" if used_git else "all text files (no git repo)"
        print("[9] No secrets in %s.\n" % scope)

    silence = scan_commit_silence(root)
    if silence is None:
        print("[10] No git repo — skipping commit-silence scan.\n")
    elif silence["latest_entry"] is None:
        problems += 1
        print("[10] Last commit %s, but NOW.md/LOG.md hold no dated entry — work is happening with no record."
              % silence["last_commit"])
        print("      -> run the closeout ritual after work sessions\n")
    elif silence["silent"]:
        problems += 1
        print("[10] Last commit %s is %dd newer than the newest NOW.md/LOG.md entry (%s)."
              % (silence["last_commit"], silence["gap"], silence["latest_entry"]))
        print("      -> committed but not recorded: run the closeout ritual\n")
    else:
        print("[10] Commits and records in step (last commit %s, newest entry %s).\n"
              % (silence["last_commit"], silence["latest_entry"]))

    if problems:
        print("FOUND %d item(s) to tidy." % problems)
        return 1
    print("ALL CLEAR — project is tidy.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
