import calendar
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    AssetCashFlow,
    CashDeposit,
    Instrument,
    Portfolio,
    Price,
    PropertyDetails,
    Transaction,
)
from app.routers.portfolio import delete_portfolio
from app.routers.real_estate import create_asset_cash_flow, create_real_estate
from app.schemas import AssetCashFlowCreate, RealEstateCreate
from app.services.adapters.base import QuotePoint
from app.services.portfolio import build_property_metrics, build_summary, price_on
from app.services.quotes import refresh_quotes


class RealEstateTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.portfolio = Portfolio(name="Nieruchomości")
        self.other_portfolio = Portfolio(name="Akcje")
        self.db.add_all([self.portfolio, self.other_portfolio])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _create_property(
        self,
        *,
        portfolio_id=None,
        purchase_date=None,
        purchase_price=Decimal("500000"),
        transaction_costs=Decimal("10000"),
        initial_valuation=None,
        rental_tax_rate=Decimal("0.085"),
        area_m2=Decimal("60"),
        name="Mieszkanie testowe",
    ):
        return create_real_estate(
            RealEstateCreate(
                portfolio_id=portfolio_id or self.portfolio.id,
                name=name,
                address="Warszawa",
                area_m2=area_m2,
                purchase_date=purchase_date or date.today() - timedelta(days=365),
                purchase_price=purchase_price,
                transaction_costs=transaction_costs,
                rental_tax_rate=rental_tax_rate,
                initial_valuation=initial_valuation,
            ),
            self.db,
        )

    def _add_cash_flow(
        self,
        instrument_id,
        on_date,
        kind,
        amount,
        *,
        tax_amount=Decimal("0"),
        category=None,
        portfolio_id=None,
    ):
        row = AssetCashFlow(
            portfolio_id=portfolio_id or self.portfolio.id,
            instrument_id=instrument_id,
            date=on_date,
            kind=kind,
            category=category,
            amount=amount,
            tax_amount=tax_amount,
            currency="PLN",
        )
        self.db.add(row)
        self.db.flush()
        return row

    @staticmethod
    def _expected_xirr(cash_flows):
        start = min(on_date for on_date, _amount in cash_flows)

        def npv(rate):
            return sum(
                float(amount) / (1 + rate) ** ((on_date - start).days / 365)
                for on_date, amount in cash_flows
            )

        lower, upper = -0.9999, 1.0
        low_value, high_value = npv(lower), npv(upper)
        while low_value * high_value > 0 and upper < 1_000_000:
            upper *= 2
            high_value = npv(upper)
        if low_value * high_value > 0:
            return None
        for _ in range(200):
            middle = (lower + upper) / 2
            middle_value = npv(middle)
            if abs(middle_value) < 1e-7:
                return middle
            if low_value * middle_value <= 0:
                upper, high_value = middle, middle_value
            else:
                lower, low_value = middle, middle_value
        return (lower + upper) / 2

    def test_create_endpoint_saves_instrument_details_buy_and_initial_valuation(self):
        purchase_date = date(2025, 3, 1)

        result = self._create_property(
            purchase_date=purchase_date,
            purchase_price=Decimal("500000"),
            transaction_costs=Decimal("12500"),
        )

        instrument = self.db.get(Instrument, result["id"])
        details = self.db.get(PropertyDetails, instrument.id)
        transaction = self.db.scalar(
            select(Transaction).where(Transaction.instrument_id == instrument.id)
        )
        price = self.db.scalar(select(Price).where(Price.instrument_id == instrument.id))
        self.assertEqual(instrument.type, "real_estate")
        self.assertEqual(instrument.provider, "manual")
        self.assertEqual(instrument.unit, "property")
        self.assertTrue(instrument.ticker.startswith("RE-mieszkanie-testo-"))
        self.assertEqual(details.area_m2, Decimal("60.00"))
        self.assertEqual(details.rental_tax_rate, Decimal("0.0850"))
        self.assertEqual(transaction.type, "BUY")
        self.assertEqual(transaction.quantity, Decimal("1.00000000"))
        self.assertEqual(transaction.price, Decimal("500000.00000000"))
        self.assertEqual(transaction.commission, Decimal("12500.00000000"))
        self.assertEqual(price.close, Decimal("500000.00000000"))
        self.assertEqual(price.date, purchase_date)

    def test_real_estate_migration_up_and_down_preserves_existing_rows(self):
        import app.config

        backend_dir = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "legacy.sqlite"
            database_url = f"sqlite:///{database_path.as_posix()}"
            config = Config(str(backend_dir / "alembic.ini"))
            with patch.object(app.config, "DATABASE_URL", database_url):
                command.upgrade(config, "003_multiple_portfolios")
                legacy_engine = create_engine(database_url)
                with legacy_engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO instruments "
                            "(ticker, isin, name, type, currency, provider, symbol, unit) "
                            "VALUES ('LEGACY', NULL, 'Legacy', 'stock_pl', 'PLN', 'stooq', 'legacy', 'share')"
                        )
                    )
                    connection.execute(
                        text(
                            "INSERT INTO transactions "
                            "(portfolio_id, instrument_id, type, quantity, price, currency, date, commission) "
                            "VALUES (1, 1, 'BUY', 1, 10, 'PLN', '2024-01-01', 0)"
                        )
                    )
                legacy_engine.dispose()

                command.upgrade(config, "head")
                upgraded_engine = create_engine(database_url)
                self.assertIn("property_details", inspect(upgraded_engine).get_table_names())
                self.assertIn("asset_cash_flows", inspect(upgraded_engine).get_table_names())
                command.downgrade(config, "-1")
                inspector = inspect(upgraded_engine)
                self.assertNotIn("property_details", inspector.get_table_names())
                self.assertNotIn("asset_cash_flows", inspector.get_table_names())
                with upgraded_engine.connect() as connection:
                    count = connection.scalar(text("SELECT COUNT(*) FROM transactions"))
                self.assertEqual(count, 1)
                upgraded_engine.dispose()

    @patch("app.services.quotes.fetch_fx_history", return_value=[])
    @patch(
        "app.services.quotes._fetch_history",
        return_value=[QuotePoint(date=date.today(), close=Decimal("31.10"), currency="PLN")],
    )
    def test_refresh_quotes_skips_properties_but_does_not_skip_manual_gold(
        self, _fetch_history, _fetch_fx
    ):
        property_data = self._create_property()
        gold = Instrument(
            ticker="XAU-9999",
            name="Złoto 999.9",
            type="gold",
            currency="PLN",
            provider="manual",
            symbol="XAU-9999",
            unit="gram",
        )
        self.db.add(gold)
        self.db.flush()
        self.db.add(
            Transaction(
                portfolio_id=self.portfolio.id,
                instrument_id=gold.id,
                type="BUY",
                quantity=Decimal("1"),
                price=Decimal("30"),
                currency="PLN",
                date=date.today() - timedelta(days=1),
                commission=Decimal("0"),
            )
        )
        self.db.commit()

        all_result = refresh_quotes(self.db)
        property_result = refresh_quotes(self.db, instrument_ids=[property_data["id"]])
        gold_result = refresh_quotes(self.db, instrument_ids=[gold.id])

        self.assertEqual(all_result["instruments"], 1)
        self.assertEqual(all_result["errors"], [])
        self.assertEqual(property_result["instruments"], 0)
        self.assertEqual(property_result["errors"], [])
        self.assertEqual(gold_result["instruments"], 1)
        self.assertEqual(gold_result["errors"], [])
        self.assertEqual(_fetch_history.call_count, 2)

    def test_manual_valuation_is_carried_forward_by_price_on(self):
        property_data = self._create_property(
            purchase_date=date(2024, 1, 1),
            initial_valuation=Decimal("500000"),
        )
        instrument_id = property_data["id"]
        valuation_date = date(2025, 6, 1)
        valuation = Price(
            instrument_id=instrument_id,
            date=valuation_date,
            close=Decimal("550000"),
            currency="PLN",
        )
        self.db.add(valuation)
        self.db.commit()

        carried = price_on(self.db, instrument_id, valuation_date + timedelta(days=20))

        self.assertEqual(carried.close, Decimal("550000.00000000"))
        self.assertEqual(carried.date, valuation_date)

    def test_capex_is_added_to_position_cost_and_offsets_equal_valuation_increase(self):
        property_data = self._create_property(
            purchase_date=date(2024, 1, 1),
            purchase_price=Decimal("500000"),
            transaction_costs=Decimal("0"),
        )
        instrument_id = property_data["id"]
        today = date.today()
        self._add_cash_flow(
            instrument_id,
            today,
            "CAPEX",
            Decimal("10000"),
            category="Remont",
        )
        self.db.add(
            Price(
                instrument_id=instrument_id,
                date=today,
                close=Decimal("510000"),
                currency="PLN",
            )
        )
        self.db.commit()

        position = build_summary(self.db, self.portfolio.id)["positions"][0]

        self.assertEqual(position["avg_cost"], Decimal("510000.00000000"))
        self.assertEqual(position["cost_pln"], Decimal("510000.00000000"))
        self.assertEqual(position["capex_pln"], Decimal("10000.00"))
        self.assertEqual(position["pnl_pln"], Decimal("0E-8"))

    def test_portfolio_xirr_includes_rent_tax_opex_and_current_valuation(self):
        purchase_date = date(2023, 1, 1)
        end_date = date(2024, 1, 1)
        property_data = self._create_property(
            purchase_date=purchase_date,
            purchase_price=Decimal("500000"),
            transaction_costs=Decimal("10000"),
            initial_valuation=Decimal("500000"),
        )
        instrument_id = property_data["id"]
        expected_flows = [(purchase_date, Decimal("-510000"))]
        for month in range(1, 13):
            rent_date = date(2023, month, calendar.monthrange(2023, month)[1])
            self._add_cash_flow(
                instrument_id,
                rent_date,
                "RENT",
                Decimal("3000"),
                tax_amount=Decimal("255"),
            )
            self._add_cash_flow(
                instrument_id,
                rent_date,
                "OPEX",
                Decimal("400"),
            )
            expected_flows.extend(
                [(rent_date, Decimal("2745")), (rent_date, Decimal("-400"))]
            )
        self.db.add(
            Price(
                instrument_id=instrument_id,
                date=end_date,
                close=Decimal("520000"),
                currency="PLN",
            )
        )
        self.db.commit()
        expected_flows.append((end_date, Decimal("520000")))

        actual = build_summary(self.db, self.portfolio.id)["xirr_pct"]
        expected = Decimal(str(self._expected_xirr(expected_flows))) * Decimal("100")

        self.assertLess(abs(actual - expected), Decimal("0.01"))

    def test_rent_tax_defaults_to_property_rate_but_explicit_zero_is_kept(self):
        property_data = self._create_property(rental_tax_rate=Decimal("0.125"))
        instrument_id = property_data["id"]

        defaulted = create_asset_cash_flow(
            instrument_id,
            AssetCashFlowCreate(
                portfolio_id=self.portfolio.id,
                date=date.today(),
                kind="RENT",
                amount=Decimal("3000"),
            ),
            self.db,
        )
        explicit_zero = create_asset_cash_flow(
            instrument_id,
            AssetCashFlowCreate(
                portfolio_id=self.portfolio.id,
                date=date.today(),
                kind="RENT",
                amount=Decimal("3000"),
                tax_amount=Decimal("0"),
            ),
            self.db,
        )

        self.assertEqual(defaulted.tax_amount, Decimal("375.00"))
        self.assertEqual(explicit_zero.tax_amount, Decimal("0.00"))

    def test_aggregate_keeps_deposit_based_stock_flows_and_adds_property_flows(self):
        start = date.today() - timedelta(days=365)
        property_data = self._create_property(
            purchase_date=start,
            purchase_price=Decimal("500000"),
            transaction_costs=Decimal("10000"),
            portfolio_id=self.portfolio.id,
        )
        property_id = property_data["id"]
        self._add_cash_flow(
            property_id,
            date.today() - timedelta(days=1),
            "RENT",
            Decimal("3000"),
            tax_amount=Decimal("255"),
        )
        stock = Instrument(
            ticker="AGG",
            name="Akcja testowa",
            type="stock_pl",
            currency="PLN",
            provider="stooq",
            symbol="agg",
            unit="share",
        )
        self.db.add(stock)
        self.db.flush()
        self.db.add_all(
            [
                Transaction(
                    portfolio_id=self.other_portfolio.id,
                    instrument_id=stock.id,
                    type="BUY",
                    quantity=Decimal("1"),
                    price=Decimal("100"),
                    currency="PLN",
                    date=start,
                    commission=Decimal("0"),
                ),
                CashDeposit(
                    portfolio_id=self.other_portfolio.id,
                    date=start,
                    amount=Decimal("100"),
                    currency="PLN",
                ),
                Price(
                    instrument_id=stock.id,
                    date=date.today(),
                    close=Decimal("110"),
                    currency="PLN",
                ),
                Price(
                    instrument_id=property_id,
                    date=date.today(),
                    close=Decimal("520000"),
                    currency="PLN",
                ),
            ]
        )
        self.db.commit()

        summary = build_summary(self.db)

        self.assertEqual(summary["value_pln"], Decimal("520110.00000000"))
        self.assertEqual(summary["income_pln"], Decimal("2745.00"))
        self.assertIsNotNone(summary["xirr_pct"])

    def test_property_metrics_calculate_full_year_gross_and_net_yield(self):
        start = date(2023, 1, 1)
        end = date(2023, 12, 31)
        property_data = self._create_property(
            purchase_date=start,
            purchase_price=Decimal("500000"),
            transaction_costs=Decimal("10000"),
            initial_valuation=Decimal("500000"),
        )
        instrument_id = property_data["id"]
        for month in range(12):
            month_number = month + 1
            rent_date = date(2023, month_number, calendar.monthrange(2023, month_number)[1])
            self._add_cash_flow(
                instrument_id,
                rent_date,
                "RENT",
                Decimal("3000"),
                tax_amount=Decimal("255"),
                category="Czynsz najmu",
            )
            self._add_cash_flow(
                instrument_id,
                rent_date,
                "OPEX",
                Decimal("400"),
                category="Czynsz administracyjny",
            )
        self.db.add(
            Price(
                instrument_id=instrument_id,
                date=end,
                close=Decimal("520000"),
                currency="PLN",
            )
        )
        self.db.commit()

        metrics = build_property_metrics(
            self.db, instrument_id, self.portfolio.id, start, end
        )

        expected_gross = Decimal("36000") / Decimal("510000") * Decimal("100")
        expected_net = Decimal("28140") / Decimal("510000") * Decimal("100")
        self.assertEqual(metrics["rent_gross_pln"], Decimal("36000.00"))
        self.assertEqual(metrics["tax_pln"], Decimal("3060.00"))
        self.assertEqual(metrics["opex_pln"], Decimal("4800.00"))
        self.assertEqual(metrics["purchase_cost_pln"], Decimal("510000.00000000"))
        self.assertAlmostEqual(float(metrics["gross_yield_pct"]), float(expected_gross), places=8)
        self.assertAlmostEqual(float(metrics["net_yield_pct"]), float(expected_net), places=8)
        self.assertEqual(len(metrics["cash_flows_by_category"]), 2)

    def test_deleting_portfolio_removes_property_flows_details_and_valuations(self):
        property_data = self._create_property()
        instrument_id = property_data["id"]
        self._add_cash_flow(
            instrument_id,
            date.today(),
            "RENT",
            Decimal("3000"),
            tax_amount=Decimal("255"),
        )
        self.db.commit()
        portfolio_id = self.portfolio.id

        result = delete_portfolio(portfolio_id, self.db)

        self.assertEqual(result["deleted_asset_cash_flows"], 1)
        self.assertEqual(result["deleted_property_details"], 1)
        self.assertIsNone(self.db.get(Portfolio, portfolio_id))
        self.assertIsNone(self.db.get(Instrument, instrument_id))
        self.assertIsNone(self.db.get(PropertyDetails, instrument_id))
        self.assertEqual(
            self.db.scalars(select(Price).where(Price.instrument_id == instrument_id)).all(),
            [],
        )
        self.assertEqual(
            self.db.scalars(
                select(AssetCashFlow).where(AssetCashFlow.portfolio_id == portfolio_id)
            ).all(),
            [],
        )


if __name__ == "__main__":
    unittest.main()
