"""diagnose command."""
import argparse


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("diagnose", help="Run diagnostics for a lane")
    p.add_argument("--lane", required=True, help="Lane name")
    return p


def run(args: argparse.Namespace) -> int:
    """Execute the diagnose command."""
    import sys
    from ..runtime.diagnose import diagnose_lane
    try:
        result = diagnose_lane(args.lane)
        print(result.output, file=sys.stdout)
        return 0 if result.exit_code == 0 else 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
