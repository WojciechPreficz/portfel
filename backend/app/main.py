from contextlib import asynccontextmanager
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text
from starlette.routing import Match

from app.auth import require_auth, router as auth_router, validate_auth_configuration
from app.config import (
    DATABASE_PATH,
    PORTFEL_AUTH_DISABLED,
    PORTFEL_CORS_ORIGINS,
    PORTFEL_FRONTEND_DIR,
    PORTFEL_SCHEDULER_ENABLED,
)
from app.database import SessionLocal, engine
from app.models import Base, Portfolio
from app.routers import fx, instruments, portfolio, quotes, transactions
from app.seed import seed_instruments
from app.services.quotes import refresh_quotes

scheduler = BackgroundScheduler(timezone=ZoneInfo("Europe/Warsaw"))
logger = logging.getLogger(__name__)


class FrontendRoute(APIRoute):
    def matches(self, scope):
        path = scope["path"]
        excluded_prefixes = ("/api", auth_router.prefix.rstrip("/"))
        if any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in excluded_prefixes
        ):
            return Match.NONE, {}
        return super().matches(scope)


def mount_frontend(app: FastAPI, frontend_dir: Path) -> None:
    if not frontend_dir.is_dir():
        return

    frontend_root = frontend_dir.resolve()
    app.mount(
        "/assets",
        StaticFiles(directory=frontend_root / "assets", check_dir=False),
        name="frontend-assets",
    )

    def serve_frontend(full_path: str):
        candidate = (frontend_root / full_path).resolve()
        try:
            candidate.relative_to(frontend_root)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not Found") from None

        if candidate.is_file():
            return FileResponse(candidate)

        index_file = frontend_root / "index.html"
        if not index_file.is_file():
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(index_file)

    frontend_router = APIRouter(route_class=FrontendRoute)
    frontend_router.add_api_route(
        "/{full_path:path}",
        serve_frontend,
        methods=["GET"],
        include_in_schema=False,
    )
    app.include_router(frontend_router)


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


def initialize() -> None:
    validate_auth_configuration()
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = engine.connect()
    try:
        connection.exec_driver_sql("PRAGMA busy_timeout = 30000")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        Base.metadata.create_all(bind=connection)
        db = SessionLocal(bind=connection)
        try:
            _ensure_portfolio_schema(db)
            seed_instruments(db)
        finally:
            db.close()
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize()
    if PORTFEL_SCHEDULER_ENABLED:
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
    if PORTFEL_SCHEDULER_ENABLED:
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
    allow_origins=PORTFEL_CORS_ORIGINS,
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


mount_frontend(app, PORTFEL_FRONTEND_DIR)
