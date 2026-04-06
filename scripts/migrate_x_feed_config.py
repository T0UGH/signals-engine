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

To the new native source format (per merged final plan):
    lanes:
      x-feed:
        source:
          auth:
            cookie_file: null   # user must set this manually
          limit: 100
          timeout_seconds: 30

The original file is backed up with a .bak suffix before writing.
"""
import argparse
import shutil
import sys
import yaml
from pathlib import Path


def migrate_config(config_text: str) -> tuple[dict, list[str]]:
    """Migrate lanes.yaml config text from opencli to native source.

    Parses YAML, migrates the x-feed section, re-serializes.

    Returns:
        (migrated_config_dict, list of changes made)
    """
    changes: list[str] = []

    config = yaml.safe_load(config_text)
    if config is None:
        config = {}

    lanes = config.setdefault("lanes", {})
    xfeed = lanes.get("x-feed", {})
    opencli = xfeed.get("opencli")

    if not opencli:
        return config, ["No opencli section found in x-feed config"]

    # Carry forward values
    old_limit = opencli.get("limit", 100)
    old_path = opencli.get("path")

    # Build new structure per final plan
    new_source = {
        "auth": {
            "cookie_file": None,  # user must set this
        },
        "limit": old_limit,
        "timeout_seconds": 30,
    }

    # Replace opencli with source
    xfeed["source"] = new_source
    if "opencli" in xfeed:
        del xfeed["opencli"]

    changes.append(f"Migrated opencli.limit={old_limit} -> source.limit")
    if old_path:
        changes.append(f"Carried opencli.path={old_path} (opencli binary no longer used)")

    return config, changes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate x-feed config from opencli to native source (final plan: source.*)"
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to lanes.yaml (default: ~/.daily-lane/config/lanes.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing",
    )
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
    migrated, changes = migrate_config(config_text)

    if not changes:
        print("No opencli section found in x-feed config. Nothing to migrate.")
        return 0

    print(f"Config file: {config_path}")
    print("Changes:")
    for c in changes:
        print(f"  - {c}")

    if args.dry_run:
        print("\n[Dry run] Would write migrated config:")
        print(yaml.dump(migrated, default_flow_style=False, sort_keys=False))
        return 0

    # Backup
    bak_path = config_path.with_suffix(config_path.suffix + ".bak")
    shutil.copy2(config_path, bak_path)
    print(f"\nBacked up original to: {bak_path}")

    # Write back
    output = yaml.dump(migrated, default_flow_style=False, sort_keys=False)
    config_path.write_text(output)
    print(f"Wrote migrated config to: {config_path}")
    print("\nIMPORTANT: Set the cookie file path in source.auth.cookie_file:")
    print(f"  source:")
    print(f"    auth:")
    print(f"      cookie_file: ~/.signal-engine/x-cookies.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
