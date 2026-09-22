from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class InstrumentOut(BaseModel):
    id: int
    ticker: str
    isin: str | None
    name: str
    type: str
    currency: str
    provider: str
    symbol: str
    unit: str

    model_config = {"from_attributes": True}


class InstrumentCreate(BaseModel):
    ticker: str
    name: str | None = None
    type: str
    isin: str | None = None
    currency: str | None = None
    provider: str | None = None
    symbol: str | None = None
    unit: str | None = None


class TransactionCreate(BaseModel):
    instrument_id: int | None = None
    instrument: InstrumentCreate | None = None
    type: str = "BUY"
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(ge=0)
    currency: str | None = None
    date: date
    commission: Decimal = Field(default=Decimal("0"), ge=0)


class TransactionOut(BaseModel):
    id: int
    instrument_id: int
    type: str
    quantity: Decimal
    price: Decimal
    currency: str
    date: date
    commission: Decimal
    instrument: InstrumentOut

    model_config = {"from_attributes": True}


class PositionOut(BaseModel):
    instrument: InstrumentOut
    quantity: Decimal
    avg_cost: Decimal
    cost_pln: Decimal
    price: Decimal | None
    price_date: date | None
    market_value_pln: Decimal
    pnl_pln: Decimal
    pnl_pct: Decimal | None
    change_1d_pln: Decimal
    change_1d_pct: Decimal | None
    weight_pct: Decimal | None


class PortfolioSummary(BaseModel):
    value_pln: Decimal
    value_prev_pln: Decimal
    change_1d_pln: Decimal
    change_1d_pct: Decimal | None
    cost_pln: Decimal
    pnl_pln: Decimal
    pnl_pct: Decimal | None
    as_of: date | None
    positions: list[PositionOut]


class HistoryPoint(BaseModel):
    date: date
    value_pln: Decimal


class PricePoint(BaseModel):
    date: date
    close: Decimal
    currency: str


class FxLatest(BaseModel):
    pair: str
    date: date
    rate: Decimal


class RefreshResult(BaseModel):
    instruments: int
    prices_upserted: int
    fx_upserted: int
    errors: list[str] = []
