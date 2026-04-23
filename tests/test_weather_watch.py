"""Tests for weather-watch lane and weather source integration."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from signals_engine.core import RunContext, RunStatus


class TestWeatherWatchLane(unittest.TestCase):
    def _make_ctx(self, tmp_dir: str, lane_config: dict | None = None) -> RunContext:
        ctx = RunContext(
            lane="weather-watch",
            date="2026-04-18",
            data_dir=Path(tmp_dir),
            config={"lanes": {"weather-watch": lane_config or {}}},
        )
        ctx.ensure_dirs()
        return ctx

    @patch("signals_engine.lanes.weather_watch.fetch_daily_weather")
    def test_collect_rejects_invalid_numeric_config(self, mock_fetch):
        from signals_engine.lanes.weather_watch import collect_weather_watch

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp, {"latitude": "north"})
            result = collect_weather_watch(ctx)

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertEqual(result.signals_written, 0)
        self.assertTrue(any("latitude" in err for err in result.errors))
        mock_fetch.assert_not_called()

    @patch("signals_engine.lanes.weather_watch.fetch_daily_weather")
    def test_collect_uses_defaults_when_config_missing(self, mock_fetch):
        from signals_engine.lanes.weather_watch import collect_weather_watch
        from signals_engine.sources.weather import DailyWeatherForecast

        mock_fetch.side_effect = [
            DailyWeatherForecast(
                forecast_date="2026-04-18",
                weather_code=1,
                weather_description="Mainly clear",
                temperature_min_c=11.0,
                temperature_max_c=24.0,
                precipitation_probability_max=10.0,
                precipitation_sum_mm=0.0,
                wind_speed_10m_max_kmh=14.0,
                wind_direction_10m_dominant_deg=135,
                source_url="https://api.open-meteo.com/v1/forecast?mock=beijing",
            ),
            DailyWeatherForecast(
                forecast_date="2026-04-18",
                weather_code=3,
                weather_description="Overcast",
                temperature_min_c=14.0,
                temperature_max_c=22.0,
                precipitation_probability_max=20.0,
                precipitation_sum_mm=0.4,
                wind_speed_10m_max_kmh=16.0,
                wind_direction_10m_dominant_deg=90,
                source_url="https://api.open-meteo.com/v1/forecast?mock=shanghai",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp, {})
            result = collect_weather_watch(ctx)

        self.assertEqual(result.status, RunStatus.SUCCESS)
        self.assertEqual(result.signals_written, 2)
        self.assertEqual(result.repos_checked, 2)
        self.assertEqual(
            [record.entity_id for record in result.signal_records],
            ["beijing-haidian", "shanghai-yangpu"],
        )
        self.assertIn("北京·海淀", result.signal_records[0].title)
        self.assertIn("上海·杨浦", result.signal_records[1].title)
        self.assertEqual(
            mock_fetch.call_args_list[0].kwargs,
            {
                "latitude": 39.9593,
                "longitude": 116.2981,
                "timezone": "Asia/Shanghai",
                "forecast_date": "2026-04-18",
            },
        )
        self.assertEqual(
            mock_fetch.call_args_list[1].kwargs,
            {
                "latitude": 31.2598,
                "longitude": 121.5257,
                "timezone": "Asia/Shanghai",
                "forecast_date": "2026-04-18",
            },
        )

    @patch("signals_engine.lanes.weather_watch.fetch_daily_weather")
    def test_collect_supports_multiple_locations(self, mock_fetch):
        from signals_engine.lanes.weather_watch import collect_weather_watch
        from signals_engine.sources.weather import DailyWeatherForecast

        mock_fetch.side_effect = [
            DailyWeatherForecast(
                forecast_date="2026-04-18",
                weather_code=0,
                weather_description="Clear sky",
                temperature_min_c=11.0,
                temperature_max_c=24.0,
                precipitation_probability_max=0.0,
                precipitation_sum_mm=0.0,
                wind_speed_10m_max_kmh=10.0,
                wind_direction_10m_dominant_deg=180,
                source_url="https://api.open-meteo.com/v1/forecast?mock=beijing",
            ),
            DailyWeatherForecast(
                forecast_date="2026-04-18",
                weather_code=3,
                weather_description="Overcast",
                temperature_min_c=14.0,
                temperature_max_c=22.0,
                precipitation_probability_max=20.0,
                precipitation_sum_mm=0.4,
                wind_speed_10m_max_kmh=16.0,
                wind_direction_10m_dominant_deg=90,
                source_url="https://api.open-meteo.com/v1/forecast?mock=shanghai",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(
                tmp,
                {
                    "locations": [
                        {
                            "location_name": "北京·海淀",
                            "latitude": 39.9593,
                            "longitude": 116.2981,
                            "timezone": "Asia/Shanghai",
                        },
                        {
                            "entity_id": "shanghai-yangpu",
                            "location_name": "上海·杨浦",
                            "latitude": 31.2598,
                            "longitude": 121.5257,
                            "timezone": "Asia/Shanghai",
                        },
                    ]
                },
            )
            result = collect_weather_watch(ctx)

            self.assertEqual(result.status, RunStatus.SUCCESS)
            self.assertEqual(result.signals_written, 2)
            self.assertEqual(result.repos_checked, 2)
            self.assertEqual([record.entity_id for record in result.signal_records], ["beijing-haidian", "shanghai-yangpu"])
            self.assertTrue(all(Path(record.file_path).exists() for record in result.signal_records))

        self.assertEqual(mock_fetch.call_count, 2)
        self.assertEqual(
            mock_fetch.call_args_list[1].kwargs,
            {
                "latitude": 31.2598,
                "longitude": 121.5257,
                "timezone": "Asia/Shanghai",
                "forecast_date": "2026-04-18",
            },
        )

    @patch("signals_engine.lanes.weather_watch.fetch_daily_weather")
    def test_collect_writes_one_daily_weather_signal(self, mock_fetch):
        from signals_engine.lanes.weather_watch import collect_weather_watch
        from signals_engine.sources.weather import DailyWeatherForecast

        mock_fetch.return_value = DailyWeatherForecast(
            forecast_date="2026-04-18",
            weather_code=3,
            weather_description="Overcast",
            temperature_min_c=12.1,
            temperature_max_c=24.8,
            precipitation_probability_max=40.0,
            precipitation_sum_mm=1.2,
            wind_speed_10m_max_kmh=18.4,
            wind_direction_10m_dominant_deg=45,
            source_url="https://api.open-meteo.com/v1/forecast?mock=1",
        )

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(tmp, {"location_name": "北京·海淀"})
            result = collect_weather_watch(ctx)

            self.assertEqual(result.status, RunStatus.SUCCESS)
            self.assertEqual(result.signals_written, 1)
            self.assertEqual(result.repos_checked, 1)

            record = result.signal_records[0]
            self.assertTrue(Path(record.file_path).exists())
            body = Path(record.file_path).read_text(encoding="utf-8")

        self.assertEqual(record.lane, "weather-watch")
        self.assertEqual(record.signal_type, "daily_weather")
        self.assertEqual(record.source, "weather")
        self.assertEqual(record.entity_type, "location")
        self.assertEqual(record.entity_id, "beijing-haidian")
        self.assertEqual(record.created_at, "2026-04-18")
        self.assertEqual(record.source_url, "https://api.open-meteo.com/v1/forecast?mock=1")
        self.assertIn("北京·海淀", record.title)
        self.assertIn("Overcast", record.title)
        self.assertIn("12.1", record.text_preview)
        self.assertIn("24.8", record.text_preview)
        self.assertIn("40%", record.text_preview)
        self.assertIn("## Daily Weather", body)
        self.assertIn("- Date: 2026-04-18", body)
        self.assertIn("- Location: 北京·海淀", body)
        self.assertIn("- Condition: Overcast", body)
        self.assertIn("- Temperature: 12.1°C to 24.8°C", body)
        self.assertIn("- Precipitation: 40% chance, 1.2 mm", body)
        self.assertIn("- Wind: up to 18.4 km/h", body)

    @patch("signals_engine.sources.weather.fetch_daily_weather")
    def test_collect_lane_registers_weather_watch_without_direct_module_import(self, mock_fetch):
        from signals_engine.lanes.registry import LANE_REGISTRY
        from signals_engine.runtime.collect import collect_lane
        from signals_engine.sources.weather import DailyWeatherForecast

        mock_fetch.return_value = DailyWeatherForecast(
            forecast_date="2026-04-18",
            weather_code=0,
            weather_description="Clear sky",
            temperature_min_c=9.0,
            temperature_max_c=23.0,
            precipitation_probability_max=0.0,
            precipitation_sum_mm=0.0,
            wind_speed_10m_max_kmh=8.0,
            wind_direction_10m_dominant_deg=180,
            source_url="https://api.open-meteo.com/v1/forecast?mock=1",
        )

        previous_module = sys.modules.pop("signals_engine.lanes.weather_watch", None)
        previous_collector = LANE_REGISTRY["weather-watch"]
        LANE_REGISTRY["weather-watch"] = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_ctx(tmp, {})
                result = collect_lane(ctx)

            self.assertEqual(result.status, RunStatus.SUCCESS)
            self.assertEqual(result.signals_written, 2)
            self.assertIsNotNone(LANE_REGISTRY["weather-watch"])
        finally:
            if previous_module is not None:
                sys.modules["signals_engine.lanes.weather_watch"] = previous_module
            LANE_REGISTRY["weather-watch"] = previous_collector

    def test_lanes_list_includes_weather_watch(self):
        from signals_engine.commands import lanes

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = lanes.run(type("Args", (), {"subcommand": "list"})())

        self.assertEqual(rc, 0)
        self.assertIn("weather-watch", buf.getvalue().splitlines())


if __name__ == "__main__":
    unittest.main()
