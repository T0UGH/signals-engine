"""Weather source helpers backed by the Open-Meteo forecast API."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "signals-engine/0.1 weather-watch"
DAILY_FIELDS = (
    "weather_code,"
    "temperature_2m_min,"
    "temperature_2m_max,"
    "precipitation_probability_max,"
    "precipitation_sum,"
    "wind_speed_10m_max,"
    "wind_direction_10m_dominant"
)

WEATHER_CODE_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


@dataclass
class DailyWeatherForecast:
    forecast_date: str
    weather_code: int
    weather_description: str
    temperature_min_c: float
    temperature_max_c: float
    precipitation_probability_max: float | None = None
    precipitation_sum_mm: float | None = None
    wind_speed_10m_max_kmh: float | None = None
    wind_direction_10m_dominant_deg: float | None = None
    source_url: str = ""


class WeatherSourceError(RuntimeError):
    """Raised when weather data retrieval or parsing fails."""


def describe_weather_code(code: int) -> str:
    """Return a readable description for an Open-Meteo WMO weather code."""
    return WEATHER_CODE_DESCRIPTIONS.get(int(code), f"Weather code {code}")


def build_forecast_url(
    *,
    latitude: float,
    longitude: float,
    timezone: str,
    forecast_date: str,
) -> str:
    """Build a stable Open-Meteo forecast URL for one daily forecast row."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": DAILY_FIELDS,
        "timezone": timezone,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "start_date": forecast_date,
        "end_date": forecast_date,
    }
    return f"{OPEN_METEO_FORECAST_URL}?{urlencode(params)}"


def fetch_daily_weather(
    *,
    latitude: float,
    longitude: float,
    timezone: str,
    forecast_date: str,
    timeout: int = 15,
) -> DailyWeatherForecast:
    """Fetch one daily weather forecast row from Open-Meteo."""
    url = build_forecast_url(
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        forecast_date=forecast_date,
    )
    payload = _request_json(url, timeout=timeout)
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise WeatherSourceError("Open-Meteo response missing daily forecast data")

    dates = _string_series(daily, "time")
    try:
        index = dates.index(forecast_date)
    except ValueError as exc:
        raise WeatherSourceError(f"Open-Meteo response did not include forecast date {forecast_date}") from exc

    weather_code = _series_value(daily, "weather_code", index, int)
    return DailyWeatherForecast(
        forecast_date=dates[index],
        weather_code=weather_code,
        weather_description=describe_weather_code(weather_code),
        temperature_min_c=_series_value(daily, "temperature_2m_min", index, float),
        temperature_max_c=_series_value(daily, "temperature_2m_max", index, float),
        precipitation_probability_max=_optional_series_value(daily, "precipitation_probability_max", index),
        precipitation_sum_mm=_optional_series_value(daily, "precipitation_sum", index),
        wind_speed_10m_max_kmh=_optional_series_value(daily, "wind_speed_10m_max", index),
        wind_direction_10m_dominant_deg=_optional_series_value(daily, "wind_direction_10m_dominant", index),
        source_url=url,
    )


def _request_json(url: str, *, timeout: int) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise WeatherSourceError(f"HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise WeatherSourceError(f"request failed for {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise WeatherSourceError(f"invalid JSON from {url}") from exc

    if not isinstance(payload, dict):
        raise WeatherSourceError("Open-Meteo response must be a JSON object")
    return payload


def _string_series(payload: dict[str, Any], key: str) -> list[str]:
    values = payload.get(key)
    if not isinstance(values, list) or not values:
        raise WeatherSourceError(f"Open-Meteo response missing daily '{key}' values")
    return [str(value) for value in values]


def _series_value(payload: dict[str, Any], key: str, index: int, coerce: type[int] | type[float]) -> int | float:
    values = payload.get(key)
    if not isinstance(values, list) or len(values) <= index:
        raise WeatherSourceError(f"Open-Meteo response missing daily '{key}' values")
    value = values[index]
    if value is None:
        raise WeatherSourceError(f"Open-Meteo response returned null for daily '{key}'")
    try:
        return coerce(value)
    except (TypeError, ValueError) as exc:
        raise WeatherSourceError(f"Open-Meteo response returned invalid '{key}' value: {value!r}") from exc


def _optional_series_value(payload: dict[str, Any], key: str, index: int) -> float | None:
    values = payload.get(key)
    if not isinstance(values, list) or len(values) <= index:
        return None
    value = values[index]
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherSourceError(f"Open-Meteo response returned invalid '{key}' value: {value!r}") from exc
