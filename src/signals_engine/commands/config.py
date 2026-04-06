"""config command."""
import argparse


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("config", help="Config operations")
    sub2 = p.add_subparsers(dest="subcommand")
    sub2.add_parser("check", help="Check config file")
    return p


def run(args: argparse.Namespace) -> int:
    """Execute the config command."""
    import sys
    import yaml
    import os
    from pathlib import Path

    if args.subcommand == "check" or args.subcommand is None:
        default_config = os.environ.get(
            "DAILY_LANE_CONFIG",
            str(Path.home() / ".daily-lane" / "config" / "lanes.yaml")
        )
        path = Path(default_config)
        if not path.exists():
            print(f"ERROR: config not found: {path}", file=sys.stderr)
            return 1
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            lanes = list(data.get("lanes", {}).keys())
            print(f"OK: {path}", file=sys.stdout)
            print(f"Lanes: {', '.join(lanes)}", file=sys.stdout)
            return 0
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
    return 0
