"""Diagnose command for lane health checks."""
from dataclasses import dataclass
import json
import os
import yaml
from pathlib import Path


@dataclass
class DiagnoseResult:
    output: str
    exit_code: int  # 0=healthy, 1=degraded, 2=broken


def _probe_native_x(timeout: int = 30) -> tuple[str, str, int]:
    """Run a minimal native X source probe.

    Validates cookie file can be loaded and makes a single lightweight
    GraphQL request to verify authentication + API connectivity.

    Returns:
        (stdout, stderr, returncode) — returncode 0 = healthy
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    try:
        from signals_engine.sources.x.auth import load_auth, AuthError
        from signals_engine.sources.x.client import XClient
    except Exception as e:
        return "", f"import failed: {e}", 2

    # Check cookie file exists
    cookie_path = Path.home() / ".signal-engine" / "x-cookies.json"
    if not cookie_path.exists():
        cookie_path_netscape = Path.home() / ".signal-engine" / "x-cookies.txt"
        if not cookie_path_netscape.exists():
            return "", f"cookie file not found: {cookie_path} or {cookie_path_netscape}", 2
        cookie_path = cookie_path_netscape

    # Load auth
    try:
        auth = load_auth(str(cookie_path))
    except AuthError as e:
        return "", f"auth validation failed: {e}", 2
    except Exception as e:
        return "", f"cookie load error: {e}", 2

    # Make a single lightweight API call
    try:
        client = XClient(auth, timeout=timeout)
        # Fetch just 1 tweet with minimal variables
        raw = client.fetch_timeline_raw(limit=1, cursor=None)
        return json.dumps(raw)[:200], "", 0
    except Exception as e:
        return "", f"API probe failed: {e}", 2


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

        # SOURCE: native X probe for x-feed, opencli for other lanes
        source_cfg = lane_cfg.get("source", {})

        if source_cfg or lane == "x-feed":
            # Native source probe (x-feed uses source config)
            cookie_cfg = source_cfg.get("auth", {}).get("cookie_file")
            cookie_path = Path(cookie_cfg).expanduser() if cookie_cfg else Path.home() / ".signal-engine" / "x-cookies.json"
            if cookie_path.exists():
                checks.append(("SOURCE", "cookie file", "OK", str(cookie_path)))
            else:
                cookie_alt = cookie_path.with_suffix(".txt")
                if cookie_alt.exists():
                    checks.append(("SOURCE", "cookie file", "OK", f"{cookie_alt} (Netscape format)"))
                else:
                    checks.append(("SOURCE", "cookie file", "WARN", f"not found (will use default path at runtime)"))
                    cookie_path = None

            if cookie_path and cookie_path.exists():
                probe_out, probe_err, probe_rc = _probe_native_x(timeout=30)
                if probe_rc != 0:
                    err_detail = probe_err[:200] if probe_err else "non-zero exit"
                    checks.append(("SOURCE", "native API probe", "FAIL", err_detail))
                    exit_code = max(exit_code, 2)
                else:
                    checks.append(("SOURCE", "native API probe", "OK", "API responded (auth valid, network OK)"))
            elif cookie_path is None:
                checks.append(("SOURCE", "native API probe", "WARN", "cookie file not found, skipping API probe"))
        else:
            # Lane has no native source config
            checks.append(("SOURCE", "source config", "WARN", "no native source configured for this lane"))

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
