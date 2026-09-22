from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FxRate, Instrument, Price, Transaction
from app.services.adapters import get_adapter
from app.services.adapters.nbp import fetch_fx_history
from app.services.adapters.yahoo import YahooAdapter


def _upsert_price(db: Session, instrument_id: int, d: date, close: Decimal, currency: str) -> bool:
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
        return adapter.fetch_history(instrument.symbol, start, end, instrument.currency)
    except Exception:
        if instrument.provider != "stooq" or instrument.currency != "PLN":
            raise
        fallback_symbol = f"{instrument.symbol.upper()}.WA"
        return YahooAdapter().fetch_history(fallback_symbol, start, end, instrument.currency)


def refresh_quotes(db: Session, years: int = 5) -> dict:
    errors: list[str] = []
    prices_upserted = 0
    fx_upserted = 0
    end = date.today()
    start = end - timedelta(days=365 * years)

    instruments = list(
        db.scalars(
            select(Instrument)
            .join(Transaction)
            .distinct()
        ).all()
    )
    currencies = {instrument.currency.upper() for instrument in instruments}
    fx_pairs = [("usd", "USDPLN")] if "USD" in currencies else []
    if "EUR" in currencies:
        fx_pairs.append(("eur", "EURPLN"))

    for code, pair in fx_pairs:
        try:
            for d, rate in fetch_fx_history(code, start, end):
                if _upsert_fx(db, pair, d, rate):
                    fx_upserted += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"FX {pair}: {exc}")

    first_tx = db.scalar(select(Transaction.date).order_by(Transaction.date.asc()).limit(1))
    hist_start = first_tx or start

    for instrument in instruments:
        try:
            points = _fetch_history(instrument, hist_start, end)
            for point in points:
                if _upsert_price(db, instrument.id, point.date, point.close, point.currency):
                    prices_upserted += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{instrument.ticker}: {exc}")

    db.commit()
    return {
        "instruments": len(instruments),
        "prices_upserted": prices_upserted,
        "fx_upserted": fx_upserted,
        "errors": errors,
    }
