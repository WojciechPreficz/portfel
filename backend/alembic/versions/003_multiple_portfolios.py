"""add independent portfolios

Revision ID: 003_multiple_portfolios
Revises: 002_cash_deposits
"""

from alembic import op
import sqlalchemy as sa


revision = "003_multiple_portfolios"
down_revision = "002_cash_deposits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.execute("INSERT INTO portfolios (name) VALUES ('Portfel główny')")
    portfolio_id = op.get_bind().execute(sa.text("SELECT id FROM portfolios LIMIT 1")).scalar_one()
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("portfolio_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_transactions_portfolio_id_portfolios", "portfolios", ["portfolio_id"], ["id"]
        )
        batch_op.create_index("ix_transactions_portfolio_id", ["portfolio_id"])
    with op.batch_alter_table("cash_deposits") as batch_op:
        batch_op.add_column(sa.Column("portfolio_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_cash_deposits_portfolio_id_portfolios", "portfolios", ["portfolio_id"], ["id"]
        )
        batch_op.create_index("ix_cash_deposits_portfolio_id", ["portfolio_id"])
    op.execute(sa.text("UPDATE transactions SET portfolio_id = :portfolio_id").bindparams(portfolio_id=portfolio_id))
    op.execute(sa.text("UPDATE cash_deposits SET portfolio_id = :portfolio_id").bindparams(portfolio_id=portfolio_id))


def downgrade() -> None:
    with op.batch_alter_table("cash_deposits") as batch_op:
        batch_op.drop_index("ix_cash_deposits_portfolio_id")
        batch_op.drop_constraint("fk_cash_deposits_portfolio_id_portfolios", type_="foreignkey")
        batch_op.drop_column("portfolio_id")
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index("ix_transactions_portfolio_id")
        batch_op.drop_constraint("fk_transactions_portfolio_id_portfolios", type_="foreignkey")
        batch_op.drop_column("portfolio_id")
    op.drop_table("portfolios")