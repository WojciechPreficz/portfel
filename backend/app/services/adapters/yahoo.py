from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from app.services.adapters.base import QuotePoint


class YahooAdapter:
    def fetch_history(
        self, symbol: str, start: date, end: date, currency: str
    ) -> list[QuotePoint]:
        period_start = int(datetime.combine(start, datetime.min.time(), timezone.utc).timestamp())
        period_end = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        response = httpx.get(
            url,
            params={
                "period1": period_start,
                "period2": period_end,
                "interval": "1d",
                "events": "history",
                "includeAdjustedClose": "true",
            },
            timeout=10.0,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        result = response.json().get("chart", {}).get("result")
        if not result:
            return []

        chart = result[0]
        timestamps = chart.get("timestamp", [])
        closes = chart.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
        points: list[QuotePoint] = []
        for timestamp, close in zip(timestamps, closes):
            if close is None:
                continue
            points.append(
                QuotePoint(
                    date=date.fromtimestamp(timestamp),
                    close=Decimal(str(round(float(close), 8))),
                    currency=currency,
                )
            )
        return points

    def fetch_last(self, symbol: str, currency: str) -> QuotePoint | None:
        end = date.today()
        start = end - timedelta(days=14)
        history = self.fetch_history(symbol, start, end, currency)
        return history[-1] if history else None
