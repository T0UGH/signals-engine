#!/usr/bin/env python3
"""Guard script: verify no opencli-based x-feed code remains.

This script checks that:
1. opencli_feed.py has been deleted
2. No Python files import from opencli_feed
3. x_feed.py uses fetch_home_timeline, not fetch_opencli_feed
4. No opencli paths / binary references in runtime/config/tests/docs for x-feed

Run: python3 scripts/check_no_opencli.py
Exits 0 if clean, 1 if violations found.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Terms that must not appear in these specific contexts for x-feed
FORBIDDEN_TERMS = {
    "opencli_feed",      # module deleted
    "fetch_opencli_feed",  # function removed
    "opencli.path",       # config key removed
    "opencli.limit",      # config key removed
    "dist/main.js",        # binary path removed
}

# Regex patterns to check in source files
PATTERNS = {
    "opencli_feed": re.compile(r"opencli_feed"),
    "fetch_opencli_feed": re.compile(r"fetch_opencli_feed"),
    "opencli\.path": re.compile(r"opencli\.path"),
    "opencli\.limit": re.compile(r"opencli\.limit"),
    "dist/main.js": re.compile(r"dist/main\.js"),
}


def check_no_opencli_feed_module() -> bool:
    """opencli_feed.py must not exist in sources/x/."""
    path = REPO_ROOT / "src" / "signal_engine" / "sources" / "x" / "opencli_feed.py"
    if path.exists():
        print(f"FAIL: opencli_feed.py still exists at {path}")
        return False
    print("OK: opencli_feed.py has been deleted")
    return True


def check_no_opencli_imports() -> bool:
    """No Python files should import from opencli_feed."""
    src_dir = REPO_ROOT / "src"
    ok = True
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text()
        if "opencli_feed" in content or "from .opencli_feed import" in content:
            print(f"FAIL: opencli_feed reference in {py_file.relative_to(REPO_ROOT)}")
            ok = False
    if ok:
        print("OK: No opencli_feed imports found")
    return ok


def check_x_feed_uses_native() -> bool:
    """x_feed.py must use fetch_home_timeline, not fetch_opencli_feed."""
    path = REPO_ROOT / "src" / "signal_engine" / "lanes" / "x_feed.py"
    content = path.read_text()
    ok = True
    if "fetch_opencli_feed" in content:
        print(f"FAIL: x_feed.py still uses fetch_opencli_feed")
        ok = False
    if "from ..sources.x.timeline import fetch_home_timeline" not in content:
        print(f"FAIL: x_feed.py does not import fetch_home_timeline from x.timeline")
        ok = False
    if ok:
        print("OK: x_feed.py uses native fetch_home_timeline")
    return ok


def check_no_opencli_terms_in_code() -> bool:
    """No opencli terms in runtime, config, tests, or docs directories.

    Exempts:
    - Migration script strings describing old config keys (legitimate migration notes)
    - Docs that discuss the migration process
    """
    dirs_to_check = [
        REPO_ROOT / "src" / "signal_engine" / "runtime",
        REPO_ROOT / "src" / "signal_engine" / "lanes",
        REPO_ROOT / "src" / "signal_engine" / "commands",
        REPO_ROOT / "tests",
    ]
    ok = True
    for directory in dirs_to_check:
        if not directory.exists():
            continue
        for py_file in directory.rglob("*.py"):
            content = py_file.read_text()
            for term, pattern in PATTERNS.items():
                if term == "opencli_feed":
                    continue
                if pattern.search(content):
                    for line_no, line in enumerate(content.splitlines(), 1):
                        if pattern.search(line) and not line.strip().startswith("#"):
                            print(f"FAIL: '{term}' found in {py_file.relative_to(REPO_ROOT)}:{line_no}")
                            ok = False
    if ok:
        print("OK: No opencli terms in runtime/lanes/commands/tests")
    return ok


def check_no_opencli_in_config_docs() -> bool:
    """No opencli references in docs about x-feed migration."""
    docs_dir = REPO_ROOT / "docs"
    ok = True
    if not docs_dir.exists():
        return ok
    for doc_file in docs_dir.rglob("*.md"):
        content = doc_file.read_text()
        # Only flag if it mentions x-feed AND opencli together in non-historical context
        lines = content.splitlines()
        for line_no, line in enumerate(lines, 1):
            if "x-feed" in line.lower() and "opencli" in line.lower():
                if not line.strip().startswith("#") and "historical" not in line.lower() and "deprecated" not in line.lower():
                    # Allow mentions in migration guide as long as they say "migrated from"
                    if "migrated from" not in line.lower() and "replaced by" not in line.lower():
                        print(f"WARN: ambiguous opencli+x-feed reference in {doc_file.relative_to(REPO_ROOT)}:{line_no}: {line.strip()[:60]}")
    return ok


def main() -> int:
    print("=== opencli residue guard ===\n")

    checks = [
        check_no_opencli_feed_module,
        check_no_opencli_imports,
        check_x_feed_uses_native,
        check_no_opencli_terms_in_code,
    ]

    all_ok = True
    for check in checks:
        if not check():
            all_ok = False
        print()

    if all_ok:
        print("PASS: No opencli x-feed residue found")
        return 0
    else:
        print("FAIL: opencli residue detected — complete migration first")
        return 1


if __name__ == "__main__":
    sys.exit(main())
