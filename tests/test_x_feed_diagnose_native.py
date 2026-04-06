"""Tests for x-feed native diagnose probe."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signal_engine.runtime.diagnose import diagnose_lane, _probe_native_x


class TestProbeNativeX(unittest.TestCase):
    """Unit tests for the native X probe function."""

    def test_probe_fails_when_cookie_missing(self):
        """Missing cookie file returns non-zero exit."""
        out, err, rc = _probe_native_x(timeout=5)
        self.assertNotEqual(rc, 0)
        self.assertIn("cookie file not found", err)

    def test_probe_fails_on_auth_validation_error(self):
        """Auth validation failure (missing auth_token) returns non-zero."""
        # Write a cookie file that passes file existence but fails auth validation
        cookie_dir = Path.home() / ".signal-engine"
        cookie_dir.mkdir(parents=True, exist_ok=True)
        cookie_path = cookie_dir / "x-cookies.json"
        cookie_path.write_text(
            '{"cookies": [{"name": "ct0", "value": "bad"}]}'
        )
        try:
            out, err, rc = _probe_native_x(timeout=5)
            self.assertNotEqual(rc, 0)
            self.assertIn("auth validation failed", err)
        finally:
            cookie_path.unlink(missing_ok=True)


class TestDiagnoseLaneXFeed(unittest.TestCase):
    """Tests for diagnose_lane with x-feed using native config."""

    def test_diagnose_xfeed_no_source_config_shows_native_warn(self):
        """x-feed with no source config shows native probe WARN (cookie not found)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = diagnose_lane(
                lane="x-feed",
                data_dir=Path(tmpdir),
                config={"lanes": {"x-feed": {"enabled": True}}},
            )
            # Without a source config, native probe tries default cookie path and warns
            self.assertIn("WARN", result.output)
            self.assertIn("native API probe", result.output)
            self.assertIn("skipping API probe", result.output)

    def test_diagnose_xfeed_with_source_config(self):
        """x-feed with source config loaded shows native probe attempt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "lanes": {
                    "x-feed": {
                        "enabled": True,
                        "source": {
                            "auth": {"cookie_file": None},
                            "limit": 100,
                            "timeout_seconds": 30,
                        },
                    }
                }
            }
            result = diagnose_lane(
                lane="x-feed",
                data_dir=Path(tmpdir),
                config=config,
            )
            # Should attempt native probe (will fail due to no cookie but not crash)
            self.assertIn("SOURCE", result.output)

    def test_diagnose_unknown_lane_broken(self):
        """Unknown lane returns exit_code 2 (BROKEN)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = diagnose_lane(
                lane="nonexistent-lane",
                data_dir=Path(tmpdir),
                config={"lanes": {}},
            )
            self.assertEqual(result.exit_code, 2)
            self.assertIn("BROKEN", result.output)

    def test_diagnose_output_contains_no_opencli(self):
        """Diagnose output for x-feed must not mention opencli."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "lanes": {
                    "x-feed": {
                        "enabled": True,
                        "source": {
                            "auth": {"cookie_file": None},
                            "limit": 100,
                            "timeout_seconds": 30,
                        },
                    }
                }
            }
            result = diagnose_lane(
                lane="x-feed",
                data_dir=Path(tmpdir),
                config=config,
            )
            self.assertNotIn("opencli", result.output.lower())
            self.assertNotIn("dist/main.js", result.output)


if __name__ == "__main__":
    unittest.main()
