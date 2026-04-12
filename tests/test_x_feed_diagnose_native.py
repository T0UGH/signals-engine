"""Tests for x-feed native diagnose probe."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signals_engine.sources.x.errors import AuthError
from signals_engine.runtime.diagnose import diagnose_lane, _probe_native_x


class TestProbeNativeX(unittest.TestCase):
    """Unit tests for the native X probe function."""

    def test_probe_cookie_file_mode_fails_when_cookie_missing(self):
        """Legacy cookie-file mode still surfaces missing cookie files explicitly."""
        missing_cookie = str(Path.home() / ".signal-engine" / "definitely-missing-x-cookies.json")
        out, err, rc = _probe_native_x(
            auth_config={
                "mode": "cookie-file",
                "cookie_file": missing_cookie,
            },
            timeout=5,
        )
        self.assertNotEqual(rc, 0)
        self.assertIn("cookie file not found", err)

    def test_probe_cookie_file_mode_fails_on_auth_validation_error(self):
        """Legacy cookie-file auth validation failure returns non-zero."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cookie_path = Path(tmpdir) / "x-cookies.json"
            cookie_path.write_text(
                '{"cookies": [{"name": "ct0", "value": "bad"}]}'
            )

            out, err, rc = _probe_native_x(
                auth_config={
                    "mode": "cookie-file",
                    "cookie_file": str(cookie_path),
                },
                timeout=5,
            )
            self.assertNotEqual(rc, 0)
            self.assertIn("auth validation failed", err)

    @patch("signals_engine.runtime.diagnose.XBrowserSessionClient.fetch_timeline_raw")
    def test_probe_browser_session_mode_reports_auth_error(self, mock_fetch):
        """Browser-session auth failures must be reported explicitly."""
        mock_fetch.side_effect = AuthError("ct0 missing from x.com browser session")

        out, err, rc = _probe_native_x(
            auth_config={
                "mode": "browser-session",
                "cdp_url": "http://127.0.0.1:9222",
            },
            timeout=5,
        )

        self.assertNotEqual(rc, 0)
        self.assertIn("ct0 missing", err)


class TestDiagnoseLaneXFeed(unittest.TestCase):
    """Tests for diagnose_lane with x-feed using native config."""

    @patch(
        "signals_engine.runtime.diagnose._probe_native_x",
        return_value=("", "browser session not available", 2),
    )
    def test_diagnose_xfeed_no_source_config_defaults_to_browser_session(self, _mock_probe):
        """x-feed without explicit auth config defaults to browser-session diagnostics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = diagnose_lane(
                lane="x-feed",
                data_dir=Path(tmpdir),
                config={"lanes": {"x-feed": {"enabled": True}}},
            )
            self.assertIn("auth mode: browser-session", result.output)
            self.assertIn("browser session not available", result.output)

    @patch(
        "signals_engine.runtime.diagnose._probe_native_x",
        return_value=("", "ct0 missing from x.com browser session", 2),
    )
    def test_diagnose_xfeed_browser_session_config(self, _mock_probe):
        """x-feed diagnose output is mode-aware for browser-session auth."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "lanes": {
                    "x-feed": {
                        "enabled": True,
                        "source": {
                            "auth": {
                                "mode": "browser-session",
                                "cdp_url": "http://127.0.0.1:9222",
                            },
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
            self.assertIn("auth mode: browser-session", result.output)
            self.assertIn("ct0 missing from x.com browser session", result.output)
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
                            "auth": {"mode": "browser-session"},
                            "limit": 100,
                            "timeout_seconds": 30,
                        },
                    }
                }
            }
            with patch(
                "signals_engine.runtime.diagnose._probe_native_x",
                return_value=("", "browser session not available", 2),
            ):
                result = diagnose_lane(
                    lane="x-feed",
                    data_dir=Path(tmpdir),
                    config=config,
                )
            self.assertNotIn("opencli", result.output.lower())


if __name__ == "__main__":
    unittest.main()
