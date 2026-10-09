from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AssetCashFlow, CashDeposit, Instrument, Portfolio, Price, PropertyDetails, Transaction
from app.schemas import HistoryPoint, PortfolioCreate, PortfolioOut, PortfolioSummary
from app.services.portfolio import build_history, build_summary

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
portfolios_router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


@portfolios_router.get("", response_model=list[PortfolioOut])
def list_portfolios(db: Session = Depends(get_db)):
    return db.scalars(select(Portfolio).order_by(Portfolio.id)).all()


@portfolios_router.post("", response_model=PortfolioOut)
def create_portfolio(payload: PortfolioCreate, db: Session = Depends(get_db)):
    portfolio = Portfolio(name=payload.name.strip())
    if not portfolio.name:
        raise HTTPException(422, "Nazwa portfela nie może być pusta")
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


@portfolios_router.patch("/{portfolio_id}", response_model=PortfolioOut)
def rename_portfolio(portfolio_id: int, payload: PortfolioCreate, db: Session = Depends(get_db)):
    portfolio = db.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(404, "Portfel nie istnieje")
    portfolio.name = payload.name.strip()
    if not portfolio.name:
        raise HTTPException(422, "Nazwa portfela nie może być pusta")
    db.commit()
    db.refresh(portfolio)
    return portfolio


@portfolios_router.delete("/{portfolio_id}")
def delete_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = db.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(404, "Portfel nie istnieje")
    result = _delete_portfolio_data(db, portfolio_id)
    db.delete(portfolio)
    db.commit()
    return {"deleted_portfolio": portfolio_id, **result}


@router.get("/summary", response_model=PortfolioSummary)
def summary(portfolio_id: int | None = None, db: Session = Depends(get_db)):
    return build_summary(db, portfolio_id)


@router.get("/history", response_model=list[HistoryPoint])
def history(portfolio_id: int | None = None, db: Session = Depends(get_db)):
    return build_history(db, portfolio_id)


@router.delete("/holdings")
def delete_holdings(portfolio_id: int, db: Session = Depends(get_db)):
    result = _delete_portfolio_data(db, portfolio_id)
    db.commit()
    return result


def _delete_portfolio_data(db: Session, portfolio_id: int):
    deleted_deposits = db.query(CashDeposit).filter(CashDeposit.portfolio_id == portfolio_id).delete()
    deleted_asset_cash_flows = db.query(AssetCashFlow).filter(
        AssetCashFlow.portfolio_id == portfolio_id
    ).delete()
    instrument_ids = db.scalars(
        select(Transaction.instrument_id).where(Transaction.portfolio_id == portfolio_id).distinct()
    ).all()
    if not instrument_ids:
        return {
            "deleted_instruments": 0,
            "deleted_transactions": 0,
            "deleted_prices": 0,
            "deleted_deposits": deleted_deposits,
            "deleted_asset_cash_flows": deleted_asset_cash_flows,
            "deleted_property_details": 0,
        }

    deleted_transactions = db.execute(
        delete(Transaction).where(
            Transaction.portfolio_id == portfolio_id,
            Transaction.instrument_id.in_(instrument_ids),
        )
    ).rowcount
    unused_instrument_ids = db.scalars(
        select(Instrument.id)
        .where(
            Instrument.id.in_(instrument_ids),
            ~select(Transaction.id).where(Transaction.instrument_id == Instrument.id).exists(),
            ~select(AssetCashFlow.id)
            .where(AssetCashFlow.instrument_id == Instrument.id)
            .exists(),
        )
    ).all()
    manual_instrument_ids = db.scalars(
        select(Instrument.id).where(
            Instrument.id.in_(unused_instrument_ids),
            Instrument.provider == "manual",
        )
    ).all()
    deleted_property_details = db.execute(
        delete(PropertyDetails).where(
            PropertyDetails.instrument_id.in_(manual_instrument_ids)
        )
    ).rowcount
    deleted_prices = db.execute(delete(Price).where(Price.instrument_id.in_(unused_instrument_ids))).rowcount
    deleted_instruments = db.execute(
        delete(Instrument).where(Instrument.id.in_(unused_instrument_ids))
    ).rowcount
    return {
        "deleted_instruments": deleted_instruments,
        "deleted_transactions": deleted_transactions,
        "deleted_prices": deleted_prices,
        "deleted_deposits": deleted_deposits,
        "deleted_asset_cash_flows": deleted_asset_cash_flows,
        "deleted_property_details": deleted_property_details,
    }
