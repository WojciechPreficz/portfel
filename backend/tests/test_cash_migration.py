from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_cash_movement_migration_preserves_existing_data_and_downgrades(tmp_path):
    import app.config

    backend_dir = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{(tmp_path / 'migration.sqlite').as_posix()}"
    config = Config(str(backend_dir / "alembic.ini"))
    with patch.object(app.config, "DATABASE_URL", database_url):
        command.upgrade(config, "004_real_estate")
        engine = create_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO cash_deposits (portfolio_id, date, amount, currency) VALUES (1, '2024-01-01', 100, 'PLN')"))
            command.upgrade(config, "005_cash_movements")
            assert "cash_movements" in inspect(engine).get_table_names()
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO cash_movements (portfolio_id, date, amount, currency, kind) VALUES (1, '2024-01-02', 15, 'PLN', 'dividend')"))
                assert connection.scalar(text("SELECT amount FROM cash_deposits")) == 100
            command.downgrade(config, "004_real_estate")
            assert "cash_movements" not in inspect(engine).get_table_names()
            assert "asset_cash_flows" in inspect(engine).get_table_names()
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT amount FROM cash_deposits")) == 100
        finally:
            engine.dispose()
