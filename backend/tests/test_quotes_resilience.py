import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from app.routers.quotes import gold_quote
from app.services.adapters.base import QuotePoint
from app.services.adapters.yahoo import YahooAdapter
from app.services.portfolio import xirr
from app.services.quotes import _fetch_history


class YahooAdapterTest(unittest.TestCase):
    @patch("app.routers.quotes.fetch_latest_fx")
    @patch("app.routers.quotes.YahooAdapter.fetch_last")
    def test_live_gold_quote_combines_yahoo_spot_with_nbp_rate(self, fetch_last, fetch_fx):
        fetch_last.return_value = QuotePoint(
            date=date(2026, 9, 23),
            close=Decimal("2650"),
            currency="USD",
        )
        fetch_fx.return_value = (date(2026, 9, 23), Decimal("3.7"))

        quote = gold_quote()

        self.assertEqual(quote.spot_usd_oz, Decimal("2650"))
        self.assertEqual(quote.usd_pln, Decimal("3.7"))
        self.assertEqual(
            quote.price_pln_g,
            Decimal("2650") * Decimal("3.7") / Decimal("31.1034768"),
        )
        fetch_last.assert_called_once_with("GC=F", "USD")
        fetch_fx.assert_called_once_with("USD")

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

    @patch("app.services.adapters.yahoo.httpx.get")
    def test_history_uses_close_when_yahoo_has_no_adjusted_closes(self, get):
        get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1790083800],
                            "indicators": {
                                "adjclose": [{"adjclose": [None]}],
                                "quote": [{"close": [2650.0]}],
                            },
                        }
                    ]
                }
            },
        )

        points = YahooAdapter().fetch_history(
            "GC=F", date(2026, 9, 22), date(2026, 9, 23), "USD"
        )

        self.assertEqual(points[0].close, Decimal("2650.0"))

    @patch("app.services.quotes.get_adapter")
    def test_gold_yahoo_ounce_price_is_converted_to_pure_gold_per_gram(self, get_adapter):
        instrument = Mock(
            type="gold",
            ticker="XAU-9999",
            provider="yahoo",
            symbol="GC=F",
            currency="USD",
        )
        get_adapter.return_value.fetch_history.return_value = [
            Mock(date=date(2026, 9, 23), close=Decimal("2000"), currency="USD")
        ]

        points = _fetch_history(instrument, date(2026, 9, 22), date(2026, 9, 23))

        self.assertEqual(
            points[0].close,
            Decimal("2000") * Decimal("0.9999") / Decimal("31.1034768"),
        )

    @patch("app.services.quotes.YahooAdapter.fetch_history")
    @patch("app.services.quotes.get_adapter")
    def test_polish_stock_without_stooq_data_falls_back_to_yahoo(self, get_adapter, yahoo_fetch_history):
        instrument = Mock(
            provider="stooq",
            currency="PLN",
            symbol="acp",
        )
        get_adapter.return_value.fetch_history.return_value = []
        yahoo_fetch_history.return_value = [Mock(date=date(2026, 9, 23), close=Decimal("226.40"), currency="PLN")]

        result = _fetch_history(instrument, date(2026, 9, 22), date(2026, 9, 23))

        self.assertEqual(result[0].close, Decimal("226.40"))
        yahoo_fetch_history.assert_called_once_with("ACP.WA", date(2026, 9, 22), date(2026, 9, 23), "PLN")


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