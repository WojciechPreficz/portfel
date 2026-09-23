from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Instrument, Transaction
from app.schemas import TransactionCreate, TransactionImportResult, TransactionOut
from app.seed import apply_instrument_defaults
from app.services.portfolio import _signed_qty
from app.services.transaction_import import read_purchases

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


@router.post("/import", response_model=TransactionImportResult)
def import_transactions(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Wybierz plik Excel w formacie .xlsx")
    try:
        purchases, errors = read_purchases(file.file.read())
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if errors:
        return TransactionImportResult(imported=0, skipped=len(errors), errors=errors)

    transactions = []
    for purchase in purchases:
        instrument = None
        if purchase["isin"]:
            instrument = db.scalar(select(Instrument).where(Instrument.isin == purchase["isin"]))
        if not instrument and purchase["ticker"]:
            instrument = db.scalar(select(Instrument).where(Instrument.ticker == purchase["ticker"]))
        if not instrument:
            raw_ticker = purchase.get("raw_ticker") or ""
            category = purchase.get("category")
            instrument_type = "etf" if category == "etf" else "stock_us" if raw_ticker.endswith(".US") else "stock_pl"
            if purchase["ticker"] and purchase.get("name"):
                data = apply_instrument_defaults({
                    "ticker": purchase["ticker"],
                    "name": purchase["name"],
                    "type": instrument_type,
                    "currency": "USD" if raw_ticker.endswith(".US") else "EUR" if instrument_type == "etf" else "PLN",
                    "provider": "yahoo" if instrument_type in {"stock_us", "etf"} else "stooq",
                    "symbol": purchase["ticker"] if instrument_type in {"stock_us", "etf"} else purchase["ticker"].lower(),
                })
                instrument = Instrument(**data)
                db.add(instrument)
                db.flush()
            else:
                errors.append(f"wiersz {purchase['row_number']}: nie znaleziono instrumentu {purchase['ticker'] or purchase['isin']}")
                continue
        transactions.append(Transaction(
            instrument_id=instrument.id,
            type="BUY",
            quantity=purchase["quantity"],
            price=purchase["price"],
            currency=purchase["currency"] or instrument.currency,
            date=purchase["date"],
            commission=purchase["commission"],
        ))
    if errors:
        return TransactionImportResult(imported=0, skipped=len(errors), errors=errors)
    db.add_all(transactions)
    db.commit()
    return TransactionImportResult(imported=len(transactions), skipped=0, errors=[])


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    tx = db.get(Transaction, transaction_id)
    if not tx:
        raise HTTPException(404, "Transakcja nie istnieje")
    db.delete(tx)
    db.commit()
    return {"ok": True}
