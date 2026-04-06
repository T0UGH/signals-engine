"""Diagnose command for lane health checks."""
from dataclasses import dataclass
import os
import yaml
from pathlib import Path


@dataclass
class DiagnoseResult:
    output: str
    exit_code: int  # 0=healthy, 1=degraded, 2=broken


def diagnose_lane(lane: str) -> DiagnoseResult:
    """Run diagnostics for the specified lane."""
    from ..lanes.registry import LANE_REGISTRY

    if lane not in LANE_REGISTRY:
        return DiagnoseResult(output=f"ERROR: unknown lane '{lane}'", exit_code=2)

    checks = []
    exit_code = 0

    # CONFIG check
    config_path = os.environ.get(
        "DAILY_LANE_CONFIG",
        str(Path.home() / ".daily-lane" / "config" / "lanes.yaml")
    )
    if not Path(config_path).exists():
        checks.append(("CONFIG", "config file", "FAIL", f"not found: {config_path}"))
        exit_code = max(exit_code, 2)
    else:
        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)
            if lane in data.get("lanes", {}):
                checks.append(("CONFIG", "lane config", "OK", lane))
            else:
                checks.append(("CONFIG", "lane config", "FAIL", f"lane '{lane}' not in config"))
                exit_code = max(exit_code, 2)
        except Exception as e:
            checks.append(("CONFIG", "config parse", "FAIL", str(e)))
            exit_code = max(exit_code, 2)

    # OUTPUT DIR check
    data_dir = Path(os.environ.get(
        "DAILY_LANE_DATA_DIR",
        str(Path.home() / ".daily-lane-data")
    ))
    lane_dir = data_dir / "signals" / lane
    if not lane_dir.parent.exists():
        checks.append(("ENVIRONMENT", "data dir", "FAIL", f"parent not writable: {lane_dir.parent}"))
        exit_code = max(exit_code, 2)
    else:
        checks.append(("ENVIRONMENT", "data dir", "OK", str(data_dir)))

    # Render output
    lines = ["[signal-engine diagnose]", "", "CONFIG"]
    current_section = "CONFIG"
    for section, name, status, detail in checks:
        if section != current_section:
            lines.append(f"\n{current_section.upper()}")
            current_section = section
        lines.append(f"- {name}: {status} ({detail})")

    summary = "HEALTHY" if exit_code == 0 else "DEGRADED" if exit_code == 1 else "BROKEN"
    lines.extend(["", "SUMMARY", f"- overall: {summary}"])

    return DiagnoseResult(output="\n".join(lines), exit_code=exit_code)
