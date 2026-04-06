#!/usr/bin/env python3
"""Guard script: verify no opencli-based x-feed imports remain.

This script checks that:
1. opencli_feed.py has been deleted
2. No Python files import opencli_feed
3. No x-feed related code uses opencli as a runtime backend

Run: python3 scripts/check_no_opencli.py
Exits 0 if clean, 1 if violations found.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FOUND_VIOLATIONS = False


def check_no_opencli_feed_module():
    """opencli_feed.py must not exist in sources/x/."""
    path = REPO_ROOT / "src" / "signal_engine" / "sources" / "x" / "opencli_feed.py"
    if path.exists():
        print(f"FAIL: opencli_feed.py still exists at {path}")
        return False
    print("OK: opencli_feed.py has been deleted")
    return True


def check_no_opencli_imports():
    """No Python files should import from opencli_feed."""
    src_dir = REPO_ROOT / "src"
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text()
        if "opencli_feed" in content or "from .opencli_feed import" in content:
            print(f"FAIL: opencli_feed reference in {py_file.relative_to(REPO_ROOT)}")
            return False
    print("OK: No opencli_feed imports found")
    return True


def check_x_feed_uses_native():
    """x_feed.py must use fetch_home_timeline, not fetch_opencli_feed."""
    path = REPO_ROOT / "src" / "signal_engine" / "lanes" / "x_feed.py"
    content = path.read_text()
    if "fetch_opencli_feed" in content:
        print(f"FAIL: x_feed.py still uses fetch_opencli_feed")
        return False
    if "from ..sources.x.timeline import fetch_home_timeline" not in content:
        print(f"FAIL: x_feed.py does not import fetch_home_timeline")
        return False
    print("OK: x_feed.py uses native fetch_home_timeline")
    return True


def main() -> int:
    global FOUND_VIOLATIONS

    print("=== opencli residue guard ===\n")

    checks = [
        check_no_opencli_feed_module,
        check_no_opencli_imports,
        check_x_feed_uses_native,
    ]

    all_ok = True
    for check in checks:
        if not check():
            all_ok = False
            FOUND_VIOLATIONS = True

    print()
    if all_ok:
        print("PASS: No opencli x-feed residue found")
        return 0
    else:
        print("FAIL: opencli residue detected — migrate to native source first")
        return 1


if __name__ == "__main__":
    sys.exit(main())
