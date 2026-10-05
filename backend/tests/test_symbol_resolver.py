import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Instrument
from app.services.symbol_aliases import XSTATION_TO_YAHOO_SUFFIX
from app.services.symbol_resolver import (
    ResolutionError,
    ResolvedInstrument,
    bossa_alias,
    normalise_ticker,
    resolve,
)


class SymbolResolverTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @patch("app.services.symbol_resolver._fast_currency", return_value=None)
    def test_exchange_suffixes_resolve_to_expected_yahoo_symbols_and_currencies(self, _currency):
        for suffix, yahoo_suffix in XSTATION_TO_YAHOO_SUFFIX.items():
            with self.subTest(suffix=suffix):
                result = resolve(
                    self.db,
                    raw_ticker=f"ABC.{suffix}",
                    isin=None,
                    name="Example",
                    category=None,
                    currency_hint=None,
                )

                self.assertIsInstance(result, ResolvedInstrument)
                self.assertEqual(result.symbol, f"ABC{yahoo_suffix}" if suffix != "PL" else "abc")
                self.assertEqual(
                    result.currency,
                    {
                        "US": "USD",
                        "PL": "PLN",
                        "DE": "EUR",
                        "UK": "GBP",
                        "FR": "EUR",
                        "NL": "EUR",
                        "IT": "EUR",
                        "ES": "EUR",
                        "CH": "CHF",
                        "BE": "EUR",
                        "PT": "EUR",
                        "DK": "DKK",
                        "SE": "SEK",
                        "NO": "NOK",
                        "FI": "EUR",
                        "AT": "EUR",
                        "IE": "EUR",
                    }[suffix],
                )
        self.assertEqual(_currency.call_count, len(XSTATION_TO_YAHOO_SUFFIX) - 1)

    @patch("app.services.symbol_resolver._fast_currency", return_value="EUR")
    @patch(
        "app.services.symbol_resolver._search_by_isin",
        return_value={"symbol": "SAP.DE", "quoteType": "EQUITY", "exchange": "GER"},
    )
    def test_isin_search_determines_foreign_equity_and_exchange(
        self, search, _currency
    ):
        result = resolve(
            self.db,
            raw_ticker="SAP.DE",
            isin="DE0007164600",
            name="SAP SE",
            category=None,
            currency_hint="PLN",
        )

        self.assertEqual(result.type, "stock_intl")
        self.assertEqual(result.provider, "yahoo")
        self.assertEqual(result.symbol, "SAP.DE")
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.exchange, "GER")
        search.assert_called_once_with("DE0007164600")
        _currency.assert_called_once_with("SAP.DE")

    @patch("app.services.symbol_resolver._fast_currency")
    @patch(
        "app.services.symbol_resolver._search_by_isin",
        return_value={"symbol": "11B.WA", "quoteType": "EQUITY", "exchange": "WSE"},
    )
    def test_isin_search_identifies_gp_w_listing_without_a_broker_ticker(
        self, search, currency
    ):
        result = resolve(
            self.db, None, "PL11BTS00015", "11 bit studios", None, None
        )

        self.assertEqual(result.ticker, "11B")
        self.assertEqual(result.type, "stock_pl")
        self.assertEqual(result.provider, "stooq")
        self.assertEqual(result.symbol, "11b")
        self.assertEqual(result.currency, "PLN")
        search.assert_called_once_with("PL11BTS00015")
        currency.assert_not_called()

    @patch("app.services.symbol_resolver.yf.Search")
    def test_existing_isin_instrument_is_returned_without_search(self, search):
        instrument = Instrument(
            ticker="SAP",
            isin="DE0007164600",
            name="SAP SE",
            type="stock_intl",
            currency="EUR",
            provider="yahoo",
            symbol="SAP.DE",
            unit="share",
        )
        self.db.add(instrument)
        self.db.commit()

        result = resolve(
            self.db, "SAP.DE", "DE0007164600", "Imported name", None, "PLN"
        )

        self.assertEqual(result.instrument_id, instrument.id)
        self.assertEqual(result.ticker, "SAP")
        search.assert_not_called()

    def test_unrecognized_ticker_does_not_default_to_polish_stock(self):
        result = resolve(self.db, "UNKNOWN", None, "Unknown", None, "PLN")

        self.assertIsInstance(result, ResolutionError)
        self.assertIn("Nie można rozpoznać", result.message)

    @patch("app.services.symbol_resolver._fast_currency", return_value=None)
    def test_known_gpw_ticker_without_suffix_uses_stooq(self, _currency):
        result = resolve(self.db, "NEU", None, "Neuca", None, None)

        self.assertEqual(result.type, "stock_pl")
        self.assertEqual(result.provider, "stooq")
        self.assertEqual(result.symbol, "neu")
        self.assertEqual(result.currency, "PLN")

    def test_bossa_name_alias_is_centralized(self):
        alias = bossa_alias("Vanguard LifeStrategy 80% Equity UCITS ETF")

        self.assertEqual(alias["ticker"], "V80A")
        self.assertEqual(alias["raw_ticker"], "V80A.AS")
        self.assertEqual(alias["isin"], "IE00BMVB5R75")

    def test_yahoo_exchange_suffixes_are_removed_from_display_ticker(self):
        self.assertEqual(normalise_ticker("V80A.AS"), "V80A")
        self.assertEqual(normalise_ticker("11B.WA"), "11B")


if __name__ == "__main__":
    unittest.main()
