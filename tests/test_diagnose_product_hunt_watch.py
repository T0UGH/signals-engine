"""Tests for diagnose output of product-hunt-watch lane."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signals_engine.runtime.diagnose import diagnose_lane


class TestDiagnoseLaneProductHuntWatch(unittest.TestCase):
    """Tests for diagnose_lane with API-driven product-hunt-watch."""

    def test_diagnose_product_hunt_watch_uses_api_config_check(self):
        """API-driven lanes should report API token config instead of native-source warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = diagnose_lane(
                lane="product-hunt-watch",
                data_dir=Path(tmpdir),
                config={
                    "lanes": {
                        "product-hunt-watch": {
                            "enabled": True,
                            "api": {
                                "token": "config-token",
                                "token_env": "PH_API_TOKEN",
                            },
                            "topics": ["Artificial Intelligence"],
                        }
                    }
                },
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("SOURCE", result.output)
        self.assertIn("api token", result.output)
        self.assertNotIn("no native source configured for this lane", result.output)

    def test_diagnose_other_non_x_lane_still_warns_without_known_source_mode(self):
        """Non-X lanes without an explicit diagnose source mode should keep the generic warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = diagnose_lane(
                lane="github-watch",
                data_dir=Path(tmpdir),
                config={"lanes": {"github-watch": {"enabled": True}}},
            )

        self.assertIn("no native source configured for this lane", result.output)

    def test_diagnose_polymarket_watch_uses_source_config_check(self):
        """Source-config-driven non-X lanes should report configured source config instead of the generic warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = diagnose_lane(
                lane="polymarket-watch",
                data_dir=Path(tmpdir),
                config={
                    "lanes": {
                        "polymarket-watch": {
                            "enabled": True,
                            "source": {"max_pages": 2, "timeout": 15},
                            "max_per_query": 3,
                        }
                    }
                },
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("SOURCE", result.output)
        self.assertIn("source config: configured", result.output)
        self.assertNotIn("no native source configured for this lane", result.output)


if __name__ == "__main__":
    unittest.main()
