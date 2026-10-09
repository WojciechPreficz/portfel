"""add broker income, taxes and interest cash movements

Revision ID: 005_cash_movements
Revises: 004_real_estate
"""

from alembic import op
import sqlalchemy as sa

revision = "005_cash_movements"
down_revision = "004_real_estate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cash_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
    )
    op.create_index("ix_cash_movements_portfolio_id", "cash_movements", ["portfolio_id"])
    op.create_index("ix_cash_movements_date", "cash_movements", ["date"])


def downgrade() -> None:
    op.drop_index("ix_cash_movements_date", table_name="cash_movements")
    op.drop_index("ix_cash_movements_portfolio_id", table_name="cash_movements")
    op.drop_table("cash_movements")
