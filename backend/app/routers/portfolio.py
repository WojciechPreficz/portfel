from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import HistoryPoint, PortfolioSummary
from app.services.portfolio import build_history, build_summary

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
def summary(db: Session = Depends(get_db)):
    return build_summary(db)


@router.get("/history", response_model=list[HistoryPoint])
def history(db: Session = Depends(get_db)):
    return build_history(db)
