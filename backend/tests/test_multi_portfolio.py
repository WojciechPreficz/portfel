import unittest
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import CashDeposit, Instrument, Portfolio, Price, Transaction
from app.routers.portfolio import delete_holdings, delete_portfolio
from app.services.adapters.base import QuotePoint
from app.services.portfolio import build_summary, fx_on, xirr
from app.services.quotes import refresh_quotes


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

    def test_missing_price_is_reported_as_unknown_not_zero_or_total_loss(self):
        self.db.query(Price).delete()
        self.db.commit()

        summary = build_summary(self.db, self.first.id)
        position = summary["positions"][0]

        self.assertIsNone(position["price"])
        self.assertIsNone(position["market_value_pln"])
        self.assertIsNone(position["pnl_pln"])
        self.assertIsNone(position["weight_pct"])
        self.assertIsNone(summary["value_pln"])
        self.assertIsNone(summary["change_1d_pln"])
        self.assertIsNone(summary["pnl_pln"])
        self.assertIsNone(summary["xirr_pct"])

    @patch("app.services.quotes.YahooAdapter.fetch_many", return_value={"TEST.WA": []})
    @patch("app.services.quotes.get_adapter")
    def test_quote_refresh_reports_instruments_without_any_quote(
        self, get_adapter, _fetch_many
    ):
        get_adapter.return_value.fetch_history.return_value = []

        result = refresh_quotes(self.db)

        self.assertEqual(result["errors"], ["TEST: brak prawidłowych notowań w Stooq i Yahoo Finance"])
        _fetch_many.assert_called_once_with(
            {"TEST.WA": (date.today() - timedelta(days=5), date.today(), "PLN")}
        )

    @patch("app.services.quotes.fetch_fx_history", return_value=[])
    @patch("app.services.quotes.YahooAdapter.fetch_many", return_value={})
    @patch("app.services.quotes.get_adapter")
    def test_stooq_history_requests_run_concurrently(
        self, get_adapter, _yahoo_fetch_many, _fetch_fx
    ):
        second_instrument = Instrument(
            ticker="TEST2",
            name="Second test company",
            type="stock_pl",
            currency="PLN",
            provider="stooq",
            symbol="test2",
            unit="share",
        )
        self.db.add(second_instrument)
        self.db.flush()
        self.db.add(
            Transaction(
                portfolio_id=self.first.id,
                instrument_id=second_instrument.id,
                type="BUY",
                quantity=Decimal("1"),
                price=Decimal("10"),
                currency="PLN",
                date=date.today(),
                commission=Decimal("0"),
            )
        )
        self.db.commit()

        both_requests_started = Barrier(2)

        def fetch_history(symbol, start, end, currency):
            both_requests_started.wait(timeout=3)
            return [
                QuotePoint(date=date.today(), close=Decimal("12"), currency=currency)
            ]

        get_adapter.return_value.fetch_history.side_effect = fetch_history

        result = refresh_quotes(self.db)

        self.assertEqual(result["errors"], [])
        self.assertEqual(get_adapter.return_value.fetch_history.call_count, 2)

    def test_fx_on_returns_none_when_the_currency_rate_is_missing(self):
        self.assertIsNone(fx_on(self.db, "GBP", date.today()))

    def test_missing_market_fx_makes_position_value_unknown(self):
        self.instrument.currency = "GBP"
        self.db.query(Transaction).filter(
            Transaction.instrument_id == self.instrument.id
        ).update({Transaction.currency: "GBP"})
        self.db.query(Price).filter(
            Price.instrument_id == self.instrument.id
        ).update({Price.currency: "GBP"})
        self.db.commit()

        position = build_summary(self.db, self.first.id)["positions"][0]

        self.assertIsNone(position["market_value_pln"])
        self.assertIsNone(position["pnl_pln"])

    def test_missing_purchase_fx_keeps_market_value_but_not_pln_cost_or_pnl(self):
        self.db.query(Transaction).filter(
            Transaction.instrument_id == self.instrument.id
        ).update({Transaction.currency: "GBP"})
        self.db.commit()

        summary = build_summary(self.db, self.first.id)
        position = summary["positions"][0]

        self.assertEqual(position["market_value_pln"], Decimal("24"))
        self.assertIsNone(position["cost_pln"])
        self.assertIsNone(position["pnl_pln"])
        self.assertIsNone(summary["cost_pln"])
        self.assertIsNone(summary["pnl_pln"])

    @patch("app.services.quotes.fetch_fx_history", return_value=[])
    @patch("app.services.quotes.YahooAdapter.fetch_many", return_value={"SAP.DE": []})
    def test_refresh_is_scoped_and_uses_first_transaction_date(
        self, yahoo_fetch_many, fetch_fx
    ):
        foreign = Instrument(
            ticker="SAP",
            name="SAP SE",
            type="stock_intl",
            currency="EUR",
            provider="yahoo",
            symbol="SAP.DE",
            unit="share",
        )
        self.db.add(foreign)
        self.db.flush()
        first_transaction = date.today() - timedelta(days=45)
        self.db.add(
            Transaction(
                portfolio_id=self.first.id,
                instrument_id=foreign.id,
                type="BUY",
                quantity=Decimal("1"),
                price=Decimal("100"),
                currency="PLN",
                date=first_transaction,
                commission=Decimal("0"),
            )
        )
        self.db.commit()

        refresh_quotes(self.db, instrument_ids=[foreign.id])

        self.assertEqual(
            yahoo_fetch_many.call_args.args[0],
            {"SAP.DE": (first_transaction, date.today(), "EUR")},
        )
        fetch_fx.assert_called_once()
        self.assertEqual(fetch_fx.call_args.args[0], "eur")
        self.assertEqual(fetch_fx.call_args.args[1], first_transaction)

    def test_clearing_one_portfolio_preserves_shared_prices_and_other_holdings(self):
        result = delete_holdings(self.first.id, self.db)

        self.assertEqual(result["deleted_transactions"], 1)
        self.assertEqual(result["deleted_prices"], 0)
        self.assertEqual(len(self.db.scalars(select(Price)).all()), 1)
        self.assertEqual(build_summary(self.db, self.second.id)["positions"][0]["quantity"], Decimal("3"))

    def test_deleting_portfolio_removes_its_data_and_updates_aggregate(self):
        first_id = self.first.id
        self.db.add(CashDeposit(
            portfolio_id=first_id,
            date=date.today(),
            amount=Decimal("100"),
            currency="PLN",
        ))
        self.db.commit()

        result = delete_portfolio(first_id, self.db)

        self.assertEqual(result["deleted_portfolio"], first_id)
        self.assertIsNone(self.db.get(Portfolio, first_id))
        self.assertEqual(self.db.scalars(select(Transaction).where(Transaction.portfolio_id == first_id)).all(), [])
        self.assertEqual(self.db.scalars(select(CashDeposit).where(CashDeposit.portfolio_id == first_id)).all(), [])
        self.assertEqual(len(self.db.scalars(select(Price)).all()), 1)
        self.assertEqual(build_summary(self.db)["positions"][0]["quantity"], Decimal("3"))

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