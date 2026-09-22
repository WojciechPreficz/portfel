from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FxRate
from app.schemas import FxLatest

router = APIRouter(prefix="/api/fx", tags=["fx"])


@router.get("/latest", response_model=list[FxLatest])
def latest_fx(db: Session = Depends(get_db)):
    result = []
    for pair in ("USDPLN", "EURPLN"):
        row = db.scalar(
            select(FxRate).where(FxRate.pair == pair).order_by(FxRate.date.desc()).limit(1)
        )
        if row:
            result.append(row)
    return result
