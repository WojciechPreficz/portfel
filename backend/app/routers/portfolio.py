from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CashDeposit, Instrument, Price, Transaction
from app.schemas import HistoryPoint, PortfolioSummary
from app.services.portfolio import build_history, build_summary

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
def summary(db: Session = Depends(get_db)):
    return build_summary(db)


@router.get("/history", response_model=list[HistoryPoint])
def history(db: Session = Depends(get_db)):
    return build_history(db)


@router.delete("/holdings")
def delete_holdings(db: Session = Depends(get_db)):
    deleted_deposits = db.query(CashDeposit).delete()
    instrument_ids = db.scalars(select(Transaction.instrument_id).distinct()).all()
    if not instrument_ids:
        db.commit()
        return {"deleted_instruments": 0, "deleted_transactions": 0, "deleted_prices": 0, "deleted_deposits": deleted_deposits}

    deleted_prices = db.execute(delete(Price).where(Price.instrument_id.in_(instrument_ids))).rowcount
    deleted_transactions = db.execute(delete(Transaction).where(Transaction.instrument_id.in_(instrument_ids))).rowcount
    deleted_instruments = db.execute(delete(Instrument).where(Instrument.id.in_(instrument_ids))).rowcount
    db.commit()
    return {
        "deleted_instruments": deleted_instruments,
        "deleted_transactions": deleted_transactions,
        "deleted_prices": deleted_prices,
        "deleted_deposits": deleted_deposits,
    }
