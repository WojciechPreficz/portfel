import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import pandas as pd
import yfinance as yf

from app.routers.quotes import gold_quote
from app.services.adapters.base import QuotePoint
from app.services.adapters.stooq import STOOQ_URL, StooqAdapter
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

    @patch("app.services.adapters.yahoo.yf.download")
    def test_missing_symbol_returns_no_points(self, download):
        download.return_value = pd.DataFrame()

        points = YahooAdapter().fetch_history(
            "MISSING", date(2026, 1, 1), date(2026, 1, 2), "USD"
        )

        self.assertEqual(points, [])
        download.assert_called_once()

    @patch("app.services.adapters.yahoo.yf.Ticker")
    @patch("app.services.adapters.yahoo.yf.download")
    def test_batch_uses_nominal_close_and_market_currency(self, download, ticker):
        index = pd.to_datetime(["2026-09-23"])
        download.return_value = pd.DataFrame(
            {
                ("SAP.DE", "Close"): [182.5],
                ("SAP.DE", "Adj Close"): [179.2],
                ("MC.PA", "Close"): [777.0],
            },
            index=index,
        )
        ticker.side_effect = [
            Mock(fast_info={"currency": "EUR"}),
            Mock(fast_info={"currency": "EUR"}),
        ]

        points_by_symbol = YahooAdapter().fetch_many(
            {
                "SAP.DE": (date(2026, 9, 22), date(2026, 9, 23), "PLN"),
                "MC.PA": (date(2026, 9, 22), date(2026, 9, 23), "EUR"),
            }
        )
        points = points_by_symbol["SAP.DE"]

        self.assertEqual(points[0].close, Decimal("182.5"))
        self.assertEqual(points[0].currency, "EUR")
        self.assertEqual(points_by_symbol["MC.PA"][0].close, Decimal("777.0"))
        download.assert_called_once_with(
            tickers=["SAP.DE", "MC.PA"],
            start="2026-09-22",
            end="2026-09-24",
            auto_adjust=False,
            group_by="ticker",
            progress=False,
        )

    @patch("app.services.adapters.yahoo.yf.Ticker")
    @patch("app.services.adapters.yahoo.yf.download")
    def test_minor_currency_quotes_are_converted_to_major_units(self, download, ticker):
        download.return_value = pd.DataFrame(
            {"Close": [102.4]}, index=pd.to_datetime(["2026-09-23"])
        )
        ticker.return_value.fast_info = {"currency": "GBp"}

        points = YahooAdapter().fetch_history(
            "VOD.L", date(2026, 9, 22), date(2026, 9, 23), "GBP"
        )

        self.assertEqual(points[0].close, Decimal("1.024"))
        self.assertEqual(points[0].currency, "GBP")

    @patch("app.services.adapters.yahoo.time.sleep")
    @patch("app.services.adapters.yahoo.yf.download")
    def test_download_retries_http_rate_limit(self, download, sleep):
        class RateLimitedError(Exception):
            status_code = 429

        download.side_effect = [
            RateLimitedError("rate limit"),
            pd.DataFrame(),
        ]

        points = YahooAdapter().fetch_history(
            "SAP.DE", date(2026, 9, 22), date(2026, 9, 23), "EUR"
        )

        self.assertEqual(points, [])
        self.assertEqual(download.call_count, 2)
        sleep.assert_called_once_with(0.5)

    @patch("app.services.adapters.yahoo.time.sleep")
    @patch("app.services.adapters.yahoo.yf.download")
    def test_download_retries_rate_limits_swallowed_by_yfinance(self, download, sleep):
        def log_rate_limit(tickers, start, end, auto_adjust, group_by, progress):
            del tickers, start, end, auto_adjust, group_by, progress
            if download.call_count == 1:
                yf.utils.get_yf_logger().error(
                    "YFRateLimitError: Too Many Requests"
                )
            return pd.DataFrame()

        download.side_effect = log_rate_limit

        points = YahooAdapter().fetch_history(
            "SAP.DE", date(2026, 9, 22), date(2026, 9, 23), "EUR"
        )

        self.assertEqual(points, [])
        self.assertEqual(download.call_count, 2)
        sleep.assert_called_once_with(0.5)

    @patch("app.services.adapters.yahoo.yf.download")
    def test_legacy_meud_fr_symbol_uses_central_alias(self, download):
        download.return_value = pd.DataFrame()

        YahooAdapter().fetch_history(
            "MEUD.FR", date(2026, 9, 22), date(2026, 9, 23), "EUR"
        )

        self.assertEqual(download.call_args.kwargs["tickers"], ["MEUD.MI"])
        self.assertEqual(YahooAdapter._canonical_symbol("11BIT.WA"), "11B.WA")

    @patch("app.services.quotes.YahooAdapter.fetch_history")
    @patch("app.services.quotes.get_adapter")
    def test_polish_stock_without_stooq_data_falls_back_to_yahoo(
        self, get_adapter, yahoo_fetch_history
    ):
        instrument = Mock(
            provider="stooq",
            type="stock_pl",
            ticker="ACP",
            currency="PLN",
            symbol="acp",
        )
        get_adapter.return_value.fetch_history.return_value = []
        yahoo_fetch_history.return_value = [
            Mock(date=date(2026, 9, 23), close=Decimal("226.40"), currency="PLN")
        ]

        result = _fetch_history(instrument, date(2026, 9, 22), date(2026, 9, 23))

        self.assertEqual(result[0].close, Decimal("226.40"))
        yahoo_fetch_history.assert_called_once_with(
            "ACP.WA", date(2026, 9, 22), date(2026, 9, 23), "PLN"
        )

    @patch("app.services.quotes.YahooAdapter.fetch_history")
    @patch("app.services.quotes.get_adapter")
    def test_non_polish_stooq_symbol_does_not_get_polish_fallback(
        self, get_adapter, yahoo_fetch_history
    ):
        instrument = Mock(
            provider="stooq",
            type="stock_intl",
            ticker="SAP",
            currency="EUR",
            symbol="SAP.DE",
        )
        get_adapter.return_value.fetch_history.side_effect = ValueError("not a GPW listing")

        with self.assertRaisesRegex(ValueError, "not a GPW listing"):
            _fetch_history(instrument, date(2026, 9, 22), date(2026, 9, 23))

        yahoo_fetch_history.assert_not_called()

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


class StooqAdapterTest(unittest.TestCase):
    @patch("app.services.adapters.stooq.httpx.Client")
    def test_history_request_is_limited_to_requested_dates(self, client_factory):
        client = client_factory.return_value.__enter__.return_value
        client.get.return_value.text = (
            "Date,Open,High,Low,Close,Volume\n"
            "2026-09-03,10,11,9,10.5,100\n"
        )

        points = StooqAdapter().fetch_history(
            "test", date(2026, 9, 1), date(2026, 9, 5), "PLN"
        )

        client.get.assert_called_once_with(
            STOOQ_URL,
            params={
                "s": "test",
                "i": "d",
                "d1": "20260901",
                "d2": "20260905",
            },
        )
        self.assertEqual(points[0].date, date(2026, 9, 3))
        self.assertEqual(points[0].close, Decimal("10.5"))


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
