from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AssetCashFlow,
    CashDeposit,
    CashMovement,
    FxRate,
    Instrument,
    Price,
    PropertyDetails,
    Transaction,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def xirr(cash_flows: list[tuple[date, Decimal]]) -> Decimal | None:
    if not cash_flows:
        return None
    if not any(amount < 0 for _, amount in cash_flows) or not any(amount > 0 for _, amount in cash_flows):
        return None

    start = min(on_date for on_date, _amount in cash_flows)
    if all(on_date == start for on_date, _amount in cash_flows):
        return None

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
    # Each portfolio owns its cost pool. Sales remove cost at the moving average;
    # a fully closed pool must not affect a later purchase or another portfolio.
    pools = {}
    txs = [tx for tx in txs if tx.date <= on_date]
    if txs and txs[0].instrument.type == "real_estate":
        capex_query = select(AssetCashFlow).where(
            AssetCashFlow.instrument_id == txs[0].instrument_id,
            AssetCashFlow.kind == "CAPEX",
            AssetCashFlow.date <= on_date,
            AssetCashFlow.portfolio_id.in_({tx.portfolio_id for tx in txs})
        )
        capex_rows = db.scalars(capex_query).all()
    else:
        capex_rows = []
    events = [(tx.date, 0, tx.id or 0, tx) for tx in txs]
    events.extend((flow.date, 1, flow.id or 0, flow) for flow in capex_rows)
    for _day, kind, _id, row in sorted(events, key=lambda event: event[:3]):
        pool = pools.setdefault(row.portfolio_id, {"qty": ZERO, "cost": ZERO, "missing": False})
        if kind == 1:
            if pool["qty"] > 0:
                amount = _cash_flow_amount_pln(db, row, fx_cache)
                if amount is None:
                    pool["missing"] = True
                else:
                    pool["cost"] += amount
        elif row.type == "BUY":
            pool["qty"] += _as_decimal(row.quantity)
            amount = _transaction_cash_flow(db, row, fx_cache)
            if amount is None:
                pool["missing"] = True
            else:
                pool["cost"] -= amount
        else:
            sold = _as_decimal(row.quantity)
            if pool["qty"] > 0:
                pool["cost"] *= (pool["qty"] - sold) / pool["qty"]
            pool["qty"] -= sold
            if pool["qty"] == 0:
                pool["cost"] = ZERO
                pool["missing"] = False
            elif pool["qty"] < 0:
                pool["missing"] = True
    qty = sum((pool["qty"] for pool in pools.values()), ZERO)
    cost_pln = (
        None if any(pool["missing"] for pool in pools.values())
        else sum((pool["cost"] for pool in pools.values()), ZERO)
    )
    avg_cost = None if cost_pln is None else (cost_pln / qty if qty else ZERO)
    return qty, avg_cost, cost_pln


def _cash_flow_amount_pln(db: Session, cash_flow: AssetCashFlow, fx_cache=None) -> Decimal | None:
    fx = fx_on(db, cash_flow.currency, cash_flow.date, fx_cache)
    return _as_decimal(cash_flow.amount) * fx if fx is not None else None


def _signed_asset_cash_flow(cash_flow: AssetCashFlow, amount_pln: Decimal) -> Decimal:
    if cash_flow.kind in {"RENT", "OTHER_INCOME"}:
        return amount_pln - _as_decimal(cash_flow.tax_amount) * (
            amount_pln / _as_decimal(cash_flow.amount) if cash_flow.amount else ZERO
        )
    return -amount_pln


def _transaction_cash_flow(db: Session, tx: Transaction, fx_cache=None) -> Decimal | None:
    # An imported PLN account amount already includes the actual conversion.
    needs_fx = tx.purchase_price_pln is None or _as_decimal(tx.commission) != ZERO
    fx = fx_on(db, tx.currency, tx.date, fx_cache) if needs_fx else Decimal("1")
    if fx is None:
        return None
    gross = (
        _as_decimal(tx.purchase_price_pln)
        if tx.purchase_price_pln is not None
        else _as_decimal(tx.quantity) * _as_decimal(tx.price) * fx
    )
    commission = _as_decimal(tx.commission) * fx
    return -(gross + commission) if tx.type == "BUY" else gross - commission


def cash_value_on(db: Session, transactions, deposits, movements, on_date: date, fx_cache=None) -> Decimal | None:
    """Keep native-currency cash balances and value them at the terminal date."""
    funded_ids = {row.portfolio_id for row in deposits if row.date <= on_date}
    balances = {}

    def add(currency, amount):
        currency = currency.upper()
        balances[currency] = balances.get(currency, ZERO) + amount

    for deposit in deposits:
        if deposit.date <= on_date:
            add(deposit.currency, _as_decimal(deposit.amount))
    for tx in transactions:
        if tx.date > on_date or tx.portfolio_id not in funded_ids:
            continue
        sign = Decimal("-1") if tx.type == "BUY" else Decimal("1")
        if tx.purchase_price_pln is not None:
            add("PLN", sign * _as_decimal(tx.purchase_price_pln))
            add(tx.currency, -_as_decimal(tx.commission))
        else:
            add(tx.currency, sign * _as_decimal(tx.quantity) * _as_decimal(tx.price) - _as_decimal(tx.commission))
    for movement in movements:
        if movement.date <= on_date and movement.portfolio_id in funded_ids:
            add(movement.currency, _as_decimal(movement.amount))
    total = ZERO
    for currency, balance in balances.items():
        if not balance:
            continue
        fx = fx_on(db, currency, on_date, fx_cache)
        if fx is None:
            return None
        total += balance * fx
    return total


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
        qty = sum((_signed_qty(tx) for tx in txs), ZERO)
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
    today = date.today()
    transaction_query = (
        select(Transaction).where(Transaction.date <= today)
        .options(selectinload(Transaction.instrument))
    )
    deposit_query = select(CashDeposit).where(CashDeposit.date <= today)
    movement_query = select(CashMovement).where(CashMovement.date <= today)
    asset_cash_flow_query = (
        select(AssetCashFlow)
        .where(AssetCashFlow.date <= today)
        .order_by(AssetCashFlow.date, AssetCashFlow.id)
    )
    if portfolio_id is not None:
        transaction_query = transaction_query.where(Transaction.portfolio_id == portfolio_id)
        deposit_query = deposit_query.where(CashDeposit.portfolio_id == portfolio_id)
        movement_query = movement_query.where(CashMovement.portfolio_id == portfolio_id)
        asset_cash_flow_query = asset_cash_flow_query.where(AssetCashFlow.portfolio_id == portfolio_id)
    transactions = list(
        db.scalars(
            transaction_query.order_by(Transaction.date, Transaction.id)
        ).all()
    )
    instruments = {i.id: i for i in db.scalars(select(Instrument)).all()}
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
    asset_cash_flows = list(db.scalars(asset_cash_flow_query).all())
    cash_flows_by_instrument: dict[int, list[AssetCashFlow]] = {}
    for cash_flow in asset_cash_flows:
        cash_flows_by_instrument.setdefault(cash_flow.instrument_id, []).append(cash_flow)
    total_income = ZERO
    total_costs = ZERO
    total_capex = ZERO
    has_missing_asset_cash_flow_fx = False
    for cash_flow in asset_cash_flows:
        amount_pln = _cash_flow_amount_pln(db, cash_flow, fx_cache)
        if amount_pln is None:
            has_missing_asset_cash_flow_fx = True
            continue
        tax_pln = _as_decimal(cash_flow.tax_amount) * (
            amount_pln / _as_decimal(cash_flow.amount)
        ) if cash_flow.amount else ZERO
        if cash_flow.kind in {"RENT", "OTHER_INCOME"}:
            total_income += amount_pln - tax_pln
        elif cash_flow.kind in {"OPEX", "TAX"}:
            total_costs += amount_pln
        elif cash_flow.kind == "CAPEX":
            total_capex += amount_pln
    if has_missing_asset_cash_flow_fx:
        total_income = total_costs = total_capex = None

    for position in positions:
        instrument_id = position["instrument"].id
        instrument_flows = cash_flows_by_instrument.get(instrument_id, [])
        position_income = ZERO
        position_costs = ZERO
        position_capex = ZERO
        missing_position_flow_fx = False
        for cash_flow in instrument_flows:
            amount_pln = _cash_flow_amount_pln(db, cash_flow, fx_cache)
            if amount_pln is None:
                missing_position_flow_fx = True
                continue
            tax_pln = _as_decimal(cash_flow.tax_amount) * (
                amount_pln / _as_decimal(cash_flow.amount)
            ) if cash_flow.amount else ZERO
            if cash_flow.kind in {"RENT", "OTHER_INCOME"}:
                position_income += amount_pln - tax_pln
            elif cash_flow.kind in {"OPEX", "TAX"}:
                position_costs += amount_pln
            elif cash_flow.kind == "CAPEX":
                position_capex += amount_pln
        position["income_pln"] = None if missing_position_flow_fx else position_income
        position["costs_pln"] = None if missing_position_flow_fx else position_costs
        position["capex_pln"] = None if missing_position_flow_fx else position_capex
        position["total_return_pln"] = (
            position["pnl_pln"] + position_income - position_costs
            if position["pnl_pln"] is not None and not missing_position_flow_fx
            else None
        )
        position["valuation_date"] = position["price_date"]
        instrument = position["instrument"]
        if instrument.type == "real_estate" or instrument_flows:
            position_xirr_flows: list[tuple[date, Decimal]] = []
            missing_position_xirr_fx = False
            for tx in grouped[instrument_id]:
                tx_flow = _transaction_cash_flow(db, tx, fx_cache)
                if tx_flow is None:
                    missing_position_xirr_fx = True
                else:
                    position_xirr_flows.append((tx.date, tx_flow))
            for cash_flow in instrument_flows:
                amount_pln = _cash_flow_amount_pln(db, cash_flow, fx_cache)
                if amount_pln is None:
                    missing_position_xirr_fx = True
                else:
                    position_xirr_flows.append((cash_flow.date, _signed_asset_cash_flow(cash_flow, amount_pln)))
            market = position["market_value_pln"]
            if market is not None:
                position_xirr_flows.append((today, market))
            result = (
                xirr(sorted(position_xirr_flows, key=lambda item: item[0]))
                if not missing_position_xirr_fx and market is not None
                else None
            )
            position["xirr_pct"] = result * HUNDRED if result is not None else None
        else:
            position["xirr_pct"] = None

    cash_flows = []
    movements = list(db.scalars(movement_query).all())
    cash_value = cash_value_on(db, transactions, deposits, movements, today, fx_cache)
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
        amount = _transaction_cash_flow(db, tx, fx_cache)
        if amount is None:
            has_missing_cash_flow_fx = True
            continue
        cash_flows.append((tx.date, amount))
    for movement in movements:
        if movement.portfolio_id in deposit_portfolio_ids:
            continue
        fx = fx_on(db, movement.currency, movement.date, fx_cache)
        if fx is None:
            has_missing_cash_flow_fx = True
        else:
            cash_flows.append((movement.date, _as_decimal(movement.amount) * fx))
    for cash_flow in asset_cash_flows:
        amount_pln = _cash_flow_amount_pln(db, cash_flow, fx_cache)
        if amount_pln is None:
            has_missing_cash_flow_fx = True
        else:
            cash_flows.append((cash_flow.date, _signed_asset_cash_flow(cash_flow, amount_pln)))
    terminal_value = value + cash_value if value is not None and cash_value is not None else None
    if terminal_value is not None:
        cash_flows.append((today, terminal_value))
    annual_return = (
        xirr(cash_flows)
        if not has_missing_prices and not has_missing_cash_flow_fx and terminal_value is not None
        else None
    )
    return {
        "value_pln": value,
        "cash_pln": cash_value,
        "total_value_pln": terminal_value,
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
        "income_pln": total_income,
        "costs_pln": total_costs,
        "total_return_pln": (
            (value - total_cost + total_income - total_costs)
            if value is not None and not has_missing_costs and total_income is not None and total_costs is not None
            else None
        ),
        "as_of": as_of,
        "positions": positions,
    }


def build_property_metrics(
    db: Session,
    instrument_id: int,
    portfolio_id: int | None,
    date_from: date,
    date_to: date,
) -> dict:
    instrument = db.get(Instrument, instrument_id)
    details = db.get(PropertyDetails, instrument_id)
    if instrument is None or details is None or date_from > date_to:
        return {
            "purchase_cost_pln": None,
            "capex_pln": None,
            "cost_basis_pln": None,
            "valuation_pln": None,
            "valuation_date": None,
            "price_per_m2": None,
            "rent_gross_pln": None,
            "other_income_pln": None,
            "tax_pln": None,
            "opex_pln": None,
            "capex_in_period_pln": None,
            "net_cash_flow_pln": None,
            "gross_yield_pct": None,
            "net_yield_pct": None,
            "value_change_pln": None,
            "total_return_pln": None,
            "xirr_pct": None,
            "cash_flows_by_category": [],
        }

    fx_cache: dict = {}
    transaction_query = select(Transaction).where(Transaction.instrument_id == instrument_id)
    cash_flow_query = select(AssetCashFlow).where(AssetCashFlow.instrument_id == instrument_id)
    if portfolio_id is not None:
        transaction_query = transaction_query.where(Transaction.portfolio_id == portfolio_id)
        cash_flow_query = cash_flow_query.where(AssetCashFlow.portfolio_id == portfolio_id)
    transactions = list(db.scalars(transaction_query.order_by(Transaction.date, Transaction.id)).all())
    all_cash_flows = list(db.scalars(cash_flow_query.order_by(AssetCashFlow.date, AssetCashFlow.id)).all())
    current_flows = [flow for flow in all_cash_flows if flow.date <= date_to]
    period_flows = [flow for flow in current_flows if date_from <= flow.date <= date_to]

    purchase_cost = ZERO
    has_purchase = False
    missing_purchase_fx = False
    period_purchase_cost = ZERO
    bought_in_period = False
    for tx in transactions:
        if tx.type != "BUY" or tx.date > date_to:
            continue
        fx = fx_on(db, tx.currency, tx.date, fx_cache)
        if fx is None:
            missing_purchase_fx = True
            continue
        gross = (
            _as_decimal(tx.purchase_price_pln)
            if tx.purchase_price_pln is not None
            else _as_decimal(tx.quantity) * _as_decimal(tx.price) * fx
        )
        total = gross + _as_decimal(tx.commission) * fx
        purchase_cost += total
        has_purchase = True
        if date_from <= tx.date <= date_to:
            period_purchase_cost += total
            bought_in_period = True
    purchase_cost_result = None if missing_purchase_fx or not has_purchase else purchase_cost

    capex_total = ZERO
    has_capex = False
    missing_capex_fx = False
    for flow in current_flows:
        if flow.kind != "CAPEX":
            continue
        amount_pln = _cash_flow_amount_pln(db, flow, fx_cache)
        if amount_pln is None:
            missing_capex_fx = True
        else:
            capex_total += amount_pln
            has_capex = True
    capex_result = None if missing_capex_fx or not has_capex else capex_total
    cost_basis = (
        purchase_cost + capex_total
        if not missing_purchase_fx and not missing_capex_fx and has_purchase
        else None
    )

    valuation = price_on(db, instrument_id, date_to)
    valuation_fx = fx_on(db, valuation.currency, date_to, fx_cache) if valuation else None
    valuation_pln = _as_decimal(valuation.close) * valuation_fx if valuation and valuation_fx is not None else None
    price_per_m2 = (
        valuation_pln / _as_decimal(details.area_m2)
        if valuation_pln is not None and details.area_m2
        else None
    )

    totals = {"RENT": ZERO, "OTHER_INCOME": ZERO, "OPEX": ZERO, "CAPEX": ZERO, "TAX": ZERO}
    kinds_seen: set[str] = set()
    tax_total = ZERO
    net_cash_flow = ZERO
    missing_period_fx = False
    category_totals: dict[tuple[str, str | None], Decimal] = {}
    for flow in period_flows:
        amount_pln = _cash_flow_amount_pln(db, flow, fx_cache)
        if amount_pln is None:
            missing_period_fx = True
            continue
        kinds_seen.add(flow.kind)
        totals[flow.kind] = totals.get(flow.kind, ZERO) + amount_pln
        tax_pln = _as_decimal(flow.tax_amount) * (
            amount_pln / _as_decimal(flow.amount)
        ) if flow.amount else ZERO
        if flow.kind in {"RENT", "OTHER_INCOME"}:
            tax_total += tax_pln
            net_cash_flow += amount_pln - tax_pln
        else:
            net_cash_flow -= amount_pln
            if flow.kind == "TAX":
                tax_total += amount_pln
        category_key = (flow.kind, flow.category)
        category_totals[category_key] = category_totals.get(category_key, ZERO) + amount_pln
    if missing_period_fx:
        rent_gross = other_income = tax_period = opex = capex_period = net_cash_flow_result = None
    else:
        rent_gross = totals["RENT"] if "RENT" in kinds_seen else None
        other_income = totals["OTHER_INCOME"] if "OTHER_INCOME" in kinds_seen else None
        tax_period = tax_total if period_flows else None
        opex = totals["OPEX"] if "OPEX" in kinds_seen else None
        capex_period = totals["CAPEX"] if "CAPEX" in kinds_seen else None
        net_cash_flow_result = net_cash_flow if period_flows else None

    period_days = (date_to - date_from).days + 1
    gross_yield = (
        rent_gross * Decimal("365") / Decimal(period_days) / cost_basis * HUNDRED
        if rent_gross is not None and cost_basis
        else None
    )
    net_yield_base = (
        rent_gross - (tax_period or ZERO) - (opex or ZERO)
        if rent_gross is not None and tax_period is not None
        else None
    )
    net_yield = (
        net_yield_base * Decimal("365") / Decimal(period_days) / cost_basis * HUNDRED
        if net_yield_base is not None and cost_basis
        else None
    )

    start_valuation = price_on(db, instrument_id, date_from)
    start_valuation_pln = None
    if start_valuation is not None:
        start_fx = fx_on(db, start_valuation.currency, date_from, fx_cache)
        if start_fx is not None:
            start_valuation_pln = _as_decimal(start_valuation.close) * start_fx
    value_change_base = period_purchase_cost if bought_in_period else start_valuation_pln
    value_change = valuation_pln - value_change_base if valuation_pln is not None and value_change_base is not None else None
    total_return = (
        value_change + net_cash_flow_result
        if value_change is not None and net_cash_flow_result is not None
        else None
    )

    xirr_flows: list[tuple[date, Decimal]] = []
    missing_xirr_fx = False
    for tx in transactions:
        if tx.date > date.today():
            continue
        tx_flow = _transaction_cash_flow(db, tx, fx_cache)
        if tx_flow is None:
            missing_xirr_fx = True
        else:
            xirr_flows.append((tx.date, tx_flow))
    for flow in all_cash_flows:
        if flow.date > date.today():
            continue
        amount_pln = _cash_flow_amount_pln(db, flow, fx_cache)
        if amount_pln is None:
            missing_xirr_fx = True
        else:
            xirr_flows.append((flow.date, _signed_asset_cash_flow(flow, amount_pln)))
    today = date.today()
    latest_valuation = price_on(db, instrument_id, today)
    if latest_valuation is not None:
        latest_fx = fx_on(db, latest_valuation.currency, today, fx_cache)
        if latest_fx is None:
            missing_xirr_fx = True
        else:
            xirr_flows.append((today, _as_decimal(latest_valuation.close) * latest_fx))
    xirr_value = (
        xirr(sorted(xirr_flows, key=lambda item: item[0]))
        if not missing_xirr_fx and latest_valuation is not None
        else None
    )
    category_rows = [
        {"kind": kind, "category": category, "amount_pln": amount}
        for (kind, category), amount in sorted(category_totals.items(), key=lambda item: (item[0][0], item[0][1] or ""))
    ]
    return {
        "purchase_cost_pln": purchase_cost_result,
        "capex_pln": capex_result,
        "cost_basis_pln": cost_basis,
        "valuation_pln": valuation_pln,
        "valuation_date": valuation.date if valuation else None,
        "price_per_m2": price_per_m2,
        "rent_gross_pln": None if missing_period_fx else rent_gross,
        "other_income_pln": None if missing_period_fx else other_income,
        "tax_pln": None if missing_period_fx else tax_period,
        "opex_pln": None if missing_period_fx else opex,
        "capex_in_period_pln": None if missing_period_fx else capex_period,
        "net_cash_flow_pln": net_cash_flow_result,
        "gross_yield_pct": gross_yield,
        "net_yield_pct": net_yield,
        "value_change_pln": value_change,
        "total_return_pln": total_return,
        "xirr_pct": xirr_value * HUNDRED if xirr_value is not None else None,
        "cash_flows_by_category": category_rows,
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
    # Load valuations once, including those before the first transaction so
    # that stale prices and exchange rates still carry forward correctly.
    instrument_ids = {tx.instrument_id for tx in transactions}
    prices = list(db.execute(
        select(Price.instrument_id, Price.date, Price.close, Price.currency)
        .where(Price.instrument_id.in_(instrument_ids), Price.date <= end)
        .order_by(Price.date)
    ).all())
    pairs = {f"{row.currency.upper()}PLN" for row in prices if row.currency.upper() != "PLN"}
    rates = list(db.execute(
        select(FxRate.pair, FxRate.date, FxRate.rate)
        .where(FxRate.pair.in_(pairs), FxRate.date <= end)
        .order_by(FxRate.date)
    ).all())

    # Keep the existing chart dates (including dates from other portfolios),
    # but advance each transaction, price and FX row only once.
    transaction_iter = iter(transactions)
    price_iter = iter(prices)
    rate_iter = iter(rates)
    next_transaction = next(transaction_iter, None)
    next_price = next(price_iter, None)
    next_rate = next(rate_iter, None)
    quantities: dict[int, Decimal] = {}
    latest_prices: dict[int, tuple[Decimal, str]] = {}
    latest_rates: dict[str, Decimal] = {}
    series = []
    last_value = None
    for d in days:
        while next_transaction is not None and next_transaction.date <= d:
            instrument_id = next_transaction.instrument_id
            quantity = quantities.get(instrument_id, ZERO) + _signed_qty(next_transaction)
            if quantity:
                quantities[instrument_id] = quantity
            else:
                quantities.pop(instrument_id, None)
            next_transaction = next(transaction_iter, None)
        while next_price is not None and next_price.date <= d:
            latest_prices[next_price.instrument_id] = (
                _as_decimal(next_price.close), next_price.currency.upper()
            )
            next_price = next(price_iter, None)
        while next_rate is not None and next_rate.date <= d:
            latest_rates[next_rate.pair] = _as_decimal(next_rate.rate)
            next_rate = next(rate_iter, None)

        value = ZERO
        for instrument_id, quantity in quantities.items():
            price = latest_prices.get(instrument_id)
            if price is None:
                continue
            close, currency = price
            fx = Decimal("1") if currency == "PLN" else latest_rates.get(f"{currency}PLN")
            if fx is not None:
                value += quantity * close * fx
        if value == 0 and last_value is None:
            continue
        last_value = value
        series.append({"date": d, "value_pln": value})
    return series
