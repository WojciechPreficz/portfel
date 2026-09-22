from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import FxRate, Instrument, Price, Transaction

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def _as_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def fx_on(db: Session, currency: str, on_date: date, cache: dict | None = None) -> Decimal:
    if currency == "PLN":
        return Decimal("1")
    pair = f"{currency}PLN"
    key = (pair, on_date)
    if cache is not None and key in cache:
        return cache[key]
    rate = db.scalar(
        select(FxRate.rate)
        .where(FxRate.pair == pair, FxRate.date <= on_date)
        .order_by(FxRate.date.desc())
        .limit(1)
    )
    result = _as_decimal(rate) if rate is not None else Decimal("1")
    if cache is not None:
        cache[key] = result
    return result


def price_on(db: Session, instrument_id: int, on_date: date, cache: dict | None = None):
    key = (instrument_id, on_date)
    if cache is not None and key in cache:
        return cache[key]
    row = db.scalar(
        select(Price)
        .where(Price.instrument_id == instrument_id, Price.date <= on_date)
        .order_by(Price.date.desc())
        .limit(1)
    )
    if cache is not None:
        cache[key] = row
    return row


def _signed_qty(tx: Transaction) -> Decimal:
    qty = _as_decimal(tx.quantity)
    return qty if tx.type == "BUY" else -qty


def holdings_as_of(transactions: list[Transaction], on_date: date) -> dict[int, list[Transaction]]:
    grouped: dict[int, list[Transaction]] = {}
    for tx in transactions:
        if tx.date <= on_date:
            grouped.setdefault(tx.instrument_id, []).append(tx)
    return grouped


def position_metrics(txs: list[Transaction], db: Session, on_date: date, fx_cache=None):
    qty = ZERO
    buy_qty = ZERO
    buy_cost_pln = ZERO
    for tx in txs:
        signed = _signed_qty(tx)
        qty += signed
        fx = fx_on(db, tx.currency, tx.date, fx_cache)
        if tx.type == "BUY":
            buy_qty += _as_decimal(tx.quantity)
            buy_cost_pln += (_as_decimal(tx.quantity) * _as_decimal(tx.price) + _as_decimal(tx.commission)) * fx
    avg_cost = (buy_cost_pln / buy_qty) if buy_qty else ZERO
    cost_pln = avg_cost * qty if qty else ZERO
    return qty, avg_cost, cost_pln


def portfolio_value_on(
    db: Session,
    transactions: list[Transaction],
    on_date: date,
    price_cache=None,
    fx_cache=None,
) -> Decimal:
    grouped = holdings_as_of(transactions, on_date)
    total = ZERO
    for instrument_id, txs in grouped.items():
        qty, _avg, _cost = position_metrics(txs, db, on_date, fx_cache)
        if qty == 0:
            continue
        px = price_on(db, instrument_id, on_date, price_cache)
        if px is None:
            continue
        fx = fx_on(db, px.currency, on_date, fx_cache)
        total += qty * _as_decimal(px.close) * fx
    return total


def build_summary(db: Session) -> dict:
    transactions = list(
        db.scalars(
            select(Transaction).options(selectinload(Transaction.instrument)).order_by(Transaction.date)
        ).all()
    )
    instruments = {i.id: i for i in db.scalars(select(Instrument)).all()}
    today = date.today()
    fx_cache: dict = {}
    price_cache: dict = {}
    grouped = holdings_as_of(transactions, today)
    positions = []
    total_value = ZERO
    total_prev = ZERO
    total_cost = ZERO
    as_of = None

    for instrument_id, txs in grouped.items():
        instrument = instruments.get(instrument_id) or txs[0].instrument
        qty, avg_cost, cost_pln = position_metrics(txs, db, today, fx_cache)
        if qty == 0:
            continue
        px = price_on(db, instrument_id, today, price_cache)
        prev_px = price_on(db, instrument_id, today - timedelta(days=1), price_cache)
        price = _as_decimal(px.close) if px else None
        price_date = px.date if px else None
        if price_date and (as_of is None or price_date > as_of):
            as_of = price_date
        currency = px.currency if px else instrument.currency
        fx = fx_on(db, currency, today, fx_cache)
        market = (qty * price * fx) if price is not None else ZERO
        prev_price = _as_decimal(prev_px.close) if prev_px else price
        prev_fx = fx_on(db, prev_px.currency if prev_px else currency, today - timedelta(days=1), fx_cache)
        prev_value = qty * (prev_price or ZERO) * prev_fx if prev_price is not None else market
        change_1d = market - prev_value
        change_1d_pct = (change_1d / prev_value * HUNDRED) if prev_value else None
        pnl = market - cost_pln
        pnl_pct = (pnl / cost_pln * HUNDRED) if cost_pln else None
        total_value += market
        total_prev += prev_value
        total_cost += cost_pln
        positions.append(
            {
                "instrument": instrument,
                "quantity": qty,
                "avg_cost": avg_cost,
                "cost_pln": cost_pln,
                "price": price,
                "price_date": price_date,
                "market_value_pln": market,
                "pnl_pln": pnl,
                "pnl_pct": pnl_pct,
                "change_1d_pln": change_1d,
                "change_1d_pct": change_1d_pct,
                "weight_pct": None,
            }
        )

    for pos in positions:
        pos["weight_pct"] = (pos["market_value_pln"] / total_value * HUNDRED) if total_value else ZERO

    positions.sort(key=lambda p: p["market_value_pln"], reverse=True)
    change_1d = total_value - total_prev
    return {
        "value_pln": total_value,
        "value_prev_pln": total_prev,
        "change_1d_pln": change_1d,
        "change_1d_pct": (change_1d / total_prev * HUNDRED) if total_prev else None,
        "cost_pln": total_cost,
        "pnl_pln": total_value - total_cost,
        "pnl_pct": ((total_value - total_cost) / total_cost * HUNDRED) if total_cost else None,
        "as_of": as_of,
        "positions": positions,
    }


def build_history(db: Session) -> list[dict]:
    transactions = list(db.scalars(select(Transaction).order_by(Transaction.date)).all())
    if not transactions:
        return []
    start = transactions[0].date
    end = date.today()
    price_dates = [
        d
        for d in db.scalars(select(Price.date).where(Price.date >= start).distinct().order_by(Price.date)).all()
    ]
    fx_dates = [
        d
        for d in db.scalars(select(FxRate.date).where(FxRate.date >= start).distinct().order_by(FxRate.date)).all()
    ]
    days = sorted(set(price_dates) | set(fx_dates) | {end})
    days = [d for d in days if start <= d <= end]
    if not days:
        days = [end]
    fx_cache: dict = {}
    price_cache: dict = {}
    series = []
    last_value = None
    for d in days:
        value = portfolio_value_on(db, transactions, d, price_cache, fx_cache)
        if value == 0 and last_value is None:
            continue
        last_value = value
        series.append({"date": d, "value_pln": value})
    return series
