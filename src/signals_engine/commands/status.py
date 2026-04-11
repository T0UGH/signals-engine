"""status command."""
import argparse

from ..core.defaults import resolve_data_dir


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("status", help="Show status for a lane run")
    p.add_argument("--lane", required=True, help="Lane name")
    p.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    p.add_argument("--data-dir", default=None, help="Data directory path")
    return p


def run(args: argparse.Namespace) -> int:
    """Execute the status command."""
    import sys
    import json
    from ..runtime.status import get_run_status
    data_dir = resolve_data_dir(args.data_dir) if args.data_dir else None
    try:
        result = get_run_status(args.lane, args.date, data_dir=data_dir)
        print(json.dumps(result, indent=2), file=sys.stdout)
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
