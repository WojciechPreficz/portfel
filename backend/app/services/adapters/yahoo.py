from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import logging
import math
import threading
import time

import yfinance as yf

from app.services.adapters.base import QuotePoint
from app.services.symbol_aliases import YAHOO_SYMBOL_ALIASES

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 0.5
MINOR_CURRENCY_DIVISORS = {
    "GBp": ("GBP", Decimal("100")),
    "GBX": ("GBP", Decimal("100")),
    "ZAc": ("ZAR", Decimal("100")),
    "ILA": ("ILS", Decimal("100")),
}
DOWNLOAD_LOCK = threading.Lock()


class _YFinanceLogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())

    @property
    def rate_limit_message(self) -> str | None:
        for message in self.messages:
            lowered = message.lower()
            if (
                "ratelimit" in lowered
                or "rate limit" in lowered
                or "too many requests" in lowered
                or "429" in lowered
            ):
                return message
        return None


class YahooRateLimitError(RuntimeError):
    pass


class YahooAdapter:
    def _with_rate_limit_retry(self, operation):
        for attempt in range(MAX_ATTEMPTS):
            try:
                return operation()
            except Exception as exc:
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
                retryable = (
                    status_code == 429
                    or "ratelimit" in type(exc).__name__.lower()
                    or "too many requests" in str(exc).lower()
                    or "429" in str(exc)
                )
                if not retryable or attempt + 1 == MAX_ATTEMPTS:
                    raise
                time.sleep(RETRY_DELAY_SECONDS * (2**attempt))

    @staticmethod
    def _canonical_symbol(symbol: str) -> str:
        return YAHOO_SYMBOL_ALIASES.get(symbol.upper(), symbol)

    @staticmethod
    def _frame_for_symbol(data, symbol: str, symbols: list[str]):
        columns = data.columns
        if getattr(columns, "nlevels", 1) > 1:
            first_level = list(columns.get_level_values(0))
            second_level = list(columns.get_level_values(1))
            if symbol in first_level:
                return data[symbol]
            if symbol in second_level:
                return data.xs(symbol, axis=1, level=1)
            if len(symbols) == 1:
                return data.xs(symbols[0], axis=1, level=0)
            return None
        return data if len(symbols) == 1 else None

    @staticmethod
    def _raw_currency(symbol: str, fallback: str) -> str:
        try:
            currency = YahooAdapter._with_currency_retry(symbol)
        except Exception:
            logger.warning("Yahoo currency lookup failed for %s; using stored currency %s", symbol, fallback, exc_info=True)
            return fallback
        return currency or fallback

    @staticmethod
    def _with_currency_retry(symbol: str) -> str | None:
        return YahooAdapter()._with_rate_limit_retry(
            lambda: yf.Ticker(symbol).fast_info.get("currency")
        )

    @staticmethod
    def _currency_and_divisor(raw_currency: str) -> tuple[str, Decimal]:
        if raw_currency in MINOR_CURRENCY_DIVISORS:
            return MINOR_CURRENCY_DIVISORS[raw_currency]
        return raw_currency.upper(), Decimal("1")

    def fetch_many(
        self, requests: dict[str, tuple[date, date, str]]
    ) -> dict[str, list[QuotePoint]]:
        points_by_symbol: dict[str, list[QuotePoint]] = {symbol: [] for symbol in requests}
        groups: dict[tuple[date, date], list[tuple[str, str, str]]] = defaultdict(list)
        for symbol, (start, end, currency) in requests.items():
            canonical = self._canonical_symbol(symbol)
            groups[(start, end)].append((symbol, canonical, currency))

        for (start, end), entries in groups.items():
            tickers = list(dict.fromkeys(canonical for _, canonical, _ in entries))
            data = self._with_rate_limit_retry(
                lambda: self._download(tickers, start, end)
            )
            if data is None or data.empty:
                continue

            currency_cache: dict[str, tuple[str, Decimal]] = {}
            for requested_symbol, canonical, fallback_currency in entries:
                frame = self._frame_for_symbol(data, canonical, tickers)
                if frame is None or "Close" not in frame:
                    continue
                if canonical not in currency_cache:
                    raw_currency = self._raw_currency(canonical, fallback_currency)
                    currency_cache[canonical] = self._currency_and_divisor(raw_currency)
                currency, divisor = currency_cache[canonical]
                series = frame["Close"]
                if getattr(series, "ndim", 1) > 1:
                    series = series.iloc[:, 0]
                for timestamp, raw_close in series.items():
                    if raw_close is None:
                        continue
                    try:
                        close = Decimal(str(raw_close))
                    except (InvalidOperation, ValueError):
                        continue
                    if not close.is_finite() or close <= 0 or not math.isfinite(float(close)):
                        continue
                    if isinstance(timestamp, datetime):
                        quote_date = timestamp.date()
                    elif isinstance(timestamp, date):
                        quote_date = timestamp
                    elif hasattr(timestamp, "date"):
                        quote_date = timestamp.date()
                    else:
                        quote_date = date.fromisoformat(str(timestamp)[:10])
                    points_by_symbol[requested_symbol].append(
                        QuotePoint(date=quote_date, close=close / divisor, currency=currency)
                    )

        for points in points_by_symbol.values():
            points.sort(key=lambda point: point.date)
        return points_by_symbol

    @staticmethod
    def _download(tickers: list[str], start: date, end: date):
        logger = yf.utils.get_yf_logger()
        capture = _YFinanceLogCapture()
        with DOWNLOAD_LOCK:
            logger.addHandler(capture)
            try:
                data = yf.download(
                    tickers=tickers,
                    start=start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    auto_adjust=False,
                    group_by="ticker",
                    progress=False,
                )
            finally:
                logger.removeHandler(capture)
        if message := capture.rate_limit_message:
            raise YahooRateLimitError(message)
        return data

    def fetch_history(
        self, symbol: str, start: date, end: date, currency: str
    ) -> list[QuotePoint]:
        return self.fetch_many({symbol: (start, end, currency)}).get(symbol, [])

    def fetch_last(self, symbol: str, currency: str) -> QuotePoint | None:
        end = date.today()
        start = end - timedelta(days=14)
        history = self.fetch_history(symbol, start, end, currency)
        return history[-1] if history else None
