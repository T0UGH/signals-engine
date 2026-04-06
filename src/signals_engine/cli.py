"""Signal Engine CLI entry point."""
import argparse
import sys

from .commands import collect, diagnose, status, lanes, config


def main() -> int:
    parser = argparse.ArgumentParser(prog="signals-engine")
    sub = parser.add_subparsers(dest="command", required=True)

    collect.add_parser(sub)
    diagnose.add_parser(sub)
    status.add_parser(sub)
    lanes.add_parser(sub)
    config.add_parser(sub)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    return COMMANDS[args.command](args)


COMMANDS: dict[str, callable] = {
    "collect": collect.run,
    "diagnose": diagnose.run,
    "status": status.run,
    "lanes": lanes.run,
    "config": config.run,
}


if __name__ == "__main__":
    raise SystemExit(main())
