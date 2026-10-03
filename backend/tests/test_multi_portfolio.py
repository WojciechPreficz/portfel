import unittest
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import CashDeposit, Instrument, Portfolio, Price, Transaction
from app.routers.portfolio import delete_holdings
from app.services.portfolio import build_summary, xirr


class MultiPortfolioTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.first = Portfolio(name="Pierwszy")
        self.second = Portfolio(name="Drugi")
        self.instrument = Instrument(
            ticker="TEST",
            name="Test company",
            type="stock_pl",
            currency="PLN",
            provider="stooq",
            symbol="test",
            unit="share",
        )
        self.db.add_all([self.first, self.second, self.instrument])
        self.db.flush()
        self.db.add_all(
            [
                Transaction(
                    portfolio_id=self.first.id,
                    instrument_id=self.instrument.id,
                    type="BUY",
                    quantity=Decimal("2"),
                    price=Decimal("10"),
                    currency="PLN",
                    date=date.today(),
                    commission=Decimal("0"),
                ),
                Transaction(
                    portfolio_id=self.second.id,
                    instrument_id=self.instrument.id,
                    type="BUY",
                    quantity=Decimal("3"),
                    price=Decimal("10"),
                    currency="PLN",
                    date=date.today(),
                    commission=Decimal("0"),
                ),
                Price(
                    instrument_id=self.instrument.id,
                    date=date.today(),
                    close=Decimal("12"),
                    currency="PLN",
                ),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_summary_is_scoped_and_aggregate_includes_each_portfolio(self):
        first = build_summary(self.db, self.first.id)
        second = build_summary(self.db, self.second.id)
        aggregate = build_summary(self.db)

        self.assertEqual(first["positions"][0]["quantity"], Decimal("2"))
        self.assertEqual(second["positions"][0]["quantity"], Decimal("3"))
        self.assertEqual(aggregate["positions"][0]["quantity"], Decimal("5"))

    def test_clearing_one_portfolio_preserves_shared_prices_and_other_holdings(self):
        result = delete_holdings(self.first.id, self.db)

        self.assertEqual(result["deleted_transactions"], 1)
        self.assertEqual(result["deleted_prices"], 0)
        self.assertEqual(len(self.db.scalars(select(Price)).all()), 1)
        self.assertEqual(build_summary(self.db, self.second.id)["positions"][0]["quantity"], Decimal("3"))

    def test_aggregate_return_includes_transactions_for_portfolios_without_deposits(self):
        start = date.today() - timedelta(days=30)
        self.db.add(CashDeposit(portfolio_id=self.first.id, date=start, amount=Decimal("20"), currency="PLN"))
        self.db.commit()

        summary = build_summary(self.db)
        expected = xirr(
            [
                (start, Decimal("-20")),
                (date.today(), Decimal("-30")),
                (date.today(), Decimal("60")),
            ]
        )

        self.assertEqual(summary["xirr_pct"], expected * Decimal("100"))


if __name__ == "__main__":
    unittest.main()