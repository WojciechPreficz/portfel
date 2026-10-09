from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.database import Base
from app.models import AssetCashFlow, CashDeposit, CashMovement, FxRate, Instrument, Portfolio, Price, PropertyDetails, Transaction
from app.routers.portfolio import delete_portfolio
from app.routers.transactions import import_transactions
from app.services.portfolio import build_property_metrics, build_summary, position_metrics, xirr
from app.services.transaction_import import read_cash_movements, read_deposits, read_purchases

D = Decimal
TODAY = date.today()
YEAR_AGO = TODAY - timedelta(days=365)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Portfolio(id=1, name="First"), Portfolio(id=2, name="Second"),
            Instrument(id=1, ticker="TEST", name="Test", type="stock_pl", currency="PLN", provider="stooq", symbol="test", unit="share"),
        ])
        session.commit()
        yield session
    engine.dispose()


def trade(db, day, kind, qty, price, portfolio=1, currency="PLN", exact_pln=None):
    tx = Transaction(portfolio_id=portfolio, instrument_id=1, date=day, type=kind,
                     quantity=D(qty), price=D(price), commission=D("0"), currency=currency,
                     purchase_price_pln=D(exact_pln) if exact_pln is not None else None)
    db.add(tx)
    db.flush()
    return tx


def test_cost_pool_resets_after_full_sale_and_is_scoped_per_portfolio(db):
    trade(db, YEAR_AGO, "BUY", "1", "100")
    trade(db, TODAY - timedelta(days=180), "SELL", "1", "130")
    trade(db, TODAY - timedelta(days=90), "BUY", "1", "200")
    trade(db, YEAR_AGO, "BUY", "1", "400", portfolio=2)
    db.add(Price(instrument_id=1, date=TODAY, close=D("200"), currency="PLN"))
    db.commit()
    first = build_summary(db, 1)
    assert first["cost_pln"] == D("200")
    assert first["pnl_pln"] == 0
    assert build_summary(db)["cost_pln"] == D("600")


def test_partial_sale_removes_moving_average_cost_before_next_purchase(db):
    txs = [trade(db, YEAR_AGO, "BUY", "2", "100"),
           trade(db, TODAY - timedelta(days=100), "SELL", "1", "150"),
           trade(db, TODAY, "BUY", "1", "200")]
    qty, average, cost = position_metrics(txs, db, TODAY)
    assert (qty, average, cost) == (D("2"), D("150"), D("300"))


def test_missing_fx_in_fully_closed_lot_does_not_poison_new_cost(db):
    txs = [trade(db, YEAR_AGO, "BUY", "1", "100", currency="GBP"),
           trade(db, TODAY - timedelta(days=100), "SELL", "1", "150", currency="GBP"),
           trade(db, TODAY, "BUY", "1", "200")]
    assert position_metrics(txs, db, TODAY)[2] == D("200")


def test_deposit_return_includes_uninvested_cash_and_retained_net_income(db):
    db.add(CashDeposit(portfolio_id=1, date=YEAR_AGO, amount=D("1000"), currency="PLN"))
    trade(db, YEAR_AGO, "BUY", "1", "500")
    db.add(Price(instrument_id=1, date=TODAY, close=D("500"), currency="PLN"))
    db.commit()
    summary = build_summary(db, 1)
    assert summary["cash_pln"] == D("500")
    assert abs(summary["xirr_pct"]) < D("0.000001")
    db.add_all([
        CashMovement(portfolio_id=1, date=TODAY, amount=D("100"), currency="PLN", kind="dividend"),
        CashMovement(portfolio_id=1, date=TODAY, amount=D("-15"), currency="PLN", kind="withholding tax"),
    ])
    db.commit()
    summary = build_summary(db, 1)
    assert summary["cash_pln"] == D("585")
    assert summary["total_value_pln"] == D("1085")
    assert abs(summary["xirr_pct"] - D("8.5")) < D("0.000001")


def test_closed_funded_position_keeps_sale_proceeds_in_terminal_cash(db):
    db.add(CashDeposit(portfolio_id=1, date=YEAR_AGO, amount=D("100"), currency="PLN"))
    trade(db, YEAR_AGO, "BUY", "1", "100")
    trade(db, TODAY, "SELL", "1", "130")
    db.commit()
    summary = build_summary(db, 1)
    assert summary["positions"] == []
    assert summary["cash_pln"] == D("130")
    assert abs(summary["xirr_pct"] - D("30")) < D("0.000001")


def test_stale_property_valuation_has_same_terminal_date_in_all_xirr_metrics(db):
    db.get(Instrument, 1).type = "real_estate"
    db.add(PropertyDetails(instrument_id=1, area_m2=D("50")))
    trade(db, YEAR_AGO, "BUY", "1", "100")
    db.add(Price(instrument_id=1, date=TODAY - timedelta(days=185), close=D("110"), currency="PLN"))
    db.commit()
    summary = build_summary(db, 1)
    metrics = build_property_metrics(db, 1, 1, YEAR_AGO, TODAY)
    assert abs(summary["xirr_pct"] - D("10")) < D("0.000001")
    assert summary["xirr_pct"] == summary["positions"][0]["xirr_pct"] == metrics["xirr_pct"]


def test_future_trades_and_deposits_do_not_affect_current_summary(db):
    trade(db, YEAR_AGO, "BUY", "1", "100")
    trade(db, TODAY + timedelta(days=30), "BUY", "1", "1000")
    db.add_all([
        CashDeposit(portfolio_id=1, date=TODAY + timedelta(days=30), amount=D("2000"), currency="PLN"),
        Price(instrument_id=1, date=TODAY, close=D("110"), currency="PLN"),
    ])
    db.commit()
    assert abs(build_summary(db, 1)["xirr_pct"] - D("10")) < D("0.000001")


def test_currency_cash_is_revalued_on_terminal_date(db):
    db.add_all([
        CashDeposit(portfolio_id=1, date=YEAR_AGO, amount=D("100"), currency="USD"),
        FxRate(pair="USDPLN", date=YEAR_AGO, rate=D("4")),
        FxRate(pair="USDPLN", date=TODAY, rate=D("5")),
    ])
    db.commit()
    summary = build_summary(db, 1)
    assert summary["cash_pln"] == D("500")
    assert abs(summary["xirr_pct"] - D("25")) < D("0.000001")


def test_aggregate_keeps_broker_dividends_in_cash_and_property_rent_external(db):
    db.add(CashDeposit(portfolio_id=1, date=YEAR_AGO, amount=D("100"), currency="PLN"))
    trade(db, YEAR_AGO, "BUY", "1", "100")
    db.add(Instrument(id=2, ticker="HOME", name="Home", type="real_estate", currency="PLN", provider="manual", symbol="home", unit="property"))
    db.flush()
    db.add_all([
        Transaction(portfolio_id=2, instrument_id=2, date=YEAR_AGO, type="BUY", quantity=D("1"), price=D("100"), commission=D("0"), currency="PLN"),
        Price(instrument_id=1, date=TODAY, close=D("110"), currency="PLN"),
        Price(instrument_id=2, date=TODAY, close=D("120"), currency="PLN"),
        CashMovement(portfolio_id=1, date=TODAY, amount=D("10"), currency="PLN", kind="dividend"),
        AssetCashFlow(portfolio_id=2, instrument_id=2, date=TODAY, kind="RENT", amount=D("10"), tax_amount=D("0"), currency="PLN"),
    ])
    db.commit()
    summary = build_summary(db)
    assert summary["cash_pln"] == D("10")
    assert summary["total_value_pln"] == D("240")
    # 200 invested a year ago -> 240 terminal wealth + 10 external rent.
    assert abs(summary["xirr_pct"] - D("25")) < D("0.000001")


def test_missing_cash_currency_rate_makes_total_value_and_xirr_unknown(db):
    db.add(CashDeposit(portfolio_id=1, date=YEAR_AGO, amount=D("100"), currency="GBP"))
    db.commit()
    summary = build_summary(db, 1)
    assert summary["cash_pln"] is None
    assert summary["total_value_pln"] is None
    assert summary["xirr_pct"] is None


def test_same_day_xirr_is_undefined():
    assert xirr([(TODAY, D("-100")), (TODAY, D("100"))]) is None


def export_content():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Cash Operations"
    sheet.append(["Type", "Instrument", "Ticker", "Category", "Time", "Amount", "ID", "Comment"])
    sheet.append(["Deposit", "", "", "", YEAR_AGO, 1000, "1", ""])
    sheet.append(["Stock purchase", "Test", "TEST.US", "STOCK", YEAR_AGO, -500, "2", "OPEN BUY 2 @ 50"])
    sheet.append(["Stock sell", "Test", "TEST.US", "STOCK", TODAY, 300, "3", "CLOSE BUY 1/2 @ 60"])
    sheet.append(["Dividend", "Test", "TEST.US", "STOCK", TODAY, 20, "4", ""])
    sheet.append(["Withholding tax", "Test", "TEST.US", "STOCK", TODAY, -3, "5", ""])
    sheet.append(["Free funds interest", "", "", "", TODAY, 1, "6", ""])
    sheet.append(["Free funds interest tax", "", "", "", TODAY, -0.19, "7", ""])
    sheet.append(["Withdrawal", "", "", "", TODAY, -100, "8", ""])
    sheet.append(["Total", "", "", "", "", 717.81, "", ""])
    content = BytesIO()
    workbook.save(content)
    return content.getvalue()


def test_xstation_import_uses_account_amounts_and_keeps_all_cash_flows(db):
    content = export_content()
    txs, errors = read_purchases(content)
    assert errors == []
    assert [tx["type"] for tx in txs] == ["BUY", "SELL"]
    assert [tx["purchase_price_pln"] for tx in txs] == [D("500"), D("300")]
    assert [tx["quantity"] for tx in txs] == [D("2"), D("1")]
    deposits, errors = read_deposits(content)
    assert errors == []
    assert [row["amount"] for row in deposits] == [D("1000"), D("-100")]
    movements, errors = read_cash_movements(content)
    assert errors == [] and len(movements) == 4
    with patch("app.services.symbol_resolver._fast_currency", return_value="USD"):
        result = import_transactions(UploadFile(filename="export.xlsx", file=BytesIO(content)), "xstation5", 1, db)
    assert result.imported == 2 and result.deposits == 2
    instrument_id = result.instrument_ids[0]
    db.add(Price(instrument_id=instrument_id, date=TODAY, close=D("300"), currency="PLN"))
    db.commit()
    summary = build_summary(db, 1)
    assert summary["cost_pln"] == D("250")  # Exact account cost, no historical USD FX needed.
    assert summary["cash_pln"] == D("717.81")
    assert summary["total_value_pln"] == D("1017.81")
    assert len(db.scalars(select(CashMovement)).all()) == 4
    delete_portfolio(1, db)
    assert db.scalars(select(CashMovement)).all() == []
