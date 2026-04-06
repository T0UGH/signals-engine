"""diagnose command."""
import argparse
import os
from pathlib import Path

import yaml


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("diagnose", help="Run diagnostics for a lane")
    p.add_argument("--lane", required=True, help="Lane name")
    p.add_argument("--data-dir", default=None, help="Data directory path")
    p.add_argument("--config", default=None, help="Config file path")
    return p


def run(args: argparse.Namespace) -> int:
    """Execute the diagnose command."""
    import sys
    from ..runtime.diagnose import diagnose_lane

    data_dir = Path(args.data_dir) if args.data_dir else None

    config = None
    config_path = args.config or os.environ.get(
        "DAILY_LANE_CONFIG",
        str(Path.home() / ".daily-lane" / "config" / "lanes.yaml")
    )
    if Path(config_path).exists():
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
        except Exception:
            pass

    try:
        result = diagnose_lane(args.lane, data_dir=data_dir, config=config)
        print(result.output, file=sys.stdout)
        return 0 if result.exit_code == 0 else 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
