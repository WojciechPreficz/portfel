from datetime import date
from decimal import Decimal
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Instrument, Portfolio, Price, Transaction
from app.routers.quotes import router
from app.services.adapters import stooq, yahoo
from app.services.adapters.base import QuotePoint
from app.services.quotes import _fetch_history, refresh_quotes


@pytest.fixture(autouse=True)
def reset_provider_state(monkeypatch):
    monkeypatch.setattr(stooq, "_unavailable_until", 0.0)
    monkeypatch.setattr(stooq, "_probe_in_flight", False)
    monkeypatch.setattr(yahoo, "CURRENCY_CACHE", yahoo.OrderedDict())


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Portfolio(id=1, name="Test"))
        for instrument_id, ticker, provider, currency, kind in [
            (1, "ACC", "stooq", "PLN", "stock_pl"),
            (2, "BBB", "stooq", "PLN", "stock_pl"),
            (3, "XYZ", "yahoo", "USD", "stock_us"),
        ]:
            session.add(Instrument(id=instrument_id, ticker=ticker, name=ticker,
                                   symbol=ticker, provider=provider, currency=currency, type=kind))
            session.add(Transaction(portfolio_id=1, instrument_id=instrument_id,
                                    date=date.today(), type="BUY", quantity=Decimal("1"),
                                    price=Decimal("10"), currency="PLN", commission=Decimal("0")))
        session.commit()
        yield session
    engine.dispose()


def point(close="12", currency="PLN"):
    return QuotePoint(date=date.today(), close=Decimal(close), currency=currency)


def test_refresh_batches_polish_and_foreign_symbols_without_touching_stooq(db, monkeypatch):
    batch = Mock(return_value={"ACC.WA": [point()], "BBB.WA": [point()], "XYZ": [point(currency="USD")]})
    adapter = Mock(side_effect=AssertionError("Stooq must not run when Yahoo has all quotes"))
    monkeypatch.setattr(yahoo.YahooAdapter, "fetch_many", batch)
    monkeypatch.setattr("app.services.quotes.get_adapter", adapter)
    monkeypatch.setattr("app.services.quotes.fetch_fx_history", lambda *_args: [])
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        response = client.post("/api/quotes/refresh")
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"instruments", "prices_upserted", "fx_upserted", "errors"}
    assert result["prices_upserted"] == 3
    assert result["errors"] == []
    batch.assert_called_once()
    assert set(batch.call_args.args[0]) == {"ACC.WA", "BBB.WA", "XYZ"}
    adapter.assert_not_called()


@pytest.mark.parametrize("failed_batch", [False, True])
def test_stooq_fills_only_missing_polish_quotes_or_failed_polish_batch(db, monkeypatch, failed_batch):
    batch = Mock(side_effect=ValueError("Yahoo unavailable")) if failed_batch else Mock(
        return_value={"ACC.WA": [point()], "BBB.WA": [], "XYZ": [point(currency="USD")]},
    )
    backup = Mock(fetch_history=Mock(return_value=[point("15")]))
    monkeypatch.setattr(yahoo.YahooAdapter, "fetch_many", batch)
    monkeypatch.setattr("app.services.quotes.get_adapter", lambda _provider: backup)
    monkeypatch.setattr("app.services.quotes.fetch_fx_history", lambda *_args: [])
    result = refresh_quotes(db)
    requested = {call.args[0] for call in backup.fetch_history.call_args_list}
    assert requested == ({"ACC", "BBB"} if failed_batch else {"BBB"})
    assert result["errors"] == (["XYZ: Yahoo unavailable"] if failed_batch else [])
    assert len(db.scalars(select(Price)).all()) == (2 if failed_batch else 3)


def test_single_instrument_uses_stooq_when_yahoo_raises(monkeypatch):
    instrument = Mock(provider="stooq", type="stock_pl", ticker="ACC", symbol="acc", currency="PLN")
    monkeypatch.setattr(yahoo.YahooAdapter, "fetch_history", Mock(side_effect=ValueError("Yahoo unavailable")))
    backup = Mock(fetch_history=Mock(return_value=[point()]))
    monkeypatch.setattr("app.services.quotes.get_adapter", lambda _provider: backup)
    assert _fetch_history(instrument, date.today(), date.today()) == [point()]
    backup.fetch_history.assert_called_once()


def test_failed_fallback_reports_one_error_and_keeps_existing_prices(db, monkeypatch):
    db.add(Price(instrument_id=2, date=date.today(), close=Decimal("11"), currency="PLN"))
    db.commit()
    monkeypatch.setattr(yahoo.YahooAdapter, "fetch_many", Mock(return_value={
        "ACC.WA": [point()], "BBB.WA": [], "XYZ": [point(currency="USD")],
    }))
    backup = Mock(fetch_history=Mock(side_effect=httpx.ConnectTimeout("offline")))
    monkeypatch.setattr("app.services.quotes.get_adapter", lambda _provider: backup)
    monkeypatch.setattr("app.services.quotes.fetch_fx_history", lambda *_args: [])
    result = refresh_quotes(db)
    assert result["errors"] == ["BBB: offline"]
    assert db.scalar(select(Price.close).where(Price.instrument_id == 2)) == Decimal("11")


def test_currency_cache_preserves_minor_units_across_refreshes_and_expires(monkeypatch):
    lookup = Mock(side_effect=["GBp", "USD"])
    monkeypatch.setattr(yahoo.YahooAdapter, "_with_currency_retry", lookup)
    monkeypatch.setattr(yahoo.yf, "download", lambda **_kwargs: pd.DataFrame(
        {"Close": [102.4]}, index=pd.to_datetime([date.today()]),
    ))
    clock = [100.0]
    monkeypatch.setattr(yahoo, "monotonic", lambda: clock[0])
    for _ in range(2):
        points = yahoo.YahooAdapter().fetch_history("VOD.L", date.today(), date.today(), "GBP")
        assert points[0].close == Decimal("1.024")
        assert points[0].currency == "GBP"
    lookup.assert_called_once()
    clock[0] += yahoo.CURRENCY_CACHE_TTL_SECONDS + 1
    points = yahoo.YahooAdapter().fetch_history("VOD.L", date.today(), date.today(), "GBP")
    assert points[0].close == Decimal("102.4")
    assert points[0].currency == "USD"
    assert lookup.call_count == 2


def test_currency_errors_are_not_cached_and_aliases_share_successful_lookup(monkeypatch):
    lookup = Mock(side_effect=[ValueError("offline"), "EUR"])
    monkeypatch.setattr(yahoo.YahooAdapter, "_with_currency_retry", lookup)
    assert yahoo.YahooAdapter._raw_currency("MEUD.FR", "USD") == "USD"
    assert yahoo.YahooAdapter._raw_currency("MEUD.MI", "USD") == "EUR"
    assert yahoo.YahooAdapter._raw_currency("MEUD.FR", "USD") == "EUR"
    assert lookup.call_count == 2


def test_currency_cache_has_bounded_size(monkeypatch):
    monkeypatch.setattr(yahoo, "MAX_CACHED_CURRENCIES", 2)
    monkeypatch.setattr(yahoo.YahooAdapter, "_with_currency_retry", lambda _symbol: "USD")
    for symbol in ("ONE", "TWO", "THREE"):
        yahoo.YahooAdapter._raw_currency(symbol, "USD")
    assert list(yahoo.CURRENCY_CACHE) == ["TWO", "THREE"]


def stooq_client(monkeypatch):
    response = httpx.Response(200, text="Date,Close\n2026-09-03,10.5\n",
                              request=httpx.Request("GET", stooq.STOOQ_URL))
    client = Mock()
    client.get.return_value = response
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=client)
    factory.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(stooq.httpx, "Client", factory)
    return client, factory


@pytest.mark.parametrize("failure", ["timeout", "429", "503"])
def test_stooq_outage_skips_requests_then_allows_one_recovery_probe(monkeypatch, failure):
    client, factory = stooq_client(monkeypatch)
    clock = [100.0]
    monkeypatch.setattr(stooq, "monotonic", lambda: clock[0])
    if failure == "timeout":
        error = httpx.ConnectTimeout("offline")
    else:
        response = httpx.Response(int(failure), request=httpx.Request("GET", stooq.STOOQ_URL))
        error = httpx.HTTPStatusError("unavailable", request=response.request, response=response)
    client.get.side_effect = error
    adapter = stooq.StooqAdapter()
    with pytest.raises(type(error)):
        adapter.fetch_history("test", date(2026, 9, 1), date(2026, 9, 5), "PLN")
    with pytest.raises(stooq.StooqUnavailableError):
        stooq.StooqAdapter().fetch_history("test2", date(2026, 9, 1), date(2026, 9, 5), "PLN")
    factory.assert_called_once()
    assert factory.call_args.kwargs["timeout"].connect == 2.0
    assert factory.call_args.kwargs["timeout"].read == 3.0
    clock[0] += stooq.STOOQ_COOLDOWN_SECONDS + 1
    probe = stooq._begin_request()
    assert probe is True
    with pytest.raises(stooq.StooqUnavailableError):
        stooq._begin_request()
    stooq._finish_request(probe)
    client.get.side_effect = None
    assert adapter.fetch_history("test", date(2026, 9, 1), date(2026, 9, 5), "PLN")[0].close == Decimal("10.5")


def test_unknown_stooq_symbol_does_not_disable_provider(monkeypatch):
    client, factory = stooq_client(monkeypatch)
    response = httpx.Response(404, request=httpx.Request("GET", stooq.STOOQ_URL))
    client.get.return_value = response
    for _ in range(2):
        with pytest.raises(httpx.HTTPStatusError):
            stooq.StooqAdapter().fetch_history("missing", date.today(), date.today(), "PLN")
    assert factory.call_count == 2


def test_successful_in_flight_request_does_not_cancel_an_outage(monkeypatch):
    assert stooq._begin_request() is False
    assert stooq._begin_request() is False
    stooq._finish_request(False, httpx.ConnectTimeout("offline"))
    stooq._finish_request(False)
    with pytest.raises(stooq.StooqUnavailableError):
        stooq._begin_request()
