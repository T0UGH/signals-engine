import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="signal-engine")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("collect")
    sub.add_parser("diagnose")
    sub.add_parser("status")
    sub.add_parser("lanes")
    sub.add_parser("config")
    parser.parse_args()
