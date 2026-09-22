from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import DATA_DIR
from app.database import SessionLocal, engine
from app.models import Base
from app.routers import fx, instruments, portfolio, quotes, transactions
from app.seed import seed_instruments
from app.services.quotes import refresh_quotes

scheduler = BackgroundScheduler(timezone=ZoneInfo("Europe/Warsaw"))


def _scheduled_refresh():
    db = SessionLocal()
    try:
        refresh_quotes(db)
    except Exception:
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_instruments(db)
    finally:
        db.close()
    scheduler.add_job(
        _scheduled_refresh,
        CronTrigger(hour=17, minute=10, timezone="Europe/Warsaw"),
        id="refresh_gpw",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled_refresh,
        CronTrigger(hour=22, minute=10, timezone="Europe/Warsaw"),
        id="refresh_us",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Portfel", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(instruments.router)
app.include_router(transactions.router)
app.include_router(portfolio.router)
app.include_router(quotes.router)
app.include_router(fx.router)


@app.get("/api/health")
def health():
    return {"ok": True}
