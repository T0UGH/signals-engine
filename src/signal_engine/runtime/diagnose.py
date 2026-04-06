"""Diagnose command for lane health checks."""
from dataclasses import dataclass
import os
import yaml
from pathlib import Path


@dataclass
class DiagnoseResult:
    output: str
    exit_code: int  # 0=healthy, 1=degraded, 2=broken


def diagnose_lane(
    lane: str,
    data_dir: Path | None = None,
    config: dict | None = None,
) -> DiagnoseResult:
    """Run diagnostics for the specified lane.

    Args:
        lane: Lane name to diagnose.
        data_dir: Override data directory (default: from env or ~/.daily-lane-data).
        config: Pre-loaded config dict (default: load from config file).
    """
    from ..lanes.registry import LANE_REGISTRY

    checks: list[tuple[str, str, str, str]] = []
    exit_code = 0

    # Determine data dir
    if data_dir is None:
        data_dir = Path(os.environ.get(
            "DAILY_LANE_DATA_DIR",
            str(Path.home() / ".daily-lane-data")
        ))

    # Determine config
    if config is None:
        config_path = os.environ.get(
            "DAILY_LANE_CONFIG",
            str(Path.home() / ".daily-lane" / "config" / "lanes.yaml")
        )
        if Path(config_path).exists():
            try:
                with open(config_path) as f:
                    config = yaml.safe_load(f)
            except Exception:
                config = None

    # SYSTEM: lane registry check
    if lane not in LANE_REGISTRY:
        checks.append(("SYSTEM", "lane registered", "FAIL", f"'{lane}' not in LANE_REGISTRY"))
        exit_code = max(exit_code, 2)
    else:
        checks.append(("SYSTEM", "lane registered", "OK", lane))

    # CONFIG check
    if config is None:
        checks.append(("CONFIG", "config file", "FAIL", "config not loaded"))
        exit_code = max(exit_code, 2)
    elif lane not in config.get("lanes", {}):
        checks.append(("CONFIG", "lane in config", "FAIL", f"'{lane}' not in lanes.yaml"))
        exit_code = max(exit_code, 2)
    else:
        lane_cfg = config["lanes"][lane]
        enabled = lane_cfg.get("enabled", True)
        checks.append(("CONFIG", "lane in config", "OK", f"{lane} (enabled={enabled})"))

        # SOURCE: opencli binary check (for opencli-based lanes)
        opencli_cfg = lane_cfg.get("opencli", {})
        opencli_path = opencli_cfg.get("path", "~/.openclaw/workspace/github/opencli")
        opencli_path_expanded = Path(opencli_path).expanduser()
        main_js = opencli_path_expanded / "dist" / "main.js"

        if not main_js.exists():
            checks.append(("SOURCE", "opencli binary", "FAIL", f"not found: {main_js}"))
            exit_code = max(exit_code, 2)
        else:
            checks.append(("SOURCE", "opencli binary", "OK", str(main_js)))

    # ENVIRONMENT check
    signals_dir = data_dir / "signals"
    if not signals_dir.exists():
        try:
            signals_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            checks.append(("ENVIRONMENT", "signals dir", "FAIL", f"cannot create: {e}"))
            exit_code = max(exit_code, 2)
            signals_dir = None

    if signals_dir and signals_dir.exists():
        checks.append(("ENVIRONMENT", "signals dir", "OK", str(signals_dir)))

    # OUTPUT check
    if signals_dir and signals_dir.exists():
        lane_dir = signals_dir / lane
        if lane_dir.exists():
            checks.append(("OUTPUT", "lane output dir", "OK", f"{lane}/ exists"))
        else:
            checks.append(("OUTPUT", "lane output dir", "WARN", f"{lane}/ not yet created"))

    # Render output
    section_order = ["SYSTEM", "CONFIG", "SOURCE", "ENVIRONMENT", "OUTPUT"]
    sections: dict[str, list[tuple[str, str, str]]] = {s: [] for s in section_order}
    for section, name, status, detail in checks:
        if section in sections:
            sections[section].append((name, status, detail))

    lines = ["[signal-engine diagnose]", ""]
    for section in section_order:
        rows = sections[section]
        if not rows:
            continue
        lines.append(section)
        for name, status, detail in rows:
            if status == "OK":
                icon = "OK"
            elif status == "FAIL":
                icon = "FAIL"
            else:
                icon = "WARN"
            lines.append(f"  [{icon}] {name}: {detail}")
        lines.append("")

    overall = "HEALTHY" if exit_code == 0 else "DEGRADED" if exit_code == 1 else "BROKEN"
    lines.append(f"SUMMARY\n- overall: {overall}")

    return DiagnoseResult(output="\n".join(lines), exit_code=exit_code)
