import re
import secrets
import unicodedata
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AssetCashFlow,
    Instrument,
    Portfolio,
    Price,
    PropertyDetails,
    Transaction,
)
from app.schemas import (
    AssetCashFlowCreate,
    AssetCashFlowOut,
    AssetCashFlowPatch,
    PropertyDetailsPatch,
    RealEstateCreate,
    RealEstateOut,
    ValuationCreate,
    ValuationOut,
)
from app.services.portfolio import build_property_metrics, price_on
from app.services.quotes import _upsert_price

router = APIRouter(prefix="/api/real-estate", tags=["real-estate"])
instrument_router = APIRouter(prefix="/api/instruments", tags=["valuations", "asset-cash-flows"])
cash_flows_router = APIRouter(prefix="/api/cash-flows", tags=["asset-cash-flows"])


def _get_property(db: Session, instrument_id: int) -> tuple[Instrument, PropertyDetails]:
    instrument = db.get(Instrument, instrument_id)
    details = db.get(PropertyDetails, instrument_id)
    if instrument is None or instrument.type != "real_estate" or details is None:
        raise HTTPException(404, "Nieruchomość nie istnieje")
    return instrument, details


def _property_out(db: Session, instrument: Instrument) -> dict:
    details = db.get(PropertyDetails, instrument.id)
    transactions = db.scalars(
        select(Transaction)
        .where(Transaction.instrument_id == instrument.id, Transaction.type == "BUY")
        .order_by(Transaction.date, Transaction.id)
    ).all()
    first_purchase = transactions[0] if transactions else None
    portfolio_id = db.scalar(
        select(Transaction.portfolio_id)
        .where(Transaction.instrument_id == instrument.id)
        .order_by(Transaction.date, Transaction.id)
        .limit(1)
    )
    valuation = price_on(db, instrument.id, date.today())
    return {
        "id": instrument.id,
        "ticker": instrument.ticker,
        "name": instrument.name,
        "address": details.address if details else None,
        "area_m2": details.area_m2 if details else None,
        "currency": instrument.currency,
        "rental_tax_rate": details.rental_tax_rate if details else Decimal("0.085"),
        "interpolate_valuations": details.interpolate_valuations if details else False,
        "portfolio_id": portfolio_id,
        "purchase_date": first_purchase.date if first_purchase else None,
        "purchase_price": first_purchase.price if first_purchase else None,
        "transaction_costs": first_purchase.commission if first_purchase else None,
        "valuation": valuation.close if valuation else None,
        "valuation_date": valuation.date if valuation else None,
    }


def _make_ticker(db: Session, name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:16].strip("-") or "lokal"
    while True:
        ticker = f"RE-{slug}-{secrets.token_hex(3)}"
        exists = db.scalar(
            select(Instrument.id).where(
                (Instrument.ticker == ticker) | (Instrument.symbol == ticker)
            )
        )
        if exists is None:
            return ticker


def _default_rent_tax(db: Session, instrument_id: int, amount: Decimal) -> Decimal:
    details = db.get(PropertyDetails, instrument_id)
    rate = details.rental_tax_rate if details is not None else Decimal("0.085")
    return (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _cash_flow_or_404(db: Session, cash_flow_id: int) -> AssetCashFlow:
    cash_flow = db.get(AssetCashFlow, cash_flow_id)
    if cash_flow is None:
        raise HTTPException(404, "Przepływ pieniężny nie istnieje")
    return cash_flow


@router.post("", response_model=RealEstateOut, status_code=201)
def create_real_estate(payload: RealEstateCreate, db: Session = Depends(get_db)):
    if db.get(Portfolio, payload.portfolio_id) is None:
        raise HTTPException(422, "Wybrany portfel nie istnieje")
    currency = payload.currency.upper()
    ticker = _make_ticker(db, payload.name)
    instrument = Instrument(
        ticker=ticker,
        name=payload.name,
        type="real_estate",
        currency=currency,
        provider="manual",
        symbol=ticker,
        unit="property",
    )
    initial_valuation = payload.initial_valuation or payload.purchase_price
    try:
        db.add(instrument)
        db.flush()
        db.add(
            PropertyDetails(
                instrument_id=instrument.id,
                area_m2=payload.area_m2,
                address=payload.address,
                rental_tax_rate=payload.rental_tax_rate,
                interpolate_valuations=False,
            )
        )
        db.add(
            Transaction(
                portfolio_id=payload.portfolio_id,
                instrument_id=instrument.id,
                type="BUY",
                quantity=Decimal("1"),
                price=payload.purchase_price,
                commission=payload.transaction_costs,
                currency=currency,
                date=payload.purchase_date,
            )
        )
        _upsert_price(db, instrument.id, payload.purchase_date, initial_valuation, currency)
        db.commit()
        db.refresh(instrument)
    except Exception:
        db.rollback()
        raise
    return _property_out(db, instrument)


@router.get("", response_model=list[RealEstateOut])
def list_real_estate(
    portfolio_id: int | None = Query(default=None), db: Session = Depends(get_db)
):
    query = select(Instrument).join(PropertyDetails).where(Instrument.type == "real_estate")
    if portfolio_id is not None:
        query = query.join(Transaction).where(Transaction.portfolio_id == portfolio_id)
    instruments = db.scalars(query.distinct().order_by(Instrument.name)).all()
    return [_property_out(db, instrument) for instrument in instruments]


@router.get("/{instrument_id}", response_model=RealEstateOut)
def get_real_estate(instrument_id: int, db: Session = Depends(get_db)):
    instrument, _details = _get_property(db, instrument_id)
    return _property_out(db, instrument)


@router.patch("/{instrument_id}", response_model=RealEstateOut)
def patch_real_estate(
    instrument_id: int,
    payload: PropertyDetailsPatch,
    db: Session = Depends(get_db),
):
    instrument, details = _get_property(db, instrument_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        if changes["name"] is None:
            raise HTTPException(422, "Nazwa nieruchomości nie może być pusta")
        instrument.name = changes.pop("name")
    for field, value in changes.items():
        setattr(details, field, value)
    db.commit()
    db.refresh(instrument)
    return _property_out(db, instrument)


@router.get("/{instrument_id}/metrics")
def real_estate_metrics(
    instrument_id: int,
    portfolio_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    instrument, _details = _get_property(db, instrument_id)
    purchase_query = select(func.min(Transaction.date)).where(
        Transaction.instrument_id == instrument_id,
        Transaction.type == "BUY",
    )
    if portfolio_id is not None:
        purchase_query = purchase_query.where(Transaction.portfolio_id == portfolio_id)
    purchase_date = db.scalar(purchase_query)
    if purchase_date is None:
        raise HTTPException(404, "Nie znaleziono zakupu tej nieruchomości w portfelu")
    start = date_from or purchase_date
    end = date_to or date.today()
    if start > end:
        raise HTTPException(422, "Data początkowa nie może być późniejsza niż końcowa")
    return build_property_metrics(db, instrument.id, portfolio_id, start, end)


@instrument_router.get("/{instrument_id}/valuations", response_model=list[ValuationOut])
def list_valuations(instrument_id: int, db: Session = Depends(get_db)):
    instrument, _details = _get_property(db, instrument_id)
    return db.scalars(
        select(Price).where(Price.instrument_id == instrument.id).order_by(Price.date)
    ).all()


@instrument_router.post("/{instrument_id}/valuations", response_model=ValuationOut)
def create_valuation(
    instrument_id: int,
    payload: ValuationCreate,
    db: Session = Depends(get_db),
):
    instrument, _details = _get_property(db, instrument_id)
    try:
        _upsert_price(db, instrument.id, payload.date, payload.value, instrument.currency)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return {"date": payload.date, "close": payload.value, "currency": instrument.currency}


@instrument_router.delete("/{instrument_id}/valuations")
def delete_valuation(
    instrument_id: int,
    valuation_date: date = Query(alias="date"),
    db: Session = Depends(get_db),
):
    instrument, _details = _get_property(db, instrument_id)
    price = db.scalar(
        select(Price).where(
            Price.instrument_id == instrument.id,
            Price.date == valuation_date,
        )
    )
    if price is None:
        raise HTTPException(404, "Wycena nie istnieje")
    purchase_date = db.scalar(
        select(func.min(Transaction.date)).where(
            Transaction.instrument_id == instrument.id,
            Transaction.type == "BUY",
        )
    )
    valuation_count = db.scalar(
        select(func.count(Price.id)).where(Price.instrument_id == instrument.id)
    )
    if valuation_date == purchase_date and valuation_count == 1:
        raise HTTPException(422, "Nie można usunąć jedynej wyceny z dnia zakupu")
    db.delete(price)
    db.commit()
    return {"ok": True}


@instrument_router.get("/{instrument_id}/cash-flows", response_model=list[AssetCashFlowOut])
def list_asset_cash_flows(
    instrument_id: int,
    portfolio_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if db.get(Instrument, instrument_id) is None:
        raise HTTPException(404, "Instrument nie istnieje")
    query = select(AssetCashFlow).where(AssetCashFlow.instrument_id == instrument_id)
    if portfolio_id is not None:
        query = query.where(AssetCashFlow.portfolio_id == portfolio_id)
    return db.scalars(query.order_by(AssetCashFlow.date.desc(), AssetCashFlow.id.desc())).all()


@instrument_router.post("/{instrument_id}/cash-flows", response_model=AssetCashFlowOut, status_code=201)
def create_asset_cash_flow(
    instrument_id: int,
    payload: AssetCashFlowCreate,
    db: Session = Depends(get_db),
):
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(404, "Instrument nie istnieje")
    if db.get(Portfolio, payload.portfolio_id) is None:
        raise HTTPException(422, "Wybrany portfel nie istnieje")
    has_transaction = db.scalar(
        select(Transaction.id)
        .where(
            Transaction.instrument_id == instrument_id,
            Transaction.portfolio_id == payload.portfolio_id,
        )
        .limit(1)
    )
    if has_transaction is None:
        raise HTTPException(422, "Instrument nie ma transakcji w wybranym portfelu")
    tax_amount = payload.tax_amount
    if payload.kind == "RENT" and tax_amount is None:
        tax_amount = _default_rent_tax(db, instrument_id, payload.amount)
    cash_flow = AssetCashFlow(
        portfolio_id=payload.portfolio_id,
        instrument_id=instrument_id,
        date=payload.date,
        kind=payload.kind.value,
        category=payload.category,
        amount=payload.amount,
        tax_amount=tax_amount or Decimal("0"),
        currency=(payload.currency or instrument.currency).upper(),
        note=payload.note,
    )
    db.add(cash_flow)
    db.commit()
    db.refresh(cash_flow)
    return cash_flow


@cash_flows_router.patch("/{cash_flow_id}", response_model=AssetCashFlowOut)
def patch_asset_cash_flow(
    cash_flow_id: int,
    payload: AssetCashFlowPatch,
    db: Session = Depends(get_db),
):
    cash_flow = _cash_flow_or_404(db, cash_flow_id)
    changes = payload.model_dump(exclude_unset=True)
    kind = changes.get("kind", AssetCashFlowKind(cash_flow.kind))
    amount = changes.get("amount", cash_flow.amount)
    if kind == AssetCashFlowKind.RENT and (
        changes.get("tax_amount", cash_flow.tax_amount) is None
        or ("kind" in changes and "tax_amount" not in changes)
    ):
        changes["tax_amount"] = _default_rent_tax(db, cash_flow.instrument_id, amount)
    elif changes.get("tax_amount", cash_flow.tax_amount) is None:
        changes["tax_amount"] = Decimal("0")
    for field, value in changes.items():
        if field == "currency" and value is not None:
            value = value.upper()
        setattr(cash_flow, field, value.value if isinstance(value, AssetCashFlowKind) else value)
    db.commit()
    db.refresh(cash_flow)
    return cash_flow


@cash_flows_router.delete("/{cash_flow_id}")
def delete_asset_cash_flow(cash_flow_id: int, db: Session = Depends(get_db)):
    cash_flow = _cash_flow_or_404(db, cash_flow_id)
    db.delete(cash_flow)
    db.commit()
    return {"ok": True}
