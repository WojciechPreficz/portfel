from datetime import date as date_type, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InstrumentType(str, Enum):
    stock_pl = "stock_pl"
    stock_us = "stock_us"
    stock_us_nyse = "stock_us_nyse"
    etf = "etf"
    gold = "gold"
    real_estate = "real_estate"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="portfolio")
    deposits: Mapped[list["CashDeposit"]] = relationship(back_populates="portfolio")
    asset_cash_flows: Mapped[list["AssetCashFlow"]] = relationship(back_populates="portfolio")


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    isin: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))
    provider: Mapped[str] = mapped_column(String(16))
    symbol: Mapped[str] = mapped_column(String(32))
    unit: Mapped[str] = mapped_column(String(16), default="share")

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="instrument")
    prices: Mapped[list["Price"]] = relationship(back_populates="instrument")
    property_details: Mapped["PropertyDetails | None"] = relationship(back_populates="instrument")
    asset_cash_flows: Mapped[list["AssetCashFlow"]] = relationship(back_populates="instrument")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    type: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    purchase_price_pln: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    date: Mapped[date_type] = mapped_column(Date, index=True)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    instrument: Mapped[Instrument] = relationship(back_populates="transactions")
    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")


class CashDeposit(Base):
    __tablename__ = "cash_deposits"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    currency: Mapped[str] = mapped_column(String(3), default="PLN")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    portfolio: Mapped[Portfolio] = relationship(back_populates="deposits")


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("instrument_id", "date", name="uq_price_instrument_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    currency: Mapped[str] = mapped_column(String(3))

    instrument: Mapped[Instrument] = relationship(back_populates="prices")


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("pair", "date", name="uq_fx_pair_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pair: Mapped[str] = mapped_column(String(8), index=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))


class PropertyDetails(Base):
    __tablename__ = "property_details"

    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rental_tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.085"))
    interpolate_valuations: Mapped[bool] = mapped_column(default=False)

    instrument: Mapped[Instrument] = relationship(back_populates="property_details")


class AssetCashFlow(Base):
    __tablename__ = "asset_cash_flows"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_asset_cash_flows_amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="PLN")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    portfolio: Mapped[Portfolio] = relationship(back_populates="asset_cash_flows")
    instrument: Mapped[Instrument] = relationship(back_populates="asset_cash_flows")
