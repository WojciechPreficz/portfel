"""add real estate details and asset cash flows

Revision ID: 004_real_estate
Revises: 003_multiple_portfolios
"""

from alembic import op
import sqlalchemy as sa


revision = "004_real_estate"
down_revision = "003_multiple_portfolios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "property_details",
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("area_m2", sa.Numeric(10, 2), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("rental_tax_rate", sa.Numeric(5, 4), server_default="0.085", nullable=False),
        sa.Column("interpolate_valuations", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("instrument_id"),
    )
    op.create_table(
        "asset_cash_flows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("currency", sa.String(3), server_default="PLN", nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_asset_cash_flows_amount_positive"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asset_cash_flows_portfolio_id", "asset_cash_flows", ["portfolio_id"])
    op.create_index("ix_asset_cash_flows_instrument_id", "asset_cash_flows", ["instrument_id"])
    op.create_index("ix_asset_cash_flows_date", "asset_cash_flows", ["date"])


def downgrade() -> None:
    op.drop_index("ix_asset_cash_flows_date", table_name="asset_cash_flows")
    op.drop_index("ix_asset_cash_flows_instrument_id", table_name="asset_cash_flows")
    op.drop_index("ix_asset_cash_flows_portfolio_id", table_name="asset_cash_flows")
    op.drop_table("asset_cash_flows")
    op.drop_table("property_details")
