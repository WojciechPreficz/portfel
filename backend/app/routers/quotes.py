from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import GoldQuote, RefreshResult
from app.services.adapters.nbp import fetch_latest_fx
from app.services.adapters.yahoo import YahooAdapter
from app.services.quotes import refresh_quotes

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.post("/refresh", response_model=RefreshResult)
def refresh(
    instrument_ids: list[int] | None = Query(None),
    db: Session = Depends(get_db),
):
    return refresh_quotes(db, instrument_ids=instrument_ids)


@router.get("/gold", response_model=GoldQuote)
def gold_quote():
    try:
        spot = YahooAdapter().fetch_last("GC=F", "USD")
        if spot is None:
            raise ValueError("Yahoo Finance nie zwrócił ceny złota (GC=F)")
        fx_date, usd_pln = fetch_latest_fx("USD")
    except (httpx.HTTPError, ValueError, KeyError, IndexError, ArithmeticError) as exc:
        raise HTTPException(502, f"Nie udało się pobrać ceny złota lub kursu NBP: {exc}") from exc
    return GoldQuote(
        spot_usd_oz=spot.close,
        spot_date=spot.date,
        usd_pln=usd_pln,
        fx_date=fx_date,
        price_pln_g=spot.close * usd_pln / Decimal("31.1034768"),
    )
