"""weather-watch lane collector."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from ..core import RunContext, RunResult, RunStatus, SignalRecord
from ..core.debuglog import debug_log
from ..runtime.run_manifest import write_run_manifest
from ..signals.index import write_index
from ..signals.writer import write_signal
from ..sources.weather import DailyWeatherForecast, WeatherSourceError, fetch_daily_weather
from .registry import register_lane


DEFAULT_LATITUDE = 39.9593
DEFAULT_LONGITUDE = 116.2981
DEFAULT_LOCATION_NAME = "北京·海淀"
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_ENTITY_ID = "beijing-haidian"


def _parse_coordinate(value: object, *, field_name: str, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"weather-watch '{field_name}' must be a number") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(
            f"weather-watch '{field_name}' must be between {minimum:g} and {maximum:g}"
        )
    return parsed


def _normalize_location_name(value: object) -> str:
    location_name = str(value or "").strip()
    if not location_name:
        raise ValueError("weather-watch 'location_name' must be a non-empty string")
    return location_name


def _normalize_timezone(value: object) -> str:
    timezone_name = str(value or "").strip()
    if not timezone_name:
        raise ValueError("weather-watch 'timezone' must be a non-empty string")
    return timezone_name


def _location_entity_id(location_name: str, latitude: float, longitude: float) -> str:
    if (
        location_name == DEFAULT_LOCATION_NAME
        and abs(latitude - DEFAULT_LATITUDE) < 0.0001
        and abs(longitude - DEFAULT_LONGITUDE) < 0.0001
    ):
        return DEFAULT_ENTITY_ID

    ascii_text = (
        unicodedata.normalize("NFKD", location_name).encode("ascii", "ignore").decode("ascii").lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if slug:
        return slug

    lat_token = f"{latitude:.4f}".replace(".", "_").replace("-", "neg_")
    lon_token = f"{longitude:.4f}".replace(".", "_").replace("-", "neg_")
    return f"lat-{lat_token}-lon-{lon_token}"


def _format_number(value: float | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _compass_direction(degrees: float | None) -> str:
    if degrees is None:
        return ""
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    index = int(((degrees % 360) + 22.5) // 45) % len(directions)
    return directions[index]


def _precipitation_summary(forecast: DailyWeatherForecast) -> str:
    parts: list[str] = []
    if forecast.precipitation_probability_max is not None:
        parts.append(f"{_format_number(forecast.precipitation_probability_max)}% chance")
    if forecast.precipitation_sum_mm is not None:
        parts.append(f"{_format_number(forecast.precipitation_sum_mm)} mm")
    return ", ".join(parts)


def _wind_summary(forecast: DailyWeatherForecast) -> str:
    if forecast.wind_speed_10m_max_kmh is None:
        return ""
    parts = [f"up to {_format_number(forecast.wind_speed_10m_max_kmh)} km/h"]
    direction = _compass_direction(forecast.wind_direction_10m_dominant_deg)
    if direction:
        degrees = _format_number(forecast.wind_direction_10m_dominant_deg)
        parts.append(f"{direction} ({degrees}°)")
    return " ".join(parts)


def _text_preview(forecast: DailyWeatherForecast) -> str:
    parts = [
        forecast.weather_description,
        f"{_format_number(forecast.temperature_min_c)}°C to {_format_number(forecast.temperature_max_c)}°C",
    ]
    precipitation = _precipitation_summary(forecast)
    if precipitation:
        parts.append(f"Precipitation {precipitation}")
    wind = _wind_summary(forecast)
    if wind:
        parts.append(f"Wind {wind}")
    return ". ".join(parts) + "."


def _body_markdown(location_name: str, forecast: DailyWeatherForecast) -> str:
    lines = [
        "## Daily Weather",
        "",
        f"- Date: {forecast.forecast_date}",
        f"- Location: {location_name}",
        f"- Condition: {forecast.weather_description}",
        (
            f"- Temperature: {_format_number(forecast.temperature_min_c)}°C "
            f"to {_format_number(forecast.temperature_max_c)}°C"
        ),
    ]
    precipitation = _precipitation_summary(forecast)
    if precipitation:
        lines.append(f"- Precipitation: {precipitation}")
    wind = _wind_summary(forecast)
    if wind:
        lines.append(f"- Wind: {wind}")
    lines.extend(["", f"- Source: {forecast.source_url}"])
    return "\n".join(lines)


def _build_signal(
    ctx: RunContext,
    *,
    location_name: str,
    latitude: float,
    longitude: float,
    forecast: DailyWeatherForecast,
) -> SignalRecord:
    entity_id = _location_entity_id(location_name, latitude, longitude)
    filename = f"{entity_id}__daily_weather__{ctx.date}.md"
    file_path = str(ctx.signals_dir / filename)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    title = (
        f"{location_name} {forecast.forecast_date} weather: "
        f"{forecast.weather_description}, "
        f"{_format_number(forecast.temperature_min_c)}°C to {_format_number(forecast.temperature_max_c)}°C"
    )
    record = SignalRecord(
        lane="weather-watch",
        signal_type="daily_weather",
        source="weather",
        entity_type="location",
        entity_id=entity_id,
        title=title,
        source_url=forecast.source_url,
        fetched_at=fetched_at,
        file_path=file_path,
        created_at=forecast.forecast_date,
        text_preview=_text_preview(forecast),
        group=location_name,
        query=forecast.weather_description,
        top_comments_text=_body_markdown(location_name, forecast),
    )
    write_signal(record)
    return record


def collect_weather_watch(ctx: RunContext) -> RunResult:
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    lane_config = ctx.config.get("lanes", {}).get("weather-watch", {})
    if not isinstance(lane_config, dict):
        ctx.errors.append("weather-watch config must be a mapping")
        return _finalize(ctx, started_at, [], 0)

    try:
        latitude = _parse_coordinate(
            lane_config.get("latitude", DEFAULT_LATITUDE),
            field_name="latitude",
            minimum=-90.0,
            maximum=90.0,
        )
        longitude = _parse_coordinate(
            lane_config.get("longitude", DEFAULT_LONGITUDE),
            field_name="longitude",
            minimum=-180.0,
            maximum=180.0,
        )
        location_name = _normalize_location_name(lane_config.get("location_name", DEFAULT_LOCATION_NAME))
        timezone_name = _normalize_timezone(lane_config.get("timezone", DEFAULT_TIMEZONE))
    except ValueError as exc:
        ctx.errors.append(str(exc))
        return _finalize(ctx, started_at, [], 0)

    ctx.ensure_dirs()
    debug_log(
        (
            "[weather-watch] START "
            f"location={location_name} latitude={latitude} longitude={longitude} timezone={timezone_name}"
        ),
        log_file=ctx.debug_log_path,
    )

    try:
        forecast = fetch_daily_weather(
            latitude=latitude,
            longitude=longitude,
            timezone=timezone_name,
            forecast_date=ctx.date,
        )
    except WeatherSourceError as exc:
        ctx.errors.append(str(exc))
        return _finalize(ctx, started_at, [], 1)

    records: list[SignalRecord] = []
    try:
        records.append(
            _build_signal(
                ctx,
                location_name=location_name,
                latitude=latitude,
                longitude=longitude,
                forecast=forecast,
            )
        )
    except Exception as exc:
        ctx.errors.append(f"failed to write daily weather signal: {exc}")

    return _finalize(ctx, started_at, records, 1)


def _finalize(ctx: RunContext, started_at: str, records: list[SignalRecord], locations_checked: int) -> RunResult:
    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    signal_types_count: dict[str, int] = {}
    for record in records:
        signal_types_count[record.signal_type] = signal_types_count.get(record.signal_type, 0) + 1

    status = RunStatus.SUCCESS if records else RunStatus.EMPTY
    if ctx.errors:
        status = RunStatus.FAILED

    result = RunResult(
        lane="weather-watch",
        date=ctx.date,
        status=status,
        started_at=started_at,
        session_id=None,
        finished_at=finished_at,
        warnings=ctx.warnings,
        errors=ctx.errors,
        signal_records=records,
        repos_checked=locations_checked,
        signals_written=len(records),
        signal_types_count=signal_types_count,
        index_file=str(ctx.index_path),
    )
    _write_index_to_file(result, ctx.index_path)
    _write_manifest_to_file(result, ctx.run_json_path)
    debug_log(
        f"[weather-watch] END signals={len(records)} locations={locations_checked}",
        log_file=ctx.debug_log_path,
    )
    return result


def _write_index_to_file(result: RunResult, index_path: Path) -> bool:
    try:
        write_index(result, index_path)
        return True
    except Exception as exc:
        result.errors.append(f"failed to write index.md: {exc}")
        result.status = RunStatus.FAILED
        return False


def _write_manifest_to_file(result: RunResult, run_json_path: Path) -> bool:
    try:
        write_run_manifest(result, run_json_path)
        return True
    except Exception as exc:
        result.errors.append(f"failed to write run.json: {exc}")
        result.status = RunStatus.FAILED
        return False


register_lane("weather-watch", collect_weather_watch)
