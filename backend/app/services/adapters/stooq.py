import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO

import httpx

from app.services.adapters.base import QuotePoint

STOOQ_URL = "https://stooq.pl/q/d/l/"


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
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(STOOQ_URL, params=params)
            response.raise_for_status()
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
