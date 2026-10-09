from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CashDeposit, CashMovement, FxRate, Instrument, Price, Transaction
from app.services.adapters import get_adapter
from app.services.adapters.base import QuotePoint
from app.services.adapters.nbp import fetch_fx_history
from app.services.adapters.yahoo import YahooAdapter
from app.seed import GOLD_PURITIES

TROY_OUNCE_GRAMS = Decimal("31.1034768")
INCREMENTAL_BUFFER_DAYS = 5
MAX_CONCURRENT_STOOQ_REQUESTS = 8
UNQUOTED_INSTRUMENT_TICKERS = {"ZWC"}


def _upsert_price(db: Session, instrument_id: int, d: date, close: Decimal, currency: str) -> bool:
    if close <= 0:
        raise ValueError(f"Nieprawidłowa cena zamknięcia: {close}")
    existing = db.scalar(
        select(Price).where(Price.instrument_id == instrument_id, Price.date == d)
    )
    if existing:
        existing.close = close
        existing.currency = currency
        return False
    db.add(Price(instrument_id=instrument_id, date=d, close=close, currency=currency))
    return True


def _upsert_fx(db: Session, pair: str, d: date, rate: Decimal) -> bool:
    existing = db.scalar(select(FxRate).where(FxRate.pair == pair, FxRate.date == d))
    if existing:
        existing.rate = rate
        return False
    db.add(FxRate(pair=pair, date=d, rate=rate))
    return True


def _fetch_history(instrument, start: date, end: date):
    adapter = get_adapter(instrument.provider)
    try:
        points = adapter.fetch_history(instrument.symbol, start, end, instrument.currency)
    except Exception:
        if not _can_fallback_to_yahoo(instrument):
            raise
        fallback_symbol = _polish_yahoo_symbol(instrument)
        points = YahooAdapter().fetch_history(
            fallback_symbol, start, end, instrument.currency
        )
        return _convert_gold_history(instrument, points)

    if _can_fallback_to_yahoo(instrument) and not points:
        fallback_symbol = _polish_yahoo_symbol(instrument)
        points = YahooAdapter().fetch_history(
            fallback_symbol, start, end, instrument.currency
        )
    return _convert_gold_history(instrument, points)


def _can_fallback_to_yahoo(instrument) -> bool:
    return (
        instrument.provider == "stooq"
        and instrument.type in {"stock_pl", "etf"}
        and instrument.currency.upper() == "PLN"
    )


def _polish_yahoo_symbol(instrument) -> str:
    ticker = instrument.ticker.upper()
    return ticker if ticker.endswith(".WA") else f"{ticker}.WA"


def _convert_gold_history(instrument, points: list[QuotePoint]) -> list[QuotePoint]:
    if instrument.type == "gold":
        purity_code = instrument.ticker.rsplit("-", 1)[-1]
        if purity_code not in GOLD_PURITIES:
            raise ValueError(f"Nieobsługiwana próba złota: {instrument.ticker}")
        purity = Decimal(purity_code) / Decimal("10000")
        return [
            QuotePoint(
                date=point.date,
                close=point.close * purity / TROY_OUNCE_GRAMS,
                currency=point.currency,
            )
            for point in points
        ]
    return points


def _instrument_start(db: Session, instrument: Instrument, end: date, years: int) -> date:
    latest_price = db.scalar(
        select(func.max(Price.date)).where(Price.instrument_id == instrument.id)
    )
    if latest_price is not None:
        return max(date(1990, 1, 1), latest_price - timedelta(days=INCREMENTAL_BUFFER_DAYS))
    first_transaction = db.scalar(
        select(func.min(Transaction.date)).where(Transaction.instrument_id == instrument.id)
    )
    return first_transaction or end - timedelta(days=365 * years)


def _fx_start(db: Session, pair: str, currency: str, fallback: date) -> date:
    latest_rate = db.scalar(select(func.max(FxRate.date)).where(FxRate.pair == pair))
    if latest_rate is not None:
        return max(date(1990, 1, 1), latest_rate - timedelta(days=INCREMENTAL_BUFFER_DAYS))

    transaction_date = db.scalar(
        select(func.min(Transaction.date))
        .where(Transaction.currency == currency)
    )
    instrument_transaction_date = db.scalar(
        select(func.min(Transaction.date))
        .join(Instrument, Instrument.id == Transaction.instrument_id)
        .where(Instrument.currency == currency)
    )
    deposit_date = db.scalar(
        select(func.min(CashDeposit.date))
        .where(CashDeposit.currency == currency)
    )
    movement_date = db.scalar(
        select(func.min(CashMovement.date)).where(CashMovement.currency == currency)
    )
    dates = [
        value
        for value in (transaction_date, instrument_transaction_date, deposit_date, movement_date)
        if value is not None
    ]
    return min(dates) if dates else fallback


def refresh_quotes(
    db: Session,
    instrument_ids: list[int] | None = None,
    years: int = 5,
) -> dict:
    errors: list[str] = []
    prices_upserted = 0
    fx_upserted = 0
    end = date.today()
    fallback_start = end - timedelta(days=365 * years)
    if instrument_ids is None:
        instruments_query = select(Instrument).join(Transaction).distinct()
    elif instrument_ids:
        instruments_query = select(Instrument).where(Instrument.id.in_(instrument_ids))
    else:
        instruments_query = select(Instrument).where(Instrument.id == -1)
    instruments = [
        instrument
        for instrument in db.scalars(instruments_query).all()
        if not (instrument.type == "real_estate" and instrument.provider == "manual")
        and instrument.ticker.upper() not in UNQUOTED_INSTRUMENT_TICKERS
    ]
    starts = {
        instrument.id: _instrument_start(db, instrument, end, years)
        for instrument in instruments
    }
    yahoo_jobs: dict[int, tuple[str, date]] = {}
    quote_points: dict[int, list[QuotePoint]] = {}
    stooq_jobs: list[Instrument] = []
    for instrument in instruments:
        start = starts[instrument.id]
        if instrument.provider == "yahoo":
            yahoo_jobs[instrument.id] = (instrument.symbol, start)
            continue
        if instrument.provider != "stooq":
            try:
                quote_points[instrument.id] = _fetch_history(instrument, start, end)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{instrument.ticker}: {exc}")
            continue

        stooq_jobs.append(instrument)

    if stooq_jobs:
        stooq = get_adapter("stooq")
        worker_count = min(MAX_CONCURRENT_STOOQ_REQUESTS, len(stooq_jobs))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(
                    stooq.fetch_history,
                    instrument.symbol,
                    starts[instrument.id],
                    end,
                    instrument.currency,
                )
                for instrument in stooq_jobs
            ]
            for instrument, future in zip(stooq_jobs, futures):
                try:
                    points = future.result()
                except Exception as exc:  # noqa: BLE001
                    if not _can_fallback_to_yahoo(instrument):
                        errors.append(f"{instrument.ticker}: {exc}")
                        continue
                    points = []
                if points:
                    quote_points[instrument.id] = points
                elif _can_fallback_to_yahoo(instrument):
                    yahoo_jobs[instrument.id] = (
                        _polish_yahoo_symbol(instrument),
                        starts[instrument.id],
                    )
                else:
                    quote_points[instrument.id] = []

    yahoo_groups: dict[date, list[Instrument]] = {}
    instruments_by_id = {instrument.id: instrument for instrument in instruments}
    for instrument_id in yahoo_jobs:
        yahoo_groups.setdefault(yahoo_jobs[instrument_id][1], []).append(
            instruments_by_id[instrument_id]
        )
    yahoo = YahooAdapter()
    for start, group in yahoo_groups.items():
        requested_symbols: dict[str, tuple[date, date, str]] = {}
        for instrument in group:
            symbol = yahoo_jobs[instrument.id][0]
            requested_symbols.setdefault(
                symbol, (start, end, instrument.currency)
            )
        try:
            fetched = yahoo.fetch_many(requested_symbols)
            for instrument in group:
                symbol = yahoo_jobs[instrument.id][0]
                quote_points[instrument.id] = fetched.get(symbol, [])
        except Exception as exc:  # noqa: BLE001
            for instrument in group:
                errors.append(f"{instrument.ticker}: {exc}")

    for instrument in instruments:
        if instrument.id not in quote_points:
            continue
        points = _convert_gold_history(instrument, quote_points[instrument.id])
        valid_points = [point for point in points if point.close > 0]
        if len(valid_points) != len(points):
            errors.append(f"{instrument.ticker}: odrzucono niedodatnie ceny")
        if not valid_points:
            errors.append(
                f"{instrument.ticker}: brak prawidłowych notowań w Stooq i Yahoo Finance"
            )
            continue
        for point in valid_points:
            instrument.currency = point.currency
            if _upsert_price(db, instrument.id, point.date, point.close, point.currency):
                prices_upserted += 1

    db.flush()
    currencies = {instrument.currency.upper() for instrument in instruments}
    currencies.update(
        currency.upper()
        for currency in db.scalars(
            select(Instrument.currency).join(Transaction).distinct()
        ).all()
    )
    currencies.update(
        currency.upper()
        for currency in db.scalars(select(Transaction.currency).distinct()).all()
    )
    currencies.update(
        currency.upper()
        for currency in db.scalars(select(CashDeposit.currency).distinct()).all()
    )
    currencies.update(
        currency.upper()
        for currency in db.scalars(select(CashMovement.currency).distinct()).all()
    )
    for currency in sorted(currencies - {"PLN"}):
        pair = f"{currency}PLN"
        try:
            start = _fx_start(db, pair, currency, fallback_start)
            for d, rate in fetch_fx_history(currency.lower(), start, end):
                if _upsert_fx(db, pair, d, rate):
                    fx_upserted += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"FX {pair}: {exc}")

    db.commit()
    return {
        "instruments": len(instruments),
        "prices_upserted": prices_upserted,
        "fx_upserted": fx_upserted,
        "errors": errors,
    }
