"""diagnose command."""
import argparse
from pathlib import Path

import yaml

from ..core.defaults import resolve_config_path, resolve_data_dir


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("diagnose", help="Run diagnostics for a lane")
    p.add_argument("--lane", required=True, help="Lane name")
    p.add_argument("--data-dir", default=None, help="Data directory path")
    p.add_argument("--config", default=None, help="Config file path")
    p.add_argument(
        "--debug-log",
        default=None,
        help="Path to debug log file (default: <data-dir>/debug.log)",
    )
    return p


def run(args: argparse.Namespace) -> int:
    """Execute the diagnose command."""
    import sys
    from ..core.debuglog import debug_log
    from ..runtime.diagnose import diagnose_lane

    data_dir = resolve_data_dir(args.data_dir) if args.data_dir else None
    debug_log_path = None
    if args.debug_log:
        debug_log_path = Path(args.debug_log)
    elif data_dir:
        debug_log_path = data_dir / "debug.log"

    config = None
    config_path = resolve_config_path(args.config)
    if Path(config_path).exists():
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
        except Exception:
            pass

    debug_log(f"[diagnose] START lane={args.lane} data_dir={data_dir}", log_file=debug_log_path)

    try:
        result = diagnose_lane(args.lane, data_dir=data_dir, config=config)
        debug_log(f"[diagnose] END exit_code={result.exit_code}", log_file=debug_log_path)
        print(result.output, file=sys.stdout)
        return 0 if result.exit_code == 0 else 1
    except Exception as e:
        debug_log(f"[diagnose] EXCEPTION: {e}", log_file=debug_log_path)
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
