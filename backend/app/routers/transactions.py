from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Instrument, Transaction
from app.schemas import TransactionCreate, TransactionOut
from app.seed import apply_instrument_defaults
from app.services.portfolio import _signed_qty

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _get_or_create_instrument(db: Session, payload: TransactionCreate) -> Instrument:
    if payload.instrument_id:
        instrument = db.get(Instrument, payload.instrument_id)
        if not instrument:
            raise HTTPException(400, "Nieznany instrument")
        return instrument
    if not payload.instrument:
        raise HTTPException(400, "Podaj instrument_id albo dane instrumentu")
    data = apply_instrument_defaults(payload.instrument.model_dump(exclude_none=True))
    existing = db.scalar(
        select(Instrument).where(
            Instrument.ticker == data["ticker"],
            Instrument.symbol == data["symbol"],
        )
    )
    if existing:
        return existing
    instrument = Instrument(**data)
    db.add(instrument)
    db.flush()
    return instrument


@router.get("", response_model=list[TransactionOut])
def list_transactions(db: Session = Depends(get_db)):
    return db.scalars(
        select(Transaction).options(selectinload(Transaction.instrument)).order_by(Transaction.date.desc(), Transaction.id.desc())
    ).all()


@router.post("", response_model=TransactionOut)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    if payload.type not in {"BUY", "SELL"}:
        raise HTTPException(400, "Typ musi być BUY lub SELL")
    instrument = _get_or_create_instrument(db, payload)
    if payload.type == "SELL":
        existing = db.scalars(select(Transaction).where(Transaction.instrument_id == instrument.id)).all()
        qty = sum((_signed_qty(tx) for tx in existing), Decimal("0"))
        if payload.quantity > qty:
            raise HTTPException(400, "Sprzedaż większa niż posiadana ilość")
    tx = Transaction(
        instrument_id=instrument.id,
        type=payload.type,
        quantity=payload.quantity,
        price=payload.price,
        currency=payload.currency or instrument.currency,
        date=payload.date,
        commission=payload.commission,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    tx = db.scalar(
        select(Transaction).options(selectinload(Transaction.instrument)).where(Transaction.id == tx.id)
    )
    return tx


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    tx = db.get(Transaction, transaction_id)
    if not tx:
        raise HTTPException(404, "Transakcja nie istnieje")
    db.delete(tx)
    db.commit()
    return {"ok": True}
