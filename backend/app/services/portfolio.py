from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import CashDeposit, FxRate, Instrument, Price, Transaction

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def xirr(cash_flows: list[tuple[date, Decimal]]) -> Decimal | None:
    if not cash_flows:
        return None
    if not any(amount < 0 for _, amount in cash_flows) or not any(amount > 0 for _, amount in cash_flows):
        return None

    start = cash_flows[0][0]

    def npv(rate: float) -> float:
        return sum(float(amount) / (1 + rate) ** ((on_date - start).days / 365) for on_date, amount in cash_flows)

    lower = -0.9999
    lower_value = npv(lower)
    upper = 1.0
    upper_value = npv(upper)
    for _ in range(32):
        if lower_value * upper_value <= 0:
            break
        upper *= 2
        upper_value = npv(upper)
    else:
        return None

    for _ in range(100):
        middle = (lower + upper) / 2
        middle_value = npv(middle)
        if abs(middle_value) < 1e-8:
            return Decimal(str(middle))
        if lower_value * middle_value <= 0:
            upper, upper_value = middle, middle_value
        else:
            lower, lower_value = middle, middle_value
    return Decimal(str((lower + upper) / 2))


def _as_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def fx_on(
    db: Session, currency: str, on_date: date, cache: dict | None = None
) -> Decimal | None:
    currency = currency.upper()
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
    result = _as_decimal(rate) if rate is not None else None
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
    has_missing_fx = False
    for tx in txs:
        signed = _signed_qty(tx)
        qty += signed
        if tx.type == "BUY":
            fx = fx_on(db, tx.currency, tx.date, fx_cache)
            if fx is None:
                has_missing_fx = True
                continue
            buy_qty += _as_decimal(tx.quantity)
            if tx.purchase_price_pln is not None:
                buy_cost_pln += _as_decimal(tx.purchase_price_pln) + _as_decimal(tx.commission) * fx
            else:
                buy_cost_pln += (_as_decimal(tx.quantity) * _as_decimal(tx.price) + _as_decimal(tx.commission)) * fx
    if has_missing_fx:
        avg_cost = cost_pln = None
    else:
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
        if fx is None:
            continue
        total += qty * _as_decimal(px.close) * fx
    return total


def build_summary(db: Session, portfolio_id: int | None = None) -> dict:
    transaction_query = select(Transaction).options(selectinload(Transaction.instrument))
    deposit_query = select(CashDeposit)
    if portfolio_id is not None:
        transaction_query = transaction_query.where(Transaction.portfolio_id == portfolio_id)
        deposit_query = deposit_query.where(CashDeposit.portfolio_id == portfolio_id)
    transactions = list(
        db.scalars(
            transaction_query.order_by(Transaction.date)
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
    has_missing_prices = False
    has_missing_previous_fx = False
    has_missing_costs = False
    has_missing_cash_flow_fx = False
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
        market = qty * price * fx if price is not None and fx is not None else None
        prev_price = _as_decimal(prev_px.close) if prev_px else price
        prev_fx = fx_on(db, prev_px.currency if prev_px else currency, today - timedelta(days=1), fx_cache)
        prev_value = (
            qty * (prev_price or ZERO) * prev_fx
            if prev_price is not None and prev_fx is not None
            else None
        )
        change_1d = (
            market - prev_value
            if market is not None and prev_value is not None
            else None
        )
        change_1d_pct = (
            change_1d / prev_value * HUNDRED
            if change_1d is not None and prev_value
            else None
        )
        pnl = (
            market - cost_pln
            if market is not None and cost_pln is not None
            else None
        )
        pnl_pct = (
            pnl / cost_pln * HUNDRED
            if pnl is not None and cost_pln
            else None
        )
        if market is None:
            has_missing_prices = True
        else:
            total_value += market
        if prev_value is not None:
            total_prev += prev_value
        elif prev_price is not None:
            has_missing_previous_fx = True
        if cost_pln is None:
            has_missing_costs = True
        else:
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
        pos["weight_pct"] = (
            (pos["market_value_pln"] / total_value * HUNDRED)
            if not has_missing_prices and total_value and pos["market_value_pln"] is not None
            else None
        )

    positions.sort(key=lambda p: p["market_value_pln"] or ZERO, reverse=True)
    value = None if has_missing_prices else total_value
    value_prev = (
        None if has_missing_prices or has_missing_previous_fx else total_prev
    )
    change_1d = value - value_prev if value is not None and value_prev is not None else None
    deposits = list(db.scalars(deposit_query.order_by(CashDeposit.date, CashDeposit.id)).all())
    cash_flows = []
    deposit_portfolio_ids = {deposit.portfolio_id for deposit in deposits}
    for deposit in deposits:
        fx = fx_on(db, deposit.currency, deposit.date, fx_cache)
        if fx is None:
            has_missing_cash_flow_fx = True
        else:
            cash_flows.append((deposit.date, -_as_decimal(deposit.amount) * fx))
    for tx in transactions:
        if tx.portfolio_id in deposit_portfolio_ids:
            continue
        fx = fx_on(db, tx.currency, tx.date, fx_cache)
        if fx is None:
            has_missing_cash_flow_fx = True
            continue
        gross = (
            _as_decimal(tx.purchase_price_pln)
            if tx.purchase_price_pln is not None
            else _as_decimal(tx.quantity) * _as_decimal(tx.price) * fx
        )
        commission = _as_decimal(tx.commission) * fx
        cash_flows.append((tx.date, -(gross + commission) if tx.type == "BUY" else gross - commission))
    if value:
        cash_flows.append((as_of or today, value))
    annual_return = (
        xirr(cash_flows)
        if not has_missing_prices and not has_missing_cash_flow_fx
        else None
    )
    return {
        "value_pln": value,
        "value_prev_pln": value_prev,
        "change_1d_pln": change_1d,
        "change_1d_pct": (change_1d / value_prev * HUNDRED) if change_1d is not None and value_prev else None,
        "cost_pln": None if has_missing_costs else total_cost,
        "pnl_pln": (
            value - total_cost
            if value is not None and not has_missing_costs
            else None
        ),
        "pnl_pct": (
            (value - total_cost) / total_cost * HUNDRED
            if value is not None and not has_missing_costs and total_cost
            else None
        ),
        "xirr_pct": annual_return * HUNDRED if annual_return is not None else None,
        "as_of": as_of,
        "positions": positions,
    }


def build_history(db: Session, portfolio_id: int | None = None) -> list[dict]:
    transaction_query = select(Transaction)
    if portfolio_id is not None:
        transaction_query = transaction_query.where(Transaction.portfolio_id == portfolio_id)
    transactions = list(db.scalars(transaction_query.order_by(Transaction.date)).all())
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
