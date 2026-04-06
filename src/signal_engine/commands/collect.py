"""collect command."""
import argparse
import os
from pathlib import Path

from ..core import RunContext, ConfigError


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("collect", help="Collect signals for a lane")
    p.add_argument("--lane", required=True, help="Lane name (e.g. x-feed)")
    p.add_argument("--date", default=None, help="Date in YYYY-MM-DD format (default: today)")
    p.add_argument("--data-dir", default=None, help="Data directory path")
    p.add_argument("--config", default=None, help="Config file path")
    return p


def load_config(config_path: str | None) -> dict:
    """Load lanes config from yaml."""
    import os
    import yaml

    if config_path:
        path = Path(config_path).expanduser()
    else:
        default_config = os.environ.get(
            "DAILY_LANE_CONFIG",
            str(Path.home() / ".daily-lane" / "config" / "lanes.yaml")
        )
        path = Path(default_config)

    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with open(path) as f:
        return yaml.safe_load(f)


def run(args: argparse.Namespace) -> int:
    """Execute the collect command."""
    import sys
    from datetime import date
    from ..runtime.collect import collect_lane

    lane = args.lane
    run_date = args.date or date.today().isoformat()

    if args.data_dir:
        data_dir = Path(args.data_dir).expanduser()
    else:
        data_dir = Path(os.environ.get(
            "DAILY_LANE_DATA_DIR",
            str(Path.home() / ".daily-lane-data")
        ))

    config = load_config(args.config)

    ctx = RunContext(lane=lane, date=run_date, data_dir=data_dir, config=config)
    ctx.ensure_dirs()

    try:
        result = collect_lane(ctx)
        print(f"Collected {result.signals_written} signals for {lane}/{run_date}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
