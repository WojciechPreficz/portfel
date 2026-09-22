from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import RefreshResult
from app.services.quotes import refresh_quotes

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


@router.post("/refresh", response_model=RefreshResult)
def refresh(db: Session = Depends(get_db)):
    return refresh_quotes(db)
