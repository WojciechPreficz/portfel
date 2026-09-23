import unittest

from app.seed import NASDAQ_STOCKS, NYSE_STOCKS, POLISH_MARKET_INSTRUMENTS, STOOQ_SYMBOL_OVERRIDES


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

    def test_provider_symbol_override_for_11bit(self):
        self.assertEqual(STOOQ_SYMBOL_OVERRIDES["11BIT"], "11b")

        etf_tickers = {row["ticker"] for row in POLISH_MARKET_INSTRUMENTS["etf"]}
        self.assertIn("C6E", etf_tickers)
        self.assertIn("V80A", etf_tickers)

    def test_nasdaq_catalog_contains_us_stocks(self):
        self.assertTrue(NASDAQ_STOCKS)
        self.assertTrue(all(row["type"] == "stock_us" for row in NASDAQ_STOCKS))
        self.assertTrue(all(row["provider"] == "yahoo" for row in NASDAQ_STOCKS))

    def test_nyse_catalog_contains_separate_us_stocks(self):
        self.assertTrue(NYSE_STOCKS)
        self.assertTrue(all(row["type"] == "stock_us_nyse" for row in NYSE_STOCKS))
        self.assertTrue(all(row["provider"] == "yahoo" for row in NYSE_STOCKS))
