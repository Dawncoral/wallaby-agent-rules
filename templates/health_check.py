#!/usr/bin/env python3
# wallaby-agent-rules v2
"""health_check.py — weekly tidy-up check for projects using the memory system.

Zero dependencies, Python 3.8+. Three scans:

  1. Stray files in the project root beyond a whitelist.
  2. Generated artifacts (.zip/.tmp/.pyc/.log) at the top level of subdirectories.
  3. .md files not registered in INDEX.md.

Usage:
  python3 health_check.py [target_dir]   # default: current directory

Exit code: 0 when clean, 1 when any scan reports findings.
Tune the constants below to your project — they are configuration, not law.
"""

import os
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
        # "Top level of a subdirectory": direct children of root's subdirs,
        # plus any nested dir that is not itself skipped.
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

    if problems:
        print("FOUND %d item(s) to tidy." % problems)
        return 1
    print("ALL CLEAR — project is tidy.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
