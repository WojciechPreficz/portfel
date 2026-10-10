from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AssetCashFlow, FxRate, Instrument, Portfolio, Price, Transaction
from app.services.portfolio import build_history, portfolio_value_on, position_metrics

D = Decimal
TODAY = date.today()
START = TODAY - timedelta(days=10)


def day(offset):
    return START + timedelta(days=offset)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([Portfolio(id=1, name="First"), Portfolio(id=2, name="Second")])
        for instrument_id, kind, currency in [
            (1, "stock_us", "USD"), (2, "real_estate", "PLN"),
            (3, "stock_pl", "PLN"), (4, "stock_us", "GBP"),
            (5, "stock_pl", "PLN"),
        ]:
            session.add(Instrument(id=instrument_id, ticker=str(instrument_id),
                                   name=str(instrument_id), type=kind, currency=currency,
                                   provider="manual", symbol=str(instrument_id)))
        session.flush()
        for portfolio, instrument, offset, kind, quantity in [
            (1, 1, 0, "BUY", "2"), (2, 1, 1, "BUY", "3"),
            (1, 1, 3, "SELL", "1"), (1, 1, 4, "SELL", "1"),
            (1, 1, 6, "BUY", "1"), (1, 1, 6, "BUY", "2"),
            (1, 1, 6, "SELL", "2"), (1, 1, 11, "BUY", "99"),
            (1, 2, 0, "BUY", "1"), (1, 4, 0, "BUY", "1"),
            (1, 5, 0, "BUY", "1"),
        ]:
            session.add(Transaction(portfolio_id=portfolio, instrument_id=instrument,
                                    date=day(offset), type=kind, quantity=D(quantity),
                                    price=D("10"), currency="PLN", commission=D("0")))
        for instrument, offset, close, currency in [
            (1, -1, "10", "USD"), (1, 3, "12", "USD"),
            (1, 6, "20", "EUR"), (1, 11, "999", "GBP"),
            (2, -1, "1000", "PLN"), (2, 4, "1200", "PLN"),
            (3, 8, "5", "PLN"), (4, 0, "100", "GBP"),
        ]:
            session.add(Price(instrument_id=instrument, date=day(offset),
                              close=D(close), currency=currency))
        for pair, offset, rate in [
            ("USDPLN", -1, "4"), ("USDPLN", 2, "5"),
            ("EURPLN", 5, "6"), ("EURPLN", 11, "9"),
        ]:
            session.add(FxRate(pair=pair, date=day(offset), rate=D(rate)))
        session.add(AssetCashFlow(portfolio_id=1, instrument_id=2, date=day(2),
                                  kind="CAPEX", amount=D("50"), tax_amount=D("0"),
                                  currency="PLN"))
        session.commit()
        yield session
    engine.dispose()


@pytest.mark.parametrize("portfolio,values", [
    (1, ["1080", "1100", "1060", "1200", "1200", "1320", "1320", "1320"]),
    (2, [None, "150", "180", "180", "180", "360", "360", "360"]),
    (None, ["1080", "1250", "1240", "1380", "1380", "1680", "1680", "1680"]),
])
def test_history_preserves_valuations_and_portfolio_scope(db, portfolio, values):
    expected = [{"date": day(offset), "value_pln": D(value)}
                for offset, value in zip([0, 2, 3, 4, 5, 6, 8, 10], values)
                if value is not None]
    assert build_history(db, portfolio) == expected


def test_history_uses_bounded_queries_without_cost_or_capex_lookups(db):
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        build_history(db, 1)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert len(statements) == 5
    assert not any("asset_cash_flows" in statement for statement in statements)


def test_history_keeps_zero_values_after_full_sale(db):
    db.add(Transaction(portfolio_id=2, instrument_id=1, date=day(4), type="SELL",
                       quantity=D("3"), price=D("12"), currency="PLN", commission=D("0")))
    db.commit()
    assert [point["value_pln"] for point in build_history(db, 2)] == [
        D("150"), D("180"), D("0"), D("0"), D("0"), D("0"), D("0"),
    ]


def test_empty_and_future_only_portfolios_have_no_history(db):
    assert build_history(db, 99) == []
    db.query(Transaction).filter(Transaction.portfolio_id == 2).delete()
    db.add(Transaction(portfolio_id=2, instrument_id=1, date=day(11), type="BUY",
                       quantity=D("1"), price=D("12"), currency="PLN", commission=D("0")))
    db.commit()
    assert build_history(db, 2) == []


def test_stock_costs_and_valuation_do_not_query_capex(db):
    transactions = list(db.scalars(select(Transaction).where(
        Transaction.portfolio_id == 1, Transaction.instrument_id == 1,
    )).all())
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        quantity, average, cost = position_metrics(transactions, db, TODAY)
        assert quantity == D("1")
        assert abs(average - D("10")) < D("0.00000001")
        assert abs(cost - D("10")) < D("0.00000001")
        assert portfolio_value_on(db, transactions, TODAY) == D("120")
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert not any("asset_cash_flows" in statement for statement in statements)


def test_property_costs_still_include_capex(db):
    transactions = list(db.scalars(select(Transaction).where(Transaction.instrument_id == 2)).all())
    assert position_metrics(transactions, db, TODAY) == (D("1"), D("60"), D("60"))
