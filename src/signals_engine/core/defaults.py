"""Default config and data path resolution."""
from collections.abc import Mapping
import os
from pathlib import Path


SIGNALS_ENGINE_CONFIG_ENV = "SIGNALS_ENGINE_CONFIG"
DAILY_LANE_CONFIG_ENV = "DAILY_LANE_CONFIG"
SIGNALS_ENGINE_DATA_DIR_ENV = "SIGNALS_ENGINE_DATA_DIR"
DAILY_LANE_DATA_DIR_ENV = "DAILY_LANE_DATA_DIR"


def default_config_path(home: Path | None = None) -> Path:
    """Return the primary config path."""
    home_dir = home or Path.home()
    return home_dir / ".signal-engine" / "config" / "lanes.yaml"


def legacy_config_path(home: Path | None = None) -> Path:
    """Return the legacy config path."""
    home_dir = home or Path.home()
    return home_dir / ".daily-lane" / "config" / "lanes.yaml"


def default_data_dir(home: Path | None = None) -> Path:
    """Return the primary data directory."""
    home_dir = home or Path.home()
    return home_dir / ".signal-engine" / "data"


def legacy_data_dir(home: Path | None = None) -> Path:
    """Return the legacy data directory."""
    home_dir = home or Path.home()
    return home_dir / ".daily-lane-data"


def _resolve_path(
    explicit_path: str | Path | None,
    *,
    env: Mapping[str, str] | None,
    primary_env_name: str,
    legacy_env_name: str,
    primary_default: Path,
    legacy_default: Path,
) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser()

    environment = os.environ if env is None else env

    primary_env_path = environment.get(primary_env_name)
    if primary_env_path:
        return Path(primary_env_path).expanduser()

    legacy_env_path = environment.get(legacy_env_name)
    if legacy_env_path:
        return Path(legacy_env_path).expanduser()

    if primary_default.exists() or not legacy_default.exists():
        return primary_default

    return legacy_default


def resolve_config_path(
    config_path: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve config path with primary and legacy compatibility fallbacks."""
    return _resolve_path(
        config_path,
        env=env,
        primary_env_name=SIGNALS_ENGINE_CONFIG_ENV,
        legacy_env_name=DAILY_LANE_CONFIG_ENV,
        primary_default=default_config_path(home),
        legacy_default=legacy_config_path(home),
    )


def resolve_data_dir(
    data_dir: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve data directory with primary and legacy compatibility fallbacks."""
    return _resolve_path(
        data_dir,
        env=env,
        primary_env_name=SIGNALS_ENGINE_DATA_DIR_ENV,
        legacy_env_name=DAILY_LANE_DATA_DIR_ENV,
        primary_default=default_data_dir(home),
        legacy_default=legacy_data_dir(home),
    )
