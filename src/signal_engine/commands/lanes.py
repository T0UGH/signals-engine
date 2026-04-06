"""lanes command."""
import argparse


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("lanes", help="List available lanes")
    sub2 = p.add_subparsers(dest="subcommand")
    sub2.add_parser("list", help="List lanes")
    return p


def run(args: argparse.Namespace) -> int:
    """Execute the lanes command."""
    import sys
    from ..lanes.registry import LANE_REGISTRY
    if args.subcommand == "list" or args.subcommand is None:
        for name in LANE_REGISTRY:
            print(name, file=sys.stdout)
        return 0
    return 0
