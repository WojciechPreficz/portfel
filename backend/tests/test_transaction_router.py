import unittest
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.database import Base
from app.models import Instrument, Portfolio, Transaction
from app.routers.transactions import create_transaction, import_transactions
from app.schemas import TransactionCreate
from app.services.portfolio import position_metrics


class TransactionRouterTest(unittest.TestCase):
    def test_gold_buy_stores_entered_pln_total_and_uses_it_as_basis(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            portfolio = Portfolio(name="IKE")
            instrument = Instrument(
                ticker="XAU-9999",
                name="Złoto 999.9 (24K)",
                type="gold",
                currency="USD",
                provider="yahoo",
                symbol="GC=F",
                unit="gram",
            )
            db.add_all([portfolio, instrument])
            db.flush()

            transaction = create_transaction(
                TransactionCreate(
                    portfolio_id=portfolio.id,
                    instrument_id=instrument.id,
                    quantity=Decimal("50"),
                    price=Decimal("0"),
                    purchase_price_pln=Decimal("13250"),
                    currency="PLN",
                    date=date(2026, 9, 15),
                ),
                db,
            )

            self.assertEqual(transaction.purchase_price_pln, Decimal("13250"))
            self.assertEqual(transaction.price, Decimal("0"))
            _quantity, avg_cost, cost_pln = position_metrics(
                [db.get(Transaction, transaction.id)], db, date(2026, 9, 15)
            )
            self.assertEqual(avg_cost, Decimal("265"))
            self.assertEqual(cost_pln, Decimal("13250"))
        finally:
            db.close()
            engine.dispose()

    def test_bossa_import_matches_vanguard_by_isin_without_mutating_shared_instrument(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            portfolio = Portfolio(name="IKE")
            instrument = Instrument(
                ticker="V80A",
                isin="IE00BMVB5R75",
                name="Vanguard LifeStrategy 80% Equity UCITS ETF Acc EUR",
                type="etf",
                currency="EUR",
                provider="yahoo",
                symbol="V80A.DE",
                unit="share",
            )
            db.add_all([portfolio, instrument])
            db.flush()

            content = (
                "Data;Walor;Rachunek;Waluta;Liczba;Strona;Cena;Wartość przed prowizją;Prowizja;Wartość po prowizji\n"
                "10.10.2022 09:04:13;Vanguard LifeStrategy 80% Equity UCITS ETF;IKE 816742;PLN;132,00;K;130,307;17200,49;49,88;17250,37\n"
            ).encode()
            result = import_transactions(
                file=UploadFile(filename="bossa.csv", file=BytesIO(content)),
                source="bossa",
                portfolio_id=portfolio.id,
                db=db,
            )

            self.assertEqual(result.imported, 1)
            self.assertEqual(result.instrument_ids, [instrument.id])
            self.assertEqual(len(db.scalars(select(Instrument)).all()), 1)
            self.assertEqual(instrument.symbol, "V80A.DE")
            self.assertEqual(instrument.provider, "yahoo")
            transaction = db.scalar(select(Transaction))
            self.assertEqual(transaction.portfolio_id, portfolio.id)
            self.assertEqual(transaction.instrument_id, instrument.id)
        finally:
            db.close()
            engine.dispose()

    @patch("app.services.symbol_resolver._fast_currency", return_value="EUR")
    def test_import_resolves_european_symbol_without_name_based_matching(self, _currency):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = Session(engine)
        try:
            portfolio = Portfolio(name="IKE")
            unrelated = Instrument(
                ticker="OTHER",
                name="Example Corp Holdings",
                type="stock_pl",
                currency="PLN",
                provider="stooq",
                symbol="other",
                unit="share",
            )
            db.add_all([portfolio, unrelated])
            db.flush()

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Cash Operations"
            sheet.append(["Time", "Type", "Ticker", "Instrument", "Comment", "Amount"])
            sheet.append(
                [
                    datetime(2026, 9, 11),
                    "Buy",
                    "SAP.DE",
                    "Example Corp",
                    "BUY 1 @ 100",
                    -100,
                ]
            )
            content = BytesIO()
            workbook.save(content)

            result = import_transactions(
                file=UploadFile(filename="xstation.xlsx", file=BytesIO(content.getvalue())),
                source="xstation5",
                portfolio_id=portfolio.id,
                db=db,
            )

            imported = db.get(Instrument, result.instrument_ids[0])
            self.assertEqual(result.imported, 1)
            self.assertNotEqual(imported.id, unrelated.id)
            self.assertEqual(imported.ticker, "SAP")
            self.assertEqual(imported.type, "stock_intl")
            self.assertEqual(imported.currency, "EUR")
            self.assertEqual(imported.provider, "yahoo")
            self.assertEqual(imported.symbol, "SAP.DE")
            self.assertEqual(unrelated.name, "Example Corp Holdings")
            self.assertEqual(unrelated.type, "stock_pl")
            self.assertEqual(unrelated.provider, "stooq")
            self.assertEqual(unrelated.symbol, "other")
            _currency.assert_called_once_with("SAP.DE")
        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()