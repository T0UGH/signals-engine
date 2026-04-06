"""collect command."""
import argparse
import os
from pathlib import Path

from ..core import RunContext, ConfigError, RunStatus


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("collect", help="Collect signals for a lane")
    p.add_argument("--lane", required=True, help="Lane name (e.g. x-feed)")
    p.add_argument("--date", default=None, help="Date in YYYY-MM-DD format (default: today)")
    p.add_argument("--data-dir", default=None, help="Data directory path")
    p.add_argument("--config", default=None, help="Config file path")
    p.add_argument(
        "--debug-log",
        default=None,
        help="Path to debug log file (default: <data-dir>/debug.log)",
    )
    return p


def load_config(config_path: str | None) -> dict:
    """Load lanes config from yaml."""
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
        import yaml
        return yaml.safe_load(f)


def run(args: argparse.Namespace) -> int:
    """Execute the collect command.

    Exit codes:
        0 = SUCCESS or EMPTY (normal completion)
        1 = FAILED or exception
    """
    import sys
    from datetime import date
    from ..core.debuglog import debug_log
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

    # Debug log path
    if args.debug_log:
        debug_log_path = Path(args.debug_log)
    else:
        debug_log_path = data_dir / "debug.log"

    config = load_config(args.config)
    ctx = RunContext(
        lane=lane,
        date=run_date,
        data_dir=data_dir,
        config=config,
        debug_log_path=debug_log_path,
    )
    ctx.ensure_dirs()

    debug_log(f"[collect] START lane={lane} date={run_date} data_dir={data_dir}", log_file=debug_log_path)

    try:
        result = collect_lane(ctx)
        debug_log(
            f"[collect] END status={result.status.value} signals={result.signals_written} "
            f"session={result.session_id or 'n/a'}",
            log_file=debug_log_path,
        )
        if result.errors:
            for err in result.errors:
                debug_log(f"[collect] ERROR: {err}", log_file=debug_log_path)

        print(
            f"[{result.status.value}] {lane}/{run_date}: "
            f"{result.signals_written} signals, "
            f"session={result.session_id or 'n/a'}",
            file=sys.stderr,
        )
        if result.errors:
            for err in result.errors:
                print(f"  ERROR: {err}", file=sys.stderr)

        # Exit code: 0 for SUCCESS/EMPTY, 1 for FAILED
        return 0 if result.status in (RunStatus.SUCCESS, RunStatus.EMPTY) else 1

    except Exception as e:
        debug_log(f"[collect] EXCEPTION: {e}", log_file=debug_log_path)
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
