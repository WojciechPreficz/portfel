import unittest
from io import BytesIO

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.database import Base
from app.models import Instrument, Portfolio, Transaction
from app.routers.transactions import _infer_import_instrument_type, import_transactions


class TransactionRouterTest(unittest.TestCase):
    def test_neu_import_is_classified_as_polish_stock(self):
        self.assertEqual(_infer_import_instrument_type("NEU", "NEU", None), "stock_pl")

    def test_pl_suffix_is_classified_as_polish_stock(self):
        self.assertEqual(_infer_import_instrument_type("DEBICA", "DEBICA.PL", None), "stock_pl")

    def test_bossa_import_matches_vanguard_by_isin_and_uses_amsterdam_symbol(self):
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
            self.assertEqual(len(db.scalars(select(Instrument)).all()), 1)
            self.assertEqual(instrument.symbol, "V80A.AS")
            self.assertEqual(instrument.provider, "yahoo")
            transaction = db.scalar(select(Transaction))
            self.assertEqual(transaction.portfolio_id, portfolio.id)
            self.assertEqual(transaction.instrument_id, instrument.id)
        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()