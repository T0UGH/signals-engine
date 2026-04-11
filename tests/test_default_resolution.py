"""Tests for default config/data resolution."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signals_engine.core.defaults import resolve_config_path, resolve_data_dir


class TestResolveConfigPath(unittest.TestCase):
    def test_explicit_arg_beats_environment(self):
        env = {
            "SIGNALS_ENGINE_CONFIG": "/tmp/new-config.yaml",
            "DAILY_LANE_CONFIG": "/tmp/legacy-config.yaml",
        }

        resolved = resolve_config_path(
            "/tmp/explicit-config.yaml",
            env=env,
            home=Path("/unused-home"),
        )

        self.assertEqual(resolved, Path("/tmp/explicit-config.yaml"))

    def test_new_environment_beats_legacy_environment(self):
        env = {
            "SIGNALS_ENGINE_CONFIG": "/tmp/new-config.yaml",
            "DAILY_LANE_CONFIG": "/tmp/legacy-config.yaml",
        }

        resolved = resolve_config_path(None, env=env, home=Path("/unused-home"))

        self.assertEqual(resolved, Path("/tmp/new-config.yaml"))

    def test_legacy_default_is_used_when_new_default_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            legacy_config = home / ".daily-lane" / "config" / "lanes.yaml"
            legacy_config.parent.mkdir(parents=True, exist_ok=True)
            legacy_config.write_text("lanes: {}\n")

            resolved = resolve_config_path(None, env={}, home=home)

        self.assertEqual(resolved, legacy_config)

    def test_new_default_stays_primary_when_both_defaults_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            new_config = home / ".signal-engine" / "config" / "lanes.yaml"
            legacy_config = home / ".daily-lane" / "config" / "lanes.yaml"
            new_config.parent.mkdir(parents=True, exist_ok=True)
            legacy_config.parent.mkdir(parents=True, exist_ok=True)
            new_config.write_text("lanes: {}\n")
            legacy_config.write_text("lanes: {}\n")

            resolved = resolve_config_path(None, env={}, home=home)

        self.assertEqual(resolved, new_config)


class TestResolveDataDir(unittest.TestCase):
    def test_explicit_arg_beats_environment(self):
        env = {
            "SIGNALS_ENGINE_DATA_DIR": "/tmp/new-data",
            "DAILY_LANE_DATA_DIR": "/tmp/legacy-data",
        }

        resolved = resolve_data_dir(
            "/tmp/explicit-data",
            env=env,
            home=Path("/unused-home"),
        )

        self.assertEqual(resolved, Path("/tmp/explicit-data"))

    def test_new_environment_beats_legacy_environment(self):
        env = {
            "SIGNALS_ENGINE_DATA_DIR": "/tmp/new-data",
            "DAILY_LANE_DATA_DIR": "/tmp/legacy-data",
        }

        resolved = resolve_data_dir(None, env=env, home=Path("/unused-home"))

        self.assertEqual(resolved, Path("/tmp/new-data"))

    def test_legacy_default_is_used_when_new_default_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            legacy_data = home / ".daily-lane-data"
            legacy_data.mkdir(parents=True, exist_ok=True)

            resolved = resolve_data_dir(None, env={}, home=home)

        self.assertEqual(resolved, legacy_data)

    def test_new_default_stays_primary_when_both_defaults_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            new_data = home / ".signal-engine" / "data"
            legacy_data = home / ".daily-lane-data"
            new_data.mkdir(parents=True, exist_ok=True)
            legacy_data.mkdir(parents=True, exist_ok=True)

            resolved = resolve_data_dir(None, env={}, home=home)

        self.assertEqual(resolved, new_data)


if __name__ == "__main__":
    unittest.main()
