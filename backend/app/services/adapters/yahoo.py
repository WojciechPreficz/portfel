from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf

from app.services.adapters.base import QuotePoint


class YahooAdapter:
    def fetch_history(
        self, symbol: str, start: date, end: date, currency: str
    ) -> list[QuotePoint]:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=True,
        )
        if hist is None or hist.empty:
            return []
        points: list[QuotePoint] = []
        for idx, row in hist.iterrows():
            close = row.get("Close")
            if close is None or close != close:
                continue
            points.append(
                QuotePoint(
                    date=idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10]),
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
