#!/usr/bin/env python3
"""Migrate x-feed lane config from opencli to native source.

Usage:
    python3 migrate_x_feed_config.py [--config PATH] [--dry-run]

This script migrates the x-feed lane config from the old opencli format:
    lanes:
      x-feed:
        opencli:
          path: ~/.openclaw/workspace/github/opencli
          limit: 100

To the new native format:
    lanes:
      x-feed:
        native:
          cookie_file: ~/.signal-engine/x-cookies.json
          limit: 100
          timeout: 30

The original file is backed up with a .bak suffix before writing.
"""
import argparse
import shutil
import sys
from pathlib import Path


def migrate_config(config_text: str) -> tuple[str, list[str]]:
    """Migrate lanes.yaml config text from opencli to native format.

    Returns:
        (migrated_text, list of changes made)
    """
    changes: list[str] = []
    lines = config_text.splitlines(keepends=True)
    result_lines: list[str] = []
    i = 0
    in_opencli_section = False
    opencli_indent = ""
    native_written = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect opencli section start
        if stripped == "opencli:":
            in_opencli_section = True
            # Get the indent of the parent (x-feed level)
            # Find the indent by looking at previous lines
            j = len(result_lines) - 1
            while j >= 0 and result_lines[j].strip() == "":
                j -= 1
            if j >= 0:
                opencli_indent = result_lines[j][:len(result_lines[j]) - len(result_lines[j].lstrip())]
            # Skip writing the opencli: line, we'll write native: instead
            i += 1
            continue

        # Detect end of opencli section (dedent back to x-feed level)
        if in_opencli_section and stripped and not line.startswith(" " * (len(opencli_indent) + 4)):
            in_opencli_section = False
            native_indent = opencli_indent + "    "
            result_lines.append(f"{native_indent}native:\n")
            if not native_written:
                result_lines.append(f"{native_indent}    cookie_file: null\n")
                result_lines.append(f"{native_indent}    limit: 100\n")
                result_lines.append(f"{native_indent}    timeout: 30\n")
                changes.append("Replaced opencli section with native section (cookie_file=null, limit=100, timeout=30)")
                native_written = True

        if in_opencli_section:
            # Extract limit from opencli section
            if stripped.startswith("limit:"):
                limit_val = stripped.split(":", 1)[1].strip()
                if limit_val:
                    changes.append(f"Carried limit={limit_val} from opencli to native")
        else:
            result_lines.append(line)

        i += 1

    # Handle case where opencli was at end of file
    if in_opencli_section:
        native_indent = opencli_indent + "    "
        result_lines.append(f"{native_indent}native:\n")
        if not native_written:
            result_lines.append(f"{native_indent}    cookie_file: null\n")
            result_lines.append(f"{native_indent}    limit: 100\n")
            result_lines.append(f"{native_indent}    timeout: 30\n")
            changes.append("Replaced opencli section with native section")
            native_written = True

    return "".join(result_lines), changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate x-feed config from opencli to native source")
    parser.add_argument("--config", default=None, help="Path to lanes.yaml (default: ~/.daily-lane/config/lanes.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    if args.config:
        config_path = Path(args.config).expanduser()
    else:
        config_path = Path.home() / ".daily-lane" / "config" / "lanes.yaml"

    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        print("Nothing to migrate.", file=sys.stderr)
        return 1

    config_text = config_path.read_text()

    migrated_text, changes = migrate_config(config_text)

    if not changes:
        print("No opencli section found in config. Nothing to migrate.")
        return 0

    print(f"Config file: {config_path}")
    print("Changes:")
    for c in changes:
        print(f"  - {c}")

    if args.dry_run:
        print("\n[Dry run] Would write migrated config:")
        print(migrated_text)
        return 0

    # Backup
    bak_path = config_path.with_suffix(config_path.suffix + ".bak")
    shutil.copy2(config_path, bak_path)
    print(f"\nBacked up original to: {bak_path}")

    config_path.write_text(migrated_text)
    print(f"Wrote migrated config to: {config_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
