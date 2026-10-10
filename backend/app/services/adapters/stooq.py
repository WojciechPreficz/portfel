import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from threading import Lock
from time import monotonic

import httpx

from app.services.adapters.base import QuotePoint

STOOQ_URL = "https://stooq.pl/q/d/l/"
STOOQ_TIMEOUT = httpx.Timeout(3.0, connect=2.0, pool=2.0)
STOOQ_COOLDOWN_SECONDS = 300
_availability_lock = Lock()
_unavailable_until = 0.0
_probe_in_flight = False


class StooqUnavailableError(RuntimeError):
    pass


def _begin_request() -> bool:
    global _probe_in_flight
    with _availability_lock:
        if _unavailable_until > monotonic():
            raise StooqUnavailableError("Stooq jest czasowo niedostępny; ponowna próba za kilka minut")
        if _unavailable_until:
            if _probe_in_flight:
                raise StooqUnavailableError("Trwa sprawdzanie dostępności Stooq")
            _probe_in_flight = True
            return True
        return False


def _finish_request(probe: bool, error: Exception | None = None):
    global _unavailable_until, _probe_in_flight
    unavailable = isinstance(error, httpx.TransportError) or (
        isinstance(error, httpx.HTTPStatusError)
        and (error.response.status_code == 429 or error.response.status_code >= 500)
    )
    with _availability_lock:
        if unavailable:
            _unavailable_until = monotonic() + STOOQ_COOLDOWN_SECONDS
        elif probe:
            _unavailable_until = 0.0
        if probe:
            _probe_in_flight = False


class StooqAdapter:
    def fetch_many(
        self, requests: dict[str, tuple[date, date, str]]
    ) -> dict[str, list[QuotePoint]]:
        return {
            symbol: self.fetch_history(symbol, start, end, currency)
            for symbol, (start, end, currency) in requests.items()
        }

    def fetch_history(
        self, symbol: str, start: date, end: date, currency: str
    ) -> list[QuotePoint]:
        params = {
            "s": symbol.lower(),
            "i": "d",
            "d1": start.strftime("%Y%m%d"),
            "d2": end.strftime("%Y%m%d"),
        }
        probe = _begin_request()
        try:
            with httpx.Client(timeout=STOOQ_TIMEOUT, follow_redirects=True, max_redirects=2) as client:
                response = client.get(STOOQ_URL, params=params)
                response.raise_for_status()
        except Exception as exc:
            _finish_request(probe, exc)
            raise
        _finish_request(probe)
        text = response.text.strip()
        if not text or text.startswith("No data"):
            return []
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames or "Date" not in reader.fieldnames:
            return []
        points: list[QuotePoint] = []
        for row in reader:
            raw_date = (row.get("Date") or "").strip()
            raw_close = (row.get("Close") or "").strip()
            if not raw_date or not raw_close:
                continue
            try:
                d = datetime.strptime(raw_date, "%Y-%m-%d").date()
                close = Decimal(raw_close)
            except (ValueError, ArithmeticError):
                continue
            if d < start or d > end:
                continue
            points.append(QuotePoint(date=d, close=close, currency=currency))
        return points

    def fetch_last(self, symbol: str, currency: str) -> QuotePoint | None:
        end = date.today()
        history = self.fetch_history(symbol, end - timedelta(days=14), end, currency)
        return history[-1] if history else None
