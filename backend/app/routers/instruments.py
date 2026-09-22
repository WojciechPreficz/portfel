from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Instrument, Price
from app.schemas import InstrumentCreate, InstrumentOut, PricePoint
from app.seed import apply_instrument_defaults

router = APIRouter(prefix="/api/instruments", tags=["instruments"])


@router.get("", response_model=list[InstrumentOut])
def list_instruments(
    q: str | None = Query(default=None),
    type: str | None = Query(default=None, alias="type"),
    db: Session = Depends(get_db),
):
    stmt = select(Instrument).order_by(Instrument.ticker)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Instrument.ticker.ilike(like),
                Instrument.name.ilike(like),
                Instrument.isin.ilike(like),
                Instrument.symbol.ilike(like),
            )
        )
    if type:
        stmt = stmt.where(Instrument.type == type)
    return db.scalars(stmt).all()


@router.get("/{instrument_id}", response_model=InstrumentOut)
def get_instrument(instrument_id: int, db: Session = Depends(get_db)):
    instrument = db.get(Instrument, instrument_id)
    if not instrument:
        raise HTTPException(404, "Instrument nie istnieje")
    return instrument


@router.get("/{instrument_id}/prices", response_model=list[PricePoint])
def instrument_prices(instrument_id: int, db: Session = Depends(get_db)):
    if not db.get(Instrument, instrument_id):
        raise HTTPException(404, "Instrument nie istnieje")
    rows = db.scalars(
        select(Price).where(Price.instrument_id == instrument_id).order_by(Price.date)
    ).all()
    return rows


@router.post("", response_model=InstrumentOut)
def create_instrument(payload: InstrumentCreate, db: Session = Depends(get_db)):
    raw = payload.model_dump(exclude_none=True)
    try:
        data = apply_instrument_defaults(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    existing = db.scalar(
        select(Instrument).where(
            Instrument.ticker == data["ticker"],
            Instrument.provider == data["provider"],
            Instrument.symbol == data["symbol"],
        )
    )
    if existing:
        return existing
    instrument = Instrument(**data)
    db.add(instrument)
    db.commit()
    db.refresh(instrument)
    return instrument
