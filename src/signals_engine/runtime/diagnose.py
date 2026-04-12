"""Diagnose command for lane health checks."""
from dataclasses import dataclass
import json
import os
import yaml
from pathlib import Path

from ..core.defaults import resolve_config_path, resolve_data_dir
from ..sources.x.auth import default_cookie_file_path, load_auth, resolve_auth_config
from ..sources.x.browser_session import XBrowserSessionClient
from ..sources.x.client import XClient
from ..sources.x.errors import AuthError
from ..sources.x.feed.timeline import HOME_TIMELINE_OPERATION, HOME_TIMELINE_QUERY_ID

_X_LANES = {"x-feed", "x-following"}
_API_TOKEN_LANES = {"product-hunt-watch": "PH_API_TOKEN"}
_DIAGNOSE_EXTRA_VARS = {
    "latestControlAvailable": True,
    "requestContext": "launch",
    "withCommunity": True,
}


@dataclass
class DiagnoseResult:
    output: str
    exit_code: int  # 0=healthy, 1=degraded, 2=broken


def _resolve_probe_cookie_path(cookie_file: str | None) -> Path:
    cookie_path = Path(cookie_file).expanduser() if cookie_file else default_cookie_file_path()
    if cookie_path.exists():
        return cookie_path

    cookie_path_netscape = cookie_path.with_suffix(".txt")
    if cookie_path_netscape.exists():
        return cookie_path_netscape
    return cookie_path


def _probe_native_x(
    auth_config: dict | None = None,
    timeout: int = 30,
) -> tuple[str, str, int]:
    """Run a minimal X source probe for the resolved auth mode."""

    try:
        resolved_auth = resolve_auth_config(auth_config)
    except AuthError as e:
        return "", f"auth config failed: {e}", 2

    if resolved_auth.mode == "cookie-file":
        cookie_path = _resolve_probe_cookie_path(resolved_auth.cookie_file)
        cookie_path_netscape = cookie_path.with_suffix(".txt")
        if not cookie_path.exists():
            return "", f"cookie file not found: {cookie_path} or {cookie_path_netscape}", 2

        try:
            auth = load_auth(str(cookie_path))
        except AuthError as e:
            return "", f"auth validation failed: {e}", 2
        except Exception as e:
            return "", f"cookie load error: {e}", 2

        try:
            client = XClient(auth, timeout=timeout)
            raw = client.fetch_timeline_raw(
                query_id=HOME_TIMELINE_QUERY_ID,
                operation_name=HOME_TIMELINE_OPERATION,
                count=1,
                cursor=None,
                extra_variables=_DIAGNOSE_EXTRA_VARS,
            )
            return json.dumps(raw)[:200], "", 0
        except Exception as e:
            return "", f"API probe failed: {e}", 2

    try:
        client = XBrowserSessionClient(resolved_auth, timeout=timeout)
        raw = client.fetch_timeline_raw(
            query_id=HOME_TIMELINE_QUERY_ID,
            operation_name=HOME_TIMELINE_OPERATION,
            count=1,
            cursor=None,
            extra_variables=_DIAGNOSE_EXTRA_VARS,
        )
        return json.dumps(raw)[:200], "", 0
    except AuthError as e:
        return "", f"auth validation failed: {e}", 2
    except Exception as e:
        return "", f"API probe failed: {e}", 2


def _diagnose_api_token_config(lane: str, lane_cfg: dict) -> tuple[str, str]:
    """Diagnose known API-token-driven lanes without treating them as native-source lanes."""
    default_token_env = _API_TOKEN_LANES[lane]
    api_cfg = lane_cfg.get("api", {})
    config_token = str(api_cfg.get("token", "") or "").strip()
    token_env = str(api_cfg.get("token_env", default_token_env) or "").strip()

    if config_token:
        return "OK", "configured via api.token"

    if token_env and os.environ.get(token_env, "").strip():
        return "OK", f"present in ${token_env}"

    if token_env:
        return "WARN", f"missing (checked api.token and ${token_env})"

    return "WARN", "missing (checked api.token)"


def diagnose_lane(
    lane: str,
    data_dir: Path | None = None,
    config: dict | None = None,
) -> DiagnoseResult:
    """Run diagnostics for the specified lane.

    Args:
        lane: Lane name to diagnose.
        data_dir: Override data directory.
        config: Pre-loaded config dict (default: load from config file).
    """
    from ..lanes.registry import LANE_REGISTRY

    checks: list[tuple[str, str, str, str]] = []
    exit_code = 0

    # Determine data dir
    if data_dir is None:
        data_dir = resolve_data_dir()

    # Determine config
    if config is None:
        config_path = resolve_config_path()
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

        # SOURCE: mode-aware native X probe for X lanes
        source_cfg = lane_cfg.get("source", {})
        auth_cfg = dict(source_cfg.get("auth", {}))
        timeout = int(source_cfg.get("timeout_seconds", 30))

        if lane in _X_LANES:
            try:
                resolved_auth = resolve_auth_config(auth_cfg)
            except AuthError as e:
                checks.append(("SOURCE", "auth mode", "FAIL", str(e)))
                exit_code = max(exit_code, 2)
                resolved_auth = None

            if resolved_auth is not None:
                checks.append(("SOURCE", "auth mode", "OK", resolved_auth.mode))
                if resolved_auth.mode == "browser-session":
                    checks.append(("SOURCE", "cdp url", "OK", resolved_auth.cdp_url))
                else:
                    cookie_path = _resolve_probe_cookie_path(resolved_auth.cookie_file)
                    cookie_path_netscape = cookie_path.with_suffix(".txt")
                    if cookie_path.exists():
                        detail = str(cookie_path)
                        if cookie_path.suffix == ".txt":
                            detail = f"{cookie_path} (Netscape format)"
                        checks.append(("SOURCE", "cookie file", "OK", detail))
                    else:
                        checks.append(
                            ("SOURCE", "cookie file", "FAIL", f"not found: {cookie_path} or {cookie_path_netscape}")
                        )
                        exit_code = max(exit_code, 2)

                probe_out, probe_err, probe_rc = _probe_native_x(
                    auth_config=auth_cfg,
                    timeout=timeout,
                )
                if probe_rc != 0:
                    err_detail = probe_err[:200] if probe_err else "non-zero exit"
                    checks.append(("SOURCE", "native API probe", "FAIL", err_detail))
                    exit_code = max(exit_code, 2)
                else:
                    checks.append(("SOURCE", "native API probe", "OK", "API responded (auth valid, network OK)"))
        elif lane in _API_TOKEN_LANES:
            status, detail = _diagnose_api_token_config(lane, lane_cfg)
            checks.append(("SOURCE", "api token", status, detail))
        elif source_cfg:
            checks.append(("SOURCE", "source config", "OK", "configured"))
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
