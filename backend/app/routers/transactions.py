from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import CashDeposit, Instrument, Transaction
from app.schemas import TransactionCreate, TransactionImportResult, TransactionOut
from app.seed import GPW_STOCK_TICKERS, apply_instrument_defaults
from app.services.portfolio import _signed_qty
from app.services.transaction_import import read_bossa_purchases, read_deposits, read_purchases

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
POLISH_IMPORT_TICKERS = set(GPW_STOCK_TICKERS) | {"NEU"}


def _infer_import_instrument_type(ticker: str | None, raw_ticker: str, category: str | None) -> str:
    if category == "etf":
        return "etf"
    if ticker in POLISH_IMPORT_TICKERS:
        return "stock_pl"
    return "stock_us" if raw_ticker.endswith(".US") else "stock_pl"


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
def import_transactions(
    file: UploadFile = File(...),
    source: str = Form("xstation5"),
    db: Session = Depends(get_db),
):
    if source not in {"xstation5", "bossa"}:
        raise HTTPException(400, "Nieznane źródło importu")
    expected_extension = ".xlsx" if source == "xstation5" else ".csv"
    if not file.filename or not file.filename.lower().endswith(expected_extension):
        raise HTTPException(400, f"Wybierz plik {expected_extension}")
    try:
        content = file.file.read()
        purchases, errors = read_purchases(content) if source == "xstation5" else read_bossa_purchases(content)
        deposits, deposit_errors = read_deposits(content) if source == "xstation5" else ([], [])
        errors.extend(deposit_errors)
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
            ticker_query = select(Instrument).where(Instrument.ticker == purchase["ticker"])
            if purchase["ticker"] in POLISH_IMPORT_TICKERS:
                ticker_query = ticker_query.where(Instrument.type == "stock_pl")
            instrument = db.scalar(ticker_query)
        if not instrument and purchase.get("name"):
            normalized_name = purchase["name"].strip().lower()
            instrument = db.scalar(
                select(Instrument).where(func.lower(Instrument.name).like(f"{normalized_name}%"))
            )
        if instrument and purchase.get("name") and purchase["name"].lower() != "my trades":
            instrument.name = purchase["name"]
        if instrument and purchase["ticker"] in POLISH_IMPORT_TICKERS and instrument.type != "stock_pl":
            instrument.type = "stock_pl"
            instrument.currency = "PLN"
            instrument.provider = "stooq"
            instrument.symbol = purchase["ticker"].lower()
            instrument.unit = "share"
        if not instrument:
            raw_ticker = purchase.get("raw_ticker") or ""
            category = purchase.get("category")
            instrument_type = _infer_import_instrument_type(purchase["ticker"], raw_ticker, category)
            if purchase["ticker"] and purchase.get("name"):
                data = apply_instrument_defaults({
                    "ticker": purchase["ticker"],
                    "name": purchase["name"],
                    "type": instrument_type,
                    "currency": "USD" if raw_ticker.endswith(".US") else "EUR" if instrument_type == "etf" else "PLN",
                    "provider": "yahoo" if instrument_type in {"stock_us", "etf"} else "stooq",
                })
                instrument = Instrument(**data)
                db.add(instrument)
                db.flush()
            else:
                errors.append(f"wiersz {purchase['row_number']}: nie znaleziono instrumentu {purchase['ticker'] or purchase['isin']}")
                continue
        transactions.append(Transaction(
            instrument_id=instrument.id,
            type=purchase.get("type", "BUY"),
            quantity=purchase["quantity"],
            price=purchase["price"],
            currency=purchase["currency"] or instrument.currency,
            date=purchase["date"],
            commission=purchase["commission"],
        ))
    if errors:
        return TransactionImportResult(imported=0, skipped=len(errors), errors=errors)
    db.add_all(transactions)
    db.add_all(
        CashDeposit(
            date=deposit["date"],
            amount=deposit["amount"],
            currency=deposit["currency"],
        )
        for deposit in deposits
    )
    db.commit()
    return TransactionImportResult(imported=len(transactions), deposits=len(deposits), skipped=0, errors=[])


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    tx = db.get(Transaction, transaction_id)
    if not tx:
        raise HTTPException(404, "Transakcja nie istnieje")
    db.delete(tx)
    db.commit()
    return {"ok": True}
