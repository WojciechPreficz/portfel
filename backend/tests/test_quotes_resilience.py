import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from app.services.adapters.yahoo import YahooAdapter
from app.services.portfolio import xirr


class YahooAdapterTest(unittest.TestCase):
    @patch("app.services.adapters.yahoo.httpx.get")
    def test_missing_symbol_returns_no_points(self, get):
        response = Mock(status_code=404)
        get.return_value = response

        points = YahooAdapter().fetch_history("C6E.DE", date(2026, 1, 1), date(2026, 1, 2), "EUR")

        self.assertEqual(points, [])
        response.raise_for_status.assert_not_called()

    @patch("app.services.adapters.yahoo.httpx.get")
    def test_legacy_meud_fr_symbol_uses_milan_listing(self, get):
        get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1790164800],
                            "indicators": {"adjclose": [{"adjclose": [316.1]}]},
                        }
                    ]
                }
            },
        )

        points = YahooAdapter().fetch_history(
            "MEUD.FR", date(2026, 9, 22), date(2026, 9, 23), "EUR"
        )

        self.assertEqual(points[0].close, Decimal("316.1"))
        self.assertIn("/MEUD.MI", get.call_args.args[0])

    @patch("app.services.adapters.yahoo.httpx.get")
    def test_current_market_price_is_used_when_available(self, get):
        get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "chart": {
                    "result": [
                        {
                            "meta": {"regularMarketPrice": 362.04, "regularMarketTime": 1790107202},
                            "timestamp": [1790083800],
                            "indicators": {"adjclose": [{"adjclose": [369.95]}]},
                        }
                    ]
                }
            },
        )

        points = YahooAdapter().fetch_history(
            "V", date(2026, 9, 22), date(2026, 9, 23), "USD"
        )

        self.assertEqual(points[-1].close, Decimal("362.04"))


class XirrTest(unittest.TestCase):
    def test_annual_return_is_ten_percent(self):
        result = xirr(
            [
                (date(2025, 1, 1), Decimal("-1000")),
                (date(2026, 1, 1), Decimal("1100")),
            ]
        )

        self.assertIsNotNone(result)
        self.assertAlmostEqual(float(result), 0.1, places=6)