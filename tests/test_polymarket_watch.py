"""Tests for ai-prediction-watch lane and Polymarket source."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from signals_engine.core import RunContext, RunStatus


class TestPolymarketSource(unittest.TestCase):
    def test_parse_search_response_keeps_relevant_ai_markets_and_synthesizes_outcomes(self):
        from signals_engine.sources.polymarket import parse_polymarket_search_response

        payload = {
            "events": [
                {
                    "id": "evt-ai-model",
                    "title": "Who will have the best AI model at the end of 2026?",
                    "slug": "best-ai-model-2026",
                    "active": True,
                    "closed": False,
                    "updatedAt": "2026-04-12T02:00:00Z",
                    "volume1mo": "1200000",
                    "volume24hr": "125000",
                    "liquidity": "210000",
                    "markets": [
                        {
                            "id": "m-openai",
                            "question": "Will OpenAI have the best AI model at the end of 2026?",
                            "active": True,
                            "closed": False,
                            "liquidity": "150000",
                            "volume": "900000",
                            "endDate": "2026-12-31T23:59:59Z",
                            "oneWeekPriceChange": "0.04",
                            "oneMonthPriceChange": "0.08",
                            "outcomes": "[\"Yes\", \"No\"]",
                            "outcomePrices": "[\"0.62\", \"0.38\"]",
                        },
                        {
                            "id": "m-anthropic",
                            "question": "Will Anthropic have the best AI model at the end of 2026?",
                            "active": True,
                            "closed": False,
                            "liquidity": "110000",
                            "volume": "450000",
                            "endDate": "2026-12-31T23:59:59Z",
                            "oneWeekPriceChange": "-0.02",
                            "outcomes": "[\"Yes\", \"No\"]",
                            "outcomePrices": "[\"0.27\", \"0.73\"]",
                        },
                        {
                            "id": "m-google",
                            "question": "Will Google have the best AI model at the end of 2026?",
                            "active": True,
                            "closed": False,
                            "liquidity": "90000",
                            "volume": "300000",
                            "endDate": "2026-12-31T23:59:59Z",
                            "oneWeekPriceChange": "0.01",
                            "outcomes": "[\"Yes\", \"No\"]",
                            "outcomePrices": "[\"0.11\", \"0.89\"]",
                        },
                    ],
                },
                {
                    "id": "evt-noise",
                    "title": "Who will win the NBA finals?",
                    "slug": "nba-finals",
                    "active": True,
                    "closed": False,
                    "updatedAt": "2026-04-12T02:00:00Z",
                    "volume1mo": "3000000",
                    "liquidity": "400000",
                    "markets": [
                        {
                            "id": "m-noise",
                            "question": "Will the Lakers win the NBA finals?",
                            "active": True,
                            "closed": False,
                            "liquidity": "400000",
                            "volume": "3000000",
                            "outcomes": "[\"Yes\", \"No\"]",
                            "outcomePrices": "[\"0.51\", \"0.49\"]",
                        }
                    ],
                },
            ]
        }

        markets = parse_polymarket_search_response(payload, query="best AI model")

        self.assertEqual(len(markets), 1)
        market = markets[0]
        self.assertEqual(market.event_id, "evt-ai-model")
        self.assertEqual(market.event_title, "Who will have the best AI model at the end of 2026?")
        self.assertEqual(market.primary_outcome, "OpenAI")
        self.assertAlmostEqual(market.primary_probability, 0.62)
        self.assertEqual(market.top_outcomes[0], ("OpenAI", 0.62))
        self.assertEqual(market.top_outcomes[1], ("Anthropic", 0.27))
        self.assertEqual(market.top_outcomes[2], ("Google", 0.11))
        self.assertEqual(market.end_date, "2026-12-31")
        self.assertIn("polymarket.com/event/best-ai-model-2026", market.url)
        self.assertGreater(market.relevance, 0.2)

    def test_parse_search_response_drops_low_relevance_noise(self):
        from signals_engine.sources.polymarket import parse_polymarket_search_response

        payload = {
            "events": [
                {
                    "id": "evt-crypto",
                    "title": "Will Bitcoin hit $200k in 2026?",
                    "slug": "bitcoin-200k",
                    "active": True,
                    "closed": False,
                    "updatedAt": "2026-04-12T02:00:00Z",
                    "volume1mo": "2500000",
                    "liquidity": "500000",
                    "markets": [
                        {
                            "id": "m-crypto",
                            "question": "Will Bitcoin hit $200k in 2026?",
                            "active": True,
                            "closed": False,
                            "liquidity": "500000",
                            "volume": "2500000",
                            "outcomes": "[\"Yes\", \"No\"]",
                            "outcomePrices": "[\"0.41\", \"0.59\"]",
                        }
                    ],
                }
            ]
        }

        markets = parse_polymarket_search_response(payload, query="coding AI model")

        self.assertEqual(markets, [])


class TestAIPredictionWatchLane(unittest.TestCase):
    def _make_ctx(self, tmp_dir: str, lane_config: dict) -> RunContext:
        ctx = RunContext(
            lane="ai-prediction-watch",
            date="2026-04-12",
            data_dir=Path(tmp_dir),
            config={"lanes": {"ai-prediction-watch": lane_config}},
        )
        ctx.ensure_dirs()
        return ctx

    @patch("signals_engine.lanes.ai_prediction_watch.fetch_polymarket_markets")
    def test_collect_writes_signals_and_index_with_topic_context(self, mock_fetch):
        from signals_engine.lanes.ai_prediction_watch import collect_ai_prediction_watch
        from signals_engine.sources.polymarket import PolymarketMarket

        openai = PolymarketMarket(
            event_id="evt-ai-model",
            market_id="m-openai",
            event_title="Who will have the best AI model at the end of 2026?",
            question="Who will have the best AI model at the end of 2026?",
            url="https://polymarket.com/event/best-ai-model-2026",
            primary_outcome="OpenAI",
            primary_probability=0.62,
            top_outcomes=[("OpenAI", 0.62), ("Anthropic", 0.27), ("Google", 0.11)],
            volume_24h=125000.0,
            volume_30d=1200000.0,
            liquidity=210000.0,
            price_movement="up 8.0% this month",
            end_date="2026-12-31",
            updated_at="2026-04-12T02:00:00Z",
            relevance=0.88,
        )
        benchmark = PolymarketMarket(
            event_id="evt-benchmark",
            market_id="m-swe-bench",
            event_title="Will an AI model exceed 80% on SWE-bench Verified in 2026?",
            question="Will an AI model exceed 80% on SWE-bench Verified in 2026?",
            url="https://polymarket.com/event/swe-bench-80",
            primary_outcome="Yes",
            primary_probability=0.57,
            top_outcomes=[("Yes", 0.57), ("No", 0.43)],
            volume_24h=22000.0,
            volume_30d=180000.0,
            liquidity=80000.0,
            price_movement="up 3.0% this week",
            end_date="2026-09-30",
            updated_at="2026-04-12T02:10:00Z",
            relevance=0.71,
        )
        mock_fetch.side_effect = [[openai], [openai, benchmark]]

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._make_ctx(
                tmp,
                {
                    "queries": [
                        {"topic": "model-race", "query": "best AI model"},
                        {"topic": "benchmark", "query": "AI benchmark"},
                    ],
                    "source": {"max_pages": 1, "timeout": 5},
                    "max_per_query": 2,
                },
            )
            result = collect_ai_prediction_watch(ctx)
            record = result.signal_records[0]
            signal_md = Path(record.file_path).read_text(encoding="utf-8")
            index_md = (Path(tmp) / "signals" / "ai-prediction-watch" / "2026-04-12" / "index.md").read_text(
                encoding="utf-8"
            )

        self.assertEqual(result.status, RunStatus.SUCCESS)
        self.assertEqual(result.repos_checked, 2)
        self.assertEqual(result.signals_written, 2)
        self.assertEqual(result.signal_types_count, {"prediction_market": 2})
        self.assertEqual(record.source, "polymarket")
        self.assertEqual(record.group, "model-race")
        self.assertEqual(record.query, "best AI model")
        self.assertEqual(record.primary_outcome, "OpenAI")
        self.assertAlmostEqual(record.primary_probability, 0.62)
        self.assertIn("primary_outcome: OpenAI", signal_md)
        self.assertIn("## Expectation", signal_md)
        self.assertIn("## Market Strength", signal_md)
        self.assertIn("Who will have the best AI model", index_md)
        self.assertIn("https://polymarket.com/event/best-ai-model-2026", index_md)

    @patch("signals_engine.sources.polymarket.fetch_polymarket_markets", return_value=[])
    def test_collect_lane_registers_ai_prediction_watch_without_direct_module_import(self, _mock_fetch):
        from signals_engine.lanes.registry import LANE_REGISTRY
        from signals_engine.runtime.collect import collect_lane

        previous_module = sys.modules.pop("signals_engine.lanes.ai_prediction_watch", None)
        previous_collector = LANE_REGISTRY["ai-prediction-watch"]
        LANE_REGISTRY["ai-prediction-watch"] = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ctx = self._make_ctx(tmp, {})
                result = collect_lane(ctx)

            self.assertEqual(result.status, RunStatus.EMPTY)
            self.assertIsNotNone(LANE_REGISTRY["ai-prediction-watch"])
        finally:
            if previous_module is not None:
                sys.modules["signals_engine.lanes.ai_prediction_watch"] = previous_module
            LANE_REGISTRY["ai-prediction-watch"] = previous_collector

    def test_lanes_list_includes_ai_prediction_watch(self):
        from signals_engine.commands import lanes

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = lanes.run(type("Args", (), {"subcommand": "list"})())

        self.assertEqual(rc, 0)
        self.assertIn("ai-prediction-watch", buf.getvalue().splitlines())


if __name__ == "__main__":
    unittest.main()
