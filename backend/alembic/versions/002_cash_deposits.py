"""store external cash deposits for portfolio returns

Revision ID: 002_cash_deposits
Revises: 001_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "002_cash_deposits"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cash_deposits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="PLN"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_cash_deposits_date", "cash_deposits", ["date"])


def downgrade() -> None:
    op.drop_index("ix_cash_deposits_date", table_name="cash_deposits")
    op.drop_table("cash_deposits")