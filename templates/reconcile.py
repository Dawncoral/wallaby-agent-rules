#!/usr/bin/env python3
# wallaby-agent-rules v3.1
"""reconcile.py — weekly consistency audit between the dated log and current state.

Zero dependencies, Python 3.8+. Two scans:

  1. Closure contradictions: LOG.md entries that claim something is done
     (shipped / fixed / merged / published / resolved / ...) while the same
     topic still sits in NOW.md's "In flight" section. One of the two files
     is stale — most often NOW.md was never updated.
  2. Evidence-free closures: LOG.md entries that claim done but point at
     nothing — no file path, no ticket, no link, no backtick reference.
     A "done" you cannot verify is a rumor.

The health check catches structural drift; this script catches *narrative*
drift — the gap between what the log claims and what the state file shows.
Write discipline always loosens. The audit is what catches it.

Usage:
  python3 reconcile.py [target_dir] [--days N]   # default: cwd, 30 days

Exit code: 0 when clean, 1 when any scan reports findings.
Tune the constants below to your project — they are configuration, not law.
"""

import re
import sys
from datetime import date
from pathlib import Path

# --- Configuration -----------------------------------------------------------

LOG_NAME = "LOG.md"
NOW_NAME = "NOW.md"

# Scan window: only log entries dated within the last N days are audited.
WINDOW_DAYS = 30

# Words that mark a log entry as a closure claim ("this got done").
CLOSURE_WORDS = re.compile(
    r"\b(shipped|ships|done|closed|closes|fixed|fixes|merged|published|"
    r"released|resolved|launched|completed|landed|deployed|closed out)\b"
    r"|已上线|已发布|已完成|已修复|已合并|已交付|已销|闭环",
    re.I,
)

# A closure entry "has evidence" when it contains any of these.
BACKTICK = re.compile(r"`[^`]+`")
URL = re.compile(r"https?://\S+")
PATH_LIKE = re.compile(r"[\w.-]+/[\w./-]+")          # dir/file or ops/runbook.md#anchor
FILE_LIKE = re.compile(r"\w[\w.-]*\.(?:md|py|js|ts|json|ya?ml|toml|sh|sql|pdf)\b", re.I)
TICKET_LIKE = re.compile(r"#\d+\b|[A-Z]+-\d+\b")     # #123, PROJ-123

# Topic tokens: which words in a closure entry identify *what* was closed.
TOKEN = re.compile(r"[A-Za-z0-9][\w.-]*")
QUOTED_CJK = re.compile(r"[「『]([^」』]{2,8})[」』]|[《〈]([^》〉]{2,8})[》〉]")

# Tokens too generic to identify a topic (extend freely).
STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "now",
    "via", "per", "our", "your", "its", "his", "her", "their", "after",
    "before", "update", "updated", "new", "v1", "v2", "v3",
}
VERSION_FRAG = re.compile(r"^v?\d+(\.\d+)*$", re.I)

# LOG entry format: - [YYYY-MM-DD] text   (newest on top, per template)
LOG_ENTRY = re.compile(r"^[-*]\s*\[(\d{4})-(\d{2})-(\d{2})\]\s*(.*)$")


# --- Parsing -----------------------------------------------------------------

def parse_log(path):
    """Return [(date, text)] for dated bullet entries in LOG.md."""
    if not path.is_file():
        return None
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LOG_ENTRY.match(line.strip())
        if not m:
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        out.append((d, m.group(4).strip()))
    return out


def parse_in_flight(path):
    """Return the open bullet lines of NOW.md's 'In flight' section.

    Everything still listed under 'In flight' is treated as open — that is
    the convention: finished work leaves the section at the next closeout.
    """
    if not path.is_file():
        return None
    lines = []
    in_section = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("## "):
            if in_section:
                break  # next section ends 'In flight'
            in_section = "in flight" in s.lower()
            continue
        if in_section and s.startswith(("- ", "* ")) and "~~" not in s:
            lines.append(s[2:])
    return lines


def topic_tokens(text):
    """Extract topic-identifying tokens from a log entry: backticked words,
    quoted CJK names, and Latin tokens of length >= 4 that are not stopwords,
    dates, or version fragments."""
    tokens = []
    for m in BACKTICK.finditer(text):
        w = m.group(0).strip("`")
        if "/" not in w and "." not in w and " " not in w and len(w) >= 2:
            tokens.append(w.lower())
    for m in QUOTED_CJK.finditer(text):
        tokens.append(m.group(1) or m.group(2))
    for m in TOKEN.finditer(URL.sub(" ", text)):
        w = m.group(0)
        if (len(w) >= 4 and not VERSION_FRAG.match(w) and not w.isdigit()
                and w.lower() not in STOPWORDS
                and not CLOSURE_WORDS.fullmatch(w)):
            tokens.append(w.lower())
    return set(tokens)


def has_evidence(text):
    return bool(BACKTICK.search(text) or URL.search(text)
                or PATH_LIKE.search(text) or FILE_LIKE.search(text)
                or TICKET_LIKE.search(text))


# --- Scans -------------------------------------------------------------------

def scan_contradictions(entries, open_lines):
    """Closure entries whose topic still appears in an open NOW.md line."""
    findings = []
    for d, text in entries:
        if not CLOSURE_WORDS.search(text):
            continue
        topics = topic_tokens(text)
        if not topics:
            continue
        for line in open_lines:
            low = line.lower()
            hit = next((t for t in topics if t in low), None)
            if hit:
                findings.append(
                    (d, text[:60], hit, line[:60]))
                break  # one open-line match per entry is enough
    return findings


def scan_evidence(entries):
    """Closure entries with nothing to verify against."""
    return [(d, text[:72]) for d, text in entries
            if CLOSURE_WORDS.search(text) and not has_evidence(text)]


# --- Main --------------------------------------------------------------------

def main(argv):
    target = Path(argv[1]) if len(argv) > 1 and not argv[1].startswith("-") else Path.cwd()
    days = WINDOW_DAYS
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])

    entries = parse_log(target / LOG_NAME)
    open_lines = parse_in_flight(target / NOW_NAME)
    problems = 0

    if entries is None:
        print("[skip] %s not found — the reconcile audit needs a dated log." % LOG_NAME)
        return 0
    if open_lines is None:
        print("[skip] %s not found — nothing to reconcile against." % NOW_NAME)
        return 0

    today = date.today()
    recent = [(d, t) for d, t in entries if 0 <= (today - d).days <= days]
    print("Auditing %d log entries from the last %d days against %d open line(s) in %s.\n"
          % (len(recent), days, len(open_lines), NOW_NAME))

    contra = scan_contradictions(recent, open_lines)
    if contra:
        problems += len(contra)
        print("[1] Log says done, NOW.md still in flight (%d):" % len(contra))
        for d, entry, token, line in contra:
            print("    %s \"%s...\" — topic \"%s\" still open: \"%s...\"" % (d, entry, token, line))
        print("    One of the two is stale. Usually NOW.md was never updated.\n")
    else:
        print("[1] Log says done, NOW.md still in flight: none.\n")

    rumors = scan_evidence(recent)
    if rumors:
        problems += len(rumors)
        print("[2] \"Done\" with nothing to point at (%d):" % len(rumors))
        for d, entry in rumors:
            print("    %s \"%s...\"" % (d, entry))
        print("    A \"done\" you cannot verify is a rumor. Add a path, ticket, or link.\n")
    else:
        print("[2] \"Done\" with nothing to point at: none.\n")

    if problems:
        print("%d finding(s). Memory is not written, it is audited." % problems)
        return 1
    print("Clean. Log and state agree with each other.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
