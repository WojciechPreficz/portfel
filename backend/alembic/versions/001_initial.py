"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("isin", sa.String(16), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False, server_default="share"),
    )
    op.create_index("ix_instruments_ticker", "instruments", ["ticker"])
    op.create_index("ix_instruments_isin", "instruments", ["isin"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("type", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 8), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("commission", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_transactions_instrument_id", "transactions", ["instrument_id"])
    op.create_index("ix_transactions_date", "transactions", ["date"])

    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("close", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.UniqueConstraint("instrument_id", "date", name="uq_price_instrument_date"),
    )
    op.create_index("ix_prices_instrument_id", "prices", ["instrument_id"])
    op.create_index("ix_prices_date", "prices", ["date"])

    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pair", sa.String(8), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.UniqueConstraint("pair", "date", name="uq_fx_pair_date"),
    )
    op.create_index("ix_fx_rates_pair", "fx_rates", ["pair"])
    op.create_index("ix_fx_rates_date", "fx_rates", ["date"])


def downgrade() -> None:
    op.drop_table("fx_rates")
    op.drop_table("prices")
    op.drop_table("transactions")
    op.drop_table("instruments")
