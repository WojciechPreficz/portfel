import unittest
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from app.services.transaction_import import read_purchases


class TransactionImportTest(unittest.TestCase):
    def test_xstation_cash_operations_uses_ticker_and_instrument_name(self):
        workbook = Workbook()
        workbook.active.title = "Summary"
        sheet = workbook.create_sheet("Cash Operations")
        sheet.append(["Time", "Type", "Ticker", "Instrument", "Comment", "Amount"])
        sheet.append([datetime(2026, 9, 11), "Buy", "ABC.US", "Example Corp", "OPEN BUY 2/95 @ 85.20", -170.40])
        sheet.append([datetime(2026, 9, 12), "Buy", "ABC.US", "Example Corp", "OPEN BUY 93/95 @ 85.40", -7942.20])

        content = BytesIO()
        workbook.save(content)

        purchases, errors = read_purchases(content.getvalue())

        self.assertEqual(errors, [])
        self.assertEqual([purchase["ticker"] for purchase in purchases], ["ABC", "ABC"])
        self.assertEqual([purchase["name"] for purchase in purchases], ["Example Corp", "Example Corp"])
        self.assertEqual([purchase["quantity"] for purchase in purchases], [Decimal("2"), Decimal("93")])
        self.assertEqual([purchase["price"] for purchase in purchases], [Decimal("85.20"), Decimal("85.40")])

    def test_xstation_uses_comment_quantity_instead_of_amount(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Time", "Type", "Symbol", "Comment", "Amount", "Price"])
        sheet.append([datetime(2026, 9, 11), "Buy", "WEC.US", "Buy 7/18 @ 106.05", 18, 106.05])

        content = BytesIO()
        workbook.save(content)

        purchases, errors = read_purchases(content.getvalue())

        self.assertEqual(errors, [])
        self.assertEqual(purchases[0]["quantity"], 7)
        self.assertEqual(purchases[0]["price"], Decimal("106.05"))

    def test_xstation_uses_comment_quantity_when_amount_is_negative(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Time", "Type", "Symbol", "Comment", "Amount", "Price"])
        sheet.append([datetime(2026, 9, 11), "Buy", "WEC.US", "Buy 7/18 @ 106.05", -18, 106.05])

        content = BytesIO()
        workbook.save(content)

        purchases, errors = read_purchases(content.getvalue())

        self.assertEqual(errors, [])
        self.assertEqual(purchases[0]["quantity"], 7)

    def test_broadcom_purchase_is_adjusted_for_ten_to_one_split(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Time", "Type", "Symbol", "Comment", "Amount", "Price"])
        sheet.append([datetime(2023, 10, 31), "Buy", "AVGO.US", "Buy 1 @ 837.92", 1, 837.92])

        content = BytesIO()
        workbook.save(content)

        purchases, errors = read_purchases(content.getvalue())

        self.assertEqual(errors, [])
        self.assertEqual(purchases[0]["quantity"], Decimal("10"))
        self.assertEqual(purchases[0]["price"], Decimal("83.792"))
        self.assertEqual(purchases[0]["date"], datetime(2023, 10, 31).date())


if __name__ == "__main__":
    unittest.main()