from contextlib import asynccontextmanager
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, select, text

from app.auth import require_auth, router as auth_router, validate_auth_configuration
from app.config import DATABASE_PATH, PORTFEL_AUTH_DISABLED
from app.database import SessionLocal, engine
from app.models import Base, Portfolio
from app.routers import fx, instruments, portfolio, quotes, transactions
from app.seed import seed_instruments
from app.services.quotes import refresh_quotes

scheduler = BackgroundScheduler(timezone=ZoneInfo("Europe/Warsaw"))
logger = logging.getLogger(__name__)


def _ensure_portfolio_schema(db):
    inspector = inspect(db.bind)
    columns = {column["name"] for column in inspector.get_columns("transactions")}
    if "portfolio_id" not in columns:
        db.execute(text("ALTER TABLE transactions ADD COLUMN portfolio_id INTEGER REFERENCES portfolios(id)"))
    if "purchase_price_pln" not in columns:
        db.execute(text("ALTER TABLE transactions ADD COLUMN purchase_price_pln NUMERIC(18, 8)"))
    deposit_columns = {column["name"] for column in inspector.get_columns("cash_deposits")}
    if "portfolio_id" not in deposit_columns:
        db.execute(text("ALTER TABLE cash_deposits ADD COLUMN portfolio_id INTEGER REFERENCES portfolios(id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_transactions_portfolio_id ON transactions(portfolio_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_cash_deposits_portfolio_id ON cash_deposits(portfolio_id)"))
    default_portfolio = db.scalar(select(Portfolio).order_by(Portfolio.id).limit(1))
    if default_portfolio is None:
        default_portfolio = Portfolio(name="Portfel główny")
        db.add(default_portfolio)
        db.flush()
    db.execute(
        text("UPDATE transactions SET portfolio_id = :portfolio_id WHERE portfolio_id IS NULL"),
        {"portfolio_id": default_portfolio.id},
    )
    db.execute(
        text("UPDATE cash_deposits SET portfolio_id = :portfolio_id WHERE portfolio_id IS NULL"),
        {"portfolio_id": default_portfolio.id},
    )
    db.commit()


def _scheduled_refresh():
    db = SessionLocal()
    try:
        result = refresh_quotes(db)
        if result["errors"]:
            logger.error("Scheduled quote refresh completed with errors: %s", result["errors"])
    except Exception:
        db.rollback()
        logger.exception("Scheduled quote refresh failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_auth_configuration()
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _ensure_portfolio_schema(db)
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


app = FastAPI(
    title="Portfel",
    lifespan=lifespan,
    docs_url="/docs" if PORTFEL_AUTH_DISABLED else None,
    redoc_url="/redoc" if PORTFEL_AUTH_DISABLED else None,
    openapi_url="/openapi.json" if PORTFEL_AUTH_DISABLED else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
protected_routers = (
    instruments.router,
    transactions.router,
    portfolio.router,
    portfolio.portfolios_router,
    quotes.router,
    fx.router,
)
for router in protected_routers:
    app.include_router(router, dependencies=[Depends(require_auth)])
app.include_router(auth_router)


@app.get("/api/health", dependencies=[Depends(require_auth)])
def health():
    return {"ok": True}
