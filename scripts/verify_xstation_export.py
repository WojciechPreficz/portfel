"""Reconcile an XStation export against the importer in an isolated in-memory DB.

Run with the backend dependencies: python scripts/verify_xstation_export.py export.xlsx
No source workbook or application database is modified; no quotes are downloaded.
"""

import argparse
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.database import Base
from app.models import Portfolio, Price
from app.routers.transactions import import_transactions
from app.services.portfolio import build_summary
from app.services.symbol_resolver import normalise_ticker

D = Decimal


def independent_xirr(flows):
    """Independent Newton iteration for the conventional deposit/terminal flows."""
    start = min(day for day, _amount in flows)
    rate = 0.1
    for _ in range(100):
        npv = derivative = 0.0
        for day, amount in flows:
            years = (day - start).days / 365
            npv += float(amount) / (1 + rate) ** years
            derivative -= years * float(amount) / (1 + rate) ** (years + 1)
        next_rate = rate - npv / derivative
        if abs(next_rate - rate) < 1e-12:
            return D(str(next_rate)) * 100
        rate = next_rate
    raise AssertionError("Independent XIRR did not converge")


def verify(path):
    content = path.read_bytes()
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    cash_sheet = workbook["Cash Operations"]
    cash_sheet.reset_dimensions()
    rows = list(cash_sheet.values)
    header = next(i for i, row in enumerate(rows) if {"Type", "Time", "Amount"}.issubset(row))
    columns = {name: rows[header].index(name) for name in ("Type", "Time", "Amount")}
    totals = defaultdict(lambda: D("0"))
    counts = defaultdict(int)
    external_flows = []
    for row in rows[header + 1:]:
        if len(row) <= max(columns.values()) or not isinstance(row[columns["Time"]], datetime):
            continue
        kind, day, amount = row[columns["Type"]], row[columns["Time"]].date(), D(str(row[columns["Amount"]]))
        totals[kind] += amount
        counts[kind] += 1
        if kind in {"Deposit", "Withdrawal"}:
            external_flows.append((day, -amount))
    expected_cash = sum(totals.values())

    open_sheet = workbook["Open Positions"]
    open_sheet.reset_dimensions()
    rows = list(open_sheet.values)
    report_day = next(row[1].date() for row in rows if row and row[0] == "Data as of report generated")
    expected_value = next(D(str(row[2])) for row in rows if len(row) > 2 and row[1] == "Open position value")
    expected_profit = next(D(str(row[2])) for row in rows if len(row) > 2 and row[1] == "Open position profit")
    header = next(i for i, row in enumerate(rows) if {"Ticker", "Volume", "Value", "Net Profit"}.issubset(row))
    columns = {name: rows[header].index(name) for name in ("Ticker", "Volume", "Value", "Category")}
    holdings = {}
    for row in rows[header + 1:]:
        if len(row) > max(columns.values()) and row[columns["Category"]] in {"STOCK", "ETF"}:
            holdings[normalise_ticker(row[columns["Ticker"]])] = (
                D(str(row[columns["Volume"]])), D(str(row[columns["Value"]])),
            )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        portfolio = Portfolio(name="Verification")
        db.add(portfolio)
        db.commit()
        with patch("app.services.symbol_resolver._fast_currency", return_value=None):
            result = import_transactions(UploadFile(filename=path.name, file=BytesIO(content)), "xstation5", portfolio.id, db)
        assert result.errors == [], result.errors
        from app.models import Instrument
        from sqlalchemy import select
        for instrument in db.scalars(select(Instrument)).all():
            if instrument.ticker in holdings:
                qty, value = holdings[instrument.ticker]
                # Mark holdings at the source report's PLN value, not a later market quote.
                db.add(Price(instrument_id=instrument.id, date=report_day, close=value / qty, currency="PLN"))
        db.commit()
        with patch("app.services.portfolio.date") as reporting_date:
            reporting_date.today.return_value = report_day
            summary = build_summary(db, portfolio.id)
        actual_qty = {p["instrument"].ticker: p["quantity"] for p in summary["positions"]}
        assert actual_qty == {ticker: qty for ticker, (qty, _value) in holdings.items()}, (actual_qty, holdings)
        assert abs(summary["value_pln"] - expected_value) < D("0.01")
        assert abs(summary["cost_pln"] - (expected_value - expected_profit)) < D("0.01")
        assert abs(summary["pnl_pln"] - expected_profit) < D("0.01")
        assert abs(summary["cash_pln"] - expected_cash) < D("0.01")
        external_flows.append((report_day, expected_value + expected_cash))
        reference_xirr = independent_xirr(external_flows)
        assert abs(summary["xirr_pct"] - reference_xirr) < D("0.000001")
        print("Operation counts:", dict(counts))
        print("Imported trades:", result.imported, "funding:", result.deposits)
        print("Holdings reconciled:", len(holdings))
        for key in ("value_pln", "cost_pln", "pnl_pln", "cash_pln", "total_value_pln", "xirr_pct"):
            print(key, summary[key].quantize(D("0.000001")))
        print("Independent XIRR:", reference_xirr.quantize(D("0.000001")))
        print("PASS: quantities, asset value, cost, P/L, cash and XIRR reconcile.")
    engine.dispose()
    workbook.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    verify(parser.parse_args().export)
