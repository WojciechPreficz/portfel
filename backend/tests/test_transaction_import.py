import unittest
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from app.services.transaction_import import read_purchases


class TransactionImportTest(unittest.TestCase):
    def test_xstation_uses_explicit_amount_instead_of_comment_fraction(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Time", "Type", "Symbol", "Comment", "Amount", "Price"])
        sheet.append([datetime(2026, 9, 11), "Buy", "WEC.US", "Buy 7/18 @ 106.05", 18, 106.05])

        content = BytesIO()
        workbook.save(content)

        purchases, errors = read_purchases(content.getvalue())

        self.assertEqual(errors, [])
        self.assertEqual(purchases[0]["quantity"], 18)
        self.assertEqual(purchases[0]["price"], Decimal("106.05"))

    def test_xstation_uses_absolute_amount_when_amount_is_negative(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Time", "Type", "Symbol", "Comment", "Amount", "Price"])
        sheet.append([datetime(2026, 9, 11), "Buy", "WEC.US", "Buy 7/18 @ 106.05", -18, 106.05])

        content = BytesIO()
        workbook.save(content)

        purchases, errors = read_purchases(content.getvalue())

        self.assertEqual(errors, [])
        self.assertEqual(purchases[0]["quantity"], 18)

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