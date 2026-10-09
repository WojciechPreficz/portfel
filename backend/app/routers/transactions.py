from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import CashDeposit, CashMovement, Instrument, Portfolio, Transaction
from app.schemas import TransactionCreate, TransactionImportResult, TransactionOut
from app.seed import apply_instrument_defaults
from app.services.portfolio import _signed_qty
from app.services.symbol_resolver import ResolutionError, resolve
from app.services.transaction_import import read_bossa_purchases, read_cash_movements, read_deposits, read_purchases

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
    if instrument.type == "gold" and payload.type == "BUY":
        if payload.purchase_price_pln is None:
            raise HTTPException(400, "Podaj całkowitą cenę zakupu złota w PLN")
        if payload.currency not in {None, "PLN"}:
            raise HTTPException(400, "Cena zakupu złota musi być podana w PLN")
    elif payload.purchase_price_pln is not None:
        raise HTTPException(400, "Cena zakupu w PLN jest dostępna tylko dla złota")
    portfolio_id = payload.portfolio_id
    if portfolio_id is None:
        portfolio_id = db.scalar(select(Portfolio.id).order_by(Portfolio.id).limit(1))
    if portfolio_id is None or not db.get(Portfolio, portfolio_id):
        raise HTTPException(400, "Nieznany portfel")
    if payload.type == "SELL":
        existing = db.scalars(
            select(Transaction).where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.instrument_id == instrument.id,
            )
        ).all()
        qty = sum((_signed_qty(tx) for tx in existing), Decimal("0"))
        if payload.quantity > qty:
            raise HTTPException(400, "Sprzedaż większa niż posiadana ilość")
    tx = Transaction(
        portfolio_id=portfolio_id,
        instrument_id=instrument.id,
        type=payload.type,
        quantity=payload.quantity,
        price=payload.price,
        purchase_price_pln=payload.purchase_price_pln,
        currency="PLN" if instrument.type == "gold" and payload.type == "BUY" else payload.currency or instrument.currency,
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
    portfolio_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    if portfolio_id is None:
        portfolio_id = db.scalar(select(Portfolio.id).order_by(Portfolio.id).limit(1))
    if portfolio_id is None or not db.get(Portfolio, portfolio_id):
        raise HTTPException(400, "Nieznany portfel")
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
        movements, movement_errors = read_cash_movements(content) if source == "xstation5" else ([], [])
        errors.extend(movement_errors)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if errors:
        return TransactionImportResult(imported=0, skipped=len(errors), errors=errors)

    transactions = []
    imported_instrument_ids = set()
    for purchase in sorted(purchases, key=lambda row: row.get("timestamp", row["date"].isoformat())):
        resolution = resolve(
            db,
            raw_ticker=purchase.get("raw_ticker"),
            isin=purchase.get("isin"),
            name=purchase.get("name"),
            category=purchase.get("category"),
            currency_hint=purchase.get("currency"),
        )
        if isinstance(resolution, ResolutionError):
            errors.append(f"wiersz {purchase['row_number']}: {resolution.message}")
            continue
        instrument = db.get(Instrument, resolution.instrument_id) if resolution.instrument_id else None
        if instrument is None:
            instrument = Instrument(
                ticker=resolution.ticker,
                isin=purchase.get("isin"),
                name=purchase.get("name") or resolution.ticker,
                type=resolution.type,
                currency=resolution.currency,
                provider=resolution.provider,
                symbol=resolution.symbol,
                unit="share",
            )
            db.add(instrument)
            db.flush()
        imported_instrument_ids.add(instrument.id)
        transactions.append(Transaction(
            portfolio_id=portfolio_id,
            instrument_id=instrument.id,
            type=purchase.get("type", "BUY"),
            quantity=purchase["quantity"],
            price=purchase["price"],
            currency=purchase["currency"] or instrument.currency,
            date=purchase["date"],
            commission=purchase["commission"],
            purchase_price_pln=purchase.get("purchase_price_pln"),
        ))
    if errors:
        return TransactionImportResult(imported=0, skipped=len(errors), errors=errors)
    db.add_all(transactions)
    db.add_all(CashMovement(portfolio_id=portfolio_id, **movement) for movement in movements)
    db.add_all(
        CashDeposit(
            portfolio_id=portfolio_id,
            date=deposit["date"],
            amount=deposit["amount"],
            currency=deposit["currency"],
        )
        for deposit in deposits
    )
    db.commit()
    return TransactionImportResult(
        imported=len(transactions),
        deposits=len(deposits),
        skipped=0,
        errors=[],
        instrument_ids=sorted(imported_instrument_ids),
    )


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    tx = db.get(Transaction, transaction_id)
    if not tx:
        raise HTTPException(404, "Transakcja nie istnieje")
    db.delete(tx)
    db.commit()
    return {"ok": True}
