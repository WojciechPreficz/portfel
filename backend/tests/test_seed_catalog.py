import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Instrument, Price, Transaction
from app.seed import GOLD_PURITIES, GPW_STOCK_TICKERS, NASDAQ_STOCKS, NYSE_STOCKS, POLISH_MARKET_INSTRUMENTS, SEED, apply_instrument_defaults, seed_instruments
from app.services.symbol_aliases import STOOQ_SYMBOL_ALIASES, YAHOO_SYMBOL_ALIASES


class SeedCatalogTest(unittest.TestCase):
    def test_polish_market_catalog_contains_index_stocks_and_etfs(self):
        self.assertIn("stock_pl", POLISH_MARKET_INSTRUMENTS)
        self.assertIn("etf", POLISH_MARKET_INSTRUMENTS)

        stock_tickers = {row["ticker"] for row in POLISH_MARKET_INSTRUMENTS["stock_pl"]}
        self.assertIn("PGE", stock_tickers)
        self.assertIn("PKO", stock_tickers)
        self.assertIn("KGH", stock_tickers)
        self.assertIn("LPP", stock_tickers)
        self.assertIn("KTY", stock_tickers)
        self.assertIn("NEUCA", GPW_STOCK_TICKERS)

    def test_provider_symbol_override_for_11bit(self):
        self.assertEqual(STOOQ_SYMBOL_ALIASES["11BIT"], "11b")
        self.assertEqual(STOOQ_SYMBOL_ALIASES["AMBRA"], "amb")
        self.assertEqual(STOOQ_SYMBOL_ALIASES["KRUK"], "kru")
        self.assertEqual(STOOQ_SYMBOL_ALIASES["ZWC"], "zwc")
        self.assertEqual(YAHOO_SYMBOL_ALIASES["AMBRA.WA"], "AMB.WA")
        self.assertEqual(YAHOO_SYMBOL_ALIASES["KRUK.WA"], "KRU.WA")

        etf_tickers = {row["ticker"] for row in POLISH_MARKET_INSTRUMENTS["etf"]}
        self.assertIn("C6E", etf_tickers)
        self.assertIn("V80A", etf_tickers)
        v80a = next(row for row in POLISH_MARKET_INSTRUMENTS["etf"] if row["ticker"] == "V80A")
        self.assertEqual(v80a["symbol"], "V80A.AS")

    def test_gold_catalog_uses_yahoo_and_has_purity_variants(self):
        gold = [row for row in SEED if row["type"] == "gold"]

        self.assertEqual(len(gold), len(GOLD_PURITIES))
        self.assertTrue(all(row["provider"] == "yahoo" for row in gold))
        self.assertTrue(all(row["currency"] == "USD" for row in gold))
        self.assertTrue(all(row["symbol"] == "GC=F" for row in gold))

    def test_meu_uses_yahoo_exchange_symbol(self):
        instrument = apply_instrument_defaults({"ticker": "MEU", "type": "etf"})

        self.assertEqual(instrument["symbol"], "MEUD.MI")

    def test_nasdaq_catalog_contains_us_stocks(self):
        self.assertTrue(NASDAQ_STOCKS)
        self.assertTrue(all(row["type"] == "stock_us" for row in NASDAQ_STOCKS))
        self.assertTrue(all(row["provider"] == "yahoo" for row in NASDAQ_STOCKS))

    def test_nyse_catalog_contains_separate_us_stocks(self):
        self.assertTrue(NYSE_STOCKS)
        self.assertTrue(all(row["type"] == "stock_us_nyse" for row in NYSE_STOCKS))
        self.assertTrue(all(row["provider"] == "yahoo" for row in NYSE_STOCKS))

    def test_polish_asseco_acp_is_not_loaded_as_us_stock(self):
        stock_pl_tickers = {row["ticker"] for row in POLISH_MARKET_INSTRUMENTS["stock_pl"]}
        nyse_tickers = {row["ticker"] for row in NYSE_STOCKS}

        self.assertIn("ACP", stock_pl_tickers)
        self.assertNotIn("ACP", nyse_tickers)

    def test_legacy_adm_mapping_is_corrected_without_losing_transactions(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                wrong_adm = Instrument(
                    ticker="ADMA",
                    name="ADM",
                    type="stock_us_nyse",
                    currency="USD",
                    provider="yahoo",
                    symbol="ADMA",
                    unit="share",
                )
                correct_adm = Instrument(
                    ticker="ADM",
                    name="ARCHER-DANIELS-MIDLAND CO",
                    type="stock_us_nyse",
                    currency="USD",
                    provider="yahoo",
                    symbol="ADM",
                    unit="share",
                )
                adma_biologics = Instrument(
                    ticker="ADMA",
                    name="ADMA Biologics Inc",
                    type="stock_us",
                    currency="USD",
                    provider="yahoo",
                    symbol="ADMA",
                    unit="share",
                )
                db.add_all([wrong_adm, correct_adm, adma_biologics])
                db.flush()
                wrong_adm_id = wrong_adm.id
                transaction = Transaction(
                    portfolio_id=1,
                    instrument_id=wrong_adm.id,
                    type="BUY",
                    quantity=Decimal("4"),
                    price=Decimal("50"),
                    currency="USD",
                    date=date(2025, 1, 1),
                    commission=Decimal("0"),
                )
                wrong_price = Price(
                    instrument_id=wrong_adm.id,
                    date=date(2025, 1, 1),
                    close=Decimal("9.72"),
                    currency="USD",
                )
                db.add_all([transaction, wrong_price])
                db.commit()

                with patch(
                    "app.seed.SEED",
                    [
                        {
                            "ticker": "ADM",
                            "name": "ARCHER-DANIELS-MIDLAND CO",
                            "type": "stock_us_nyse",
                            "currency": "USD",
                            "provider": "yahoo",
                            "symbol": "ADM",
                            "unit": "share",
                        },
                        {
                            "ticker": "ADMA",
                            "name": "ADMA Biologics Inc",
                            "type": "stock_us",
                            "currency": "USD",
                            "provider": "yahoo",
                            "symbol": "ADMA",
                            "unit": "share",
                        },
                    ],
                ):
                    seed_instruments(db)

                self.assertIsNone(db.get(Instrument, wrong_adm_id))
                self.assertEqual(
                    db.scalar(select(Transaction)).instrument_id, correct_adm.id
                )
                self.assertEqual(
                    db.scalar(select(Instrument).where(Instrument.ticker == "ADM")).symbol,
                    "ADM",
                )
                self.assertEqual(db.scalars(select(Price)).all(), [])
                self.assertEqual(
                    db.scalar(select(Instrument).where(Instrument.type == "stock_us")).name,
                    "ADMA Biologics Inc",
                )
        finally:
            engine.dispose()
