import unittest

from app.seed import GPW_STOCK_TICKERS, NASDAQ_STOCKS, NYSE_STOCKS, POLISH_MARKET_INSTRUMENTS, STOOQ_SYMBOL_OVERRIDES, apply_instrument_defaults


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
        self.assertEqual(STOOQ_SYMBOL_OVERRIDES["11BIT"], "11b")

        etf_tickers = {row["ticker"] for row in POLISH_MARKET_INSTRUMENTS["etf"]}
        self.assertIn("C6E", etf_tickers)
        self.assertIn("V80A", etf_tickers)

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
