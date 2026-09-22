from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass
class QuotePoint:
    date: date
    close: Decimal
    currency: str


class PriceAdapter(Protocol):
    def fetch_history(
        self, symbol: str, start: date, end: date, currency: str
    ) -> list[QuotePoint]: ...

    def fetch_last(self, symbol: str, currency: str) -> QuotePoint | None: ...
