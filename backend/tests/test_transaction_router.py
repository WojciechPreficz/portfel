import unittest

from app.routers.transactions import _infer_import_instrument_type


class TransactionRouterTest(unittest.TestCase):
    def test_neu_import_is_classified_as_polish_stock(self):
        self.assertEqual(_infer_import_instrument_type("NEU", "NEU", None), "stock_pl")


if __name__ == "__main__":
    unittest.main()