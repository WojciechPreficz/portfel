from __future__ import annotations

from datetime import date as date_type, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator


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


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PortfolioOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    portfolio_id: int | None = None
    instrument_id: int | None = None
    instrument: InstrumentCreate | None = None
    type: str = "BUY"
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(ge=0)
    purchase_price_pln: Decimal | None = Field(default=None, gt=0)
    currency: str | None = None
    date: date_type
    commission: Decimal = Field(default=Decimal("0"), ge=0)


class TransactionOut(BaseModel):
    id: int
    instrument_id: int
    type: str
    quantity: Decimal
    price: Decimal
    purchase_price_pln: Decimal | None
    currency: str
    date: date_type
    commission: Decimal
    instrument: InstrumentOut

    model_config = {"from_attributes": True}


class TransactionImportResult(BaseModel):
    imported: int
    deposits: int = 0
    skipped: int
    errors: list[str]
    instrument_ids: list[int] = Field(default_factory=list)


class PositionOut(BaseModel):
    instrument: InstrumentOut
    quantity: Decimal
    avg_cost: Decimal | None
    cost_pln: Decimal | None
    price: Decimal | None
    price_date: date_type | None
    market_value_pln: Decimal | None
    pnl_pln: Decimal | None
    pnl_pct: Decimal | None
    change_1d_pln: Decimal | None
    change_1d_pct: Decimal | None
    weight_pct: Decimal | None
    income_pln: Decimal | None = None
    costs_pln: Decimal | None = None
    capex_pln: Decimal | None = None
    total_return_pln: Decimal | None = None
    xirr_pct: Decimal | None = None
    valuation_date: date_type | None = None


class PortfolioSummary(BaseModel):
    value_pln: Decimal | None
    cash_pln: Decimal | None = None
    total_value_pln: Decimal | None = None
    value_prev_pln: Decimal | None
    change_1d_pln: Decimal | None
    change_1d_pct: Decimal | None
    cost_pln: Decimal | None
    pnl_pln: Decimal | None
    pnl_pct: Decimal | None
    xirr_pct: Decimal | None
    as_of: date_type | None
    positions: list[PositionOut]
    income_pln: Decimal | None = None
    costs_pln: Decimal | None = None
    total_return_pln: Decimal | None = None


class HistoryPoint(BaseModel):
    date: date_type
    value_pln: Decimal


class PricePoint(BaseModel):
    date: date_type
    close: Decimal
    currency: str


class FxLatest(BaseModel):
    pair: str
    date: date_type
    rate: Decimal


class GoldQuote(BaseModel):
    spot_usd_oz: Decimal
    spot_date: date_type
    usd_pln: Decimal
    fx_date: date_type
    price_pln_g: Decimal


class RefreshResult(BaseModel):
    instruments: int
    prices_upserted: int
    fx_upserted: int
    errors: list[str] = []


class AssetCashFlowKind(str, Enum):
    RENT = "RENT"
    OTHER_INCOME = "OTHER_INCOME"
    OPEX = "OPEX"
    CAPEX = "CAPEX"
    TAX = "TAX"


class RealEstateCreate(BaseModel):
    portfolio_id: int
    name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    area_m2: Decimal | None = None
    purchase_date: date_type
    purchase_price: Decimal
    transaction_costs: Decimal
    currency: str = Field(default="PLN", min_length=3, max_length=3)
    rental_tax_rate: Decimal = Decimal("0.085")
    initial_valuation: Decimal | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Nazwa nieruchomości nie może być pusta")
        return value.strip()

    @field_validator("area_m2")
    @classmethod
    def validate_area(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("Metraż musi być większy od zera")
        return value

    @field_validator("purchase_price")
    @classmethod
    def validate_purchase_price(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Cena zakupu musi być większa od zera")
        return value

    @field_validator("transaction_costs")
    @classmethod
    def validate_transaction_costs(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("Koszty transakcyjne nie mogą być ujemne")
        return value

    @field_validator("initial_valuation")
    @classmethod
    def validate_initial_valuation(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("Wycena początkowa musi być większa od zera")
        return value

    @field_validator("rental_tax_rate")
    @classmethod
    def validate_rental_tax_rate(cls, value: Decimal) -> Decimal:
        if value < 0 or value > 1:
            raise ValueError("Stawka ryczałtu musi mieścić się w przedziale od 0 do 1")
        return value


class PropertyDetailsPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    area_m2: Decimal | None = None
    rental_tax_rate: Decimal | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Nazwa nieruchomości nie może być pusta")
        return value.strip() if value is not None else value

    @field_validator("area_m2")
    @classmethod
    def validate_area(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("Metraż musi być większy od zera")
        return value

    @field_validator("rental_tax_rate")
    @classmethod
    def validate_rental_tax_rate(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (value < 0 or value > 1):
            raise ValueError("Stawka ryczałtu musi mieścić się w przedziale od 0 do 1")
        return value


class RealEstateOut(BaseModel):
    id: int
    ticker: str
    name: str
    address: str | None
    area_m2: Decimal | None
    currency: str
    rental_tax_rate: Decimal
    interpolate_valuations: bool
    portfolio_id: int | None
    purchase_date: date_type | None
    purchase_price: Decimal | None
    transaction_costs: Decimal | None
    valuation: Decimal | None
    valuation_date: date_type | None


class ValuationCreate(BaseModel):
    date: date_type
    value: Decimal

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Wartość wyceny musi być większa od zera")
        return value


class ValuationOut(BaseModel):
    date: date_type
    close: Decimal
    currency: str

    model_config = {"from_attributes": True}


class AssetCashFlowCreate(BaseModel):
    portfolio_id: int
    date: date_type
    kind: AssetCashFlowKind
    category: str | None = Field(default=None, max_length=64)
    amount: Decimal
    tax_amount: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("kind", mode="before")
    @classmethod
    def validate_kind(cls, value):
        try:
            return AssetCashFlowKind(value)
        except (TypeError, ValueError):
            raise ValueError("Nieprawidłowy rodzaj przepływu pieniężnego") from None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Kwota przepływu musi być większa od zera")
        return value

    @field_validator("tax_amount")
    @classmethod
    def validate_tax_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("Kwota podatku nie może być ujemna")
        return value


class AssetCashFlowPatch(BaseModel):
    date: date_type | None = None
    kind: AssetCashFlowKind | None = None
    category: str | None = Field(default=None, max_length=64)
    amount: Decimal | None = None
    tax_amount: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: date_type | None) -> date_type | None:
        if value is None:
            raise ValueError("Data przepływu jest wymagana")
        return value

    @field_validator("kind", mode="before")
    @classmethod
    def validate_kind(cls, value):
        if value is None:
            raise ValueError("Rodzaj przepływu jest wymagany")
        try:
            return AssetCashFlowKind(value)
        except (TypeError, ValueError):
            raise ValueError("Nieprawidłowy rodzaj przepływu pieniężnego") from None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            raise ValueError("Kwota przepływu jest wymagana")
        if value <= 0:
            raise ValueError("Kwota przepływu musi być większa od zera")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Waluta przepływu nie może być pusta")
        return value

    @field_validator("tax_amount")
    @classmethod
    def validate_tax_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("Kwota podatku nie może być ujemna")
        return value


class AssetCashFlowOut(BaseModel):
    id: int
    portfolio_id: int
    instrument_id: int
    date: date_type
    kind: AssetCashFlowKind
    category: str | None
    amount: Decimal
    tax_amount: Decimal
    currency: str
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
