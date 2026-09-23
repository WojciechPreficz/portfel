from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from app.services.adapters.base import QuotePoint


YAHOO_SYMBOL_ALIASES = {
    "MEUD.FR": "MEUD.MI",
}


class YahooAdapter:
    def fetch_history(
        self, symbol: str, start: date, end: date, currency: str
    ) -> list[QuotePoint]:
        symbol = YAHOO_SYMBOL_ALIASES.get(symbol.upper(), symbol)
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
        meta = chart.get("meta", {})
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
        market_price = meta.get("regularMarketPrice")
        market_timestamp = meta.get("regularMarketTime")
        if market_price is not None and market_timestamp is not None:
            market_date = date.fromtimestamp(market_timestamp)
            if start <= market_date <= end:
                market_point = QuotePoint(
                    date=market_date,
                    close=Decimal(str(round(float(market_price), 8))),
                    currency=currency,
                )
                points = [point for point in points if point.date != market_date]
                points.append(market_point)
                points.sort(key=lambda point: point.date)
        return points

    def fetch_last(self, symbol: str, currency: str) -> QuotePoint | None:
        end = date.today()
        start = end - timedelta(days=14)
        history = self.fetch_history(symbol, start, end, currency)
        return history[-1] if history else None
