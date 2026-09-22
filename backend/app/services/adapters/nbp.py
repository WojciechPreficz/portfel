from datetime import date, timedelta
from decimal import Decimal

import httpx

from app.services.adapters.base import QuotePoint

NBP_GOLD = "https://api.nbp.pl/api/cenyzlota"
NBP_FX = "https://api.nbp.pl/api/exchangerates/rates/a"
HEADERS = {"Accept": "application/json"}


def _daterange_chunks(start: date, end: date, max_days: int = 365):
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max_days - 1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


class NbpAdapter:
    def fetch_history(
        self, symbol: str, start: date, end: date, currency: str
    ) -> list[QuotePoint]:
        del symbol
        points: list[QuotePoint] = []
        with httpx.Client(timeout=10.0, headers=HEADERS) as client:
            for chunk_start, chunk_end in _daterange_chunks(start, end):
                url = f"{NBP_GOLD}/{chunk_start.isoformat()}/{chunk_end.isoformat()}/"
                response = client.get(url, params={"format": "json"})
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                for row in response.json():
                    points.append(
                        QuotePoint(
                            date=date.fromisoformat(row["data"]),
                            close=Decimal(str(row["cena"])),
                            currency=currency or "PLN",
                        )
                    )
        return points

    def fetch_last(self, symbol: str, currency: str) -> QuotePoint | None:
        del symbol
        with httpx.Client(timeout=15.0, headers=HEADERS) as client:
            response = client.get(f"{NBP_GOLD}/today", params={"format": "json"})
            if response.status_code == 404:
                response = client.get(f"{NBP_GOLD}", params={"format": "json"})
            response.raise_for_status()
            payload = response.json()
            row = payload[0] if isinstance(payload, list) else payload
            return QuotePoint(
                date=date.fromisoformat(row["data"]),
                close=Decimal(str(row["cena"])),
                currency=currency or "PLN",
            )


def fetch_fx_history(code: str, start: date, end: date) -> list[tuple[date, Decimal]]:
    rows: list[tuple[date, Decimal]] = []
    with httpx.Client(timeout=10.0, headers=HEADERS) as client:
        for chunk_start, chunk_end in _daterange_chunks(start, end):
            url = f"{NBP_FX}/{code.lower()}/{chunk_start.isoformat()}/{chunk_end.isoformat()}/"
            response = client.get(url, params={"format": "json"})
            if response.status_code == 404:
                continue
            response.raise_for_status()
            data = response.json()
            for rate in data.get("rates", []):
                rows.append(
                    (
                        date.fromisoformat(rate["effectiveDate"]),
                        Decimal(str(rate["mid"])),
                    )
                )
    return rows
