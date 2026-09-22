import unittest

from app.seed import POLISH_MARKET_INSTRUMENTS


class SeedCatalogTest(unittest.TestCase):
    def test_polish_market_catalog_contains_index_stocks_and_etfs(self):
        self.assertIn("stock_pl", POLISH_MARKET_INSTRUMENTS)
        self.assertIn("etf", POLISH_MARKET_INSTRUMENTS)

        stock_tickers = {row["ticker"] for row in POLISH_MARKET_INSTRUMENTS["stock_pl"]}
        self.assertIn("PGE", stock_tickers)
        self.assertIn("PKO", stock_tickers)
        self.assertIn("KGH", stock_tickers)
        self.assertIn("LPP", stock_tickers)

        etf_tickers = {row["ticker"] for row in POLISH_MARKET_INSTRUMENTS["etf"]}
        self.assertIn("C6E", etf_tickers)
        self.assertIn("V80A", etf_tickers)
