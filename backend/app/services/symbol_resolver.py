from dataclasses import dataclass
import logging
import re

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Instrument
from app.seed import GPW_STOCK_TICKERS
from app.services.symbol_aliases import (
    BOSSA_NAME_ALIASES,
    STOOQ_SYMBOL_ALIASES,
    XSTATION_SUFFIX_CURRENCIES,
    XSTATION_TO_YAHOO_SUFFIX,
    YAHOO_SUFFIX_TO_XSTATION,
    YAHOO_SYMBOL_ALIASES,
)

logger = logging.getLogger(__name__)
POLISH_MARKET_TICKERS = set(GPW_STOCK_TICKERS) | {"NEU"}


@dataclass(frozen=True)
class ResolvedInstrument:
    ticker: str
    type: str
    provider: str
    symbol: str
    currency: str
    exchange: str
    instrument_id: int | None = None


@dataclass(frozen=True)
class ResolutionError:
    message: str


def normalise_ticker(raw_ticker: str | None) -> str | None:
    if not raw_ticker:
        return None
    ticker = raw_ticker.strip().upper()
    suffixes = sorted(
        {f".{suffix}" for suffix in XSTATION_TO_YAHOO_SUFFIX}
        | set(YAHOO_SUFFIX_TO_XSTATION),
        key=len,
        reverse=True,
    )
    for ending in suffixes:
        if ticker.endswith(ending):
            return ticker[: -len(ending)]
    return ticker or None


def _exchange_suffix(raw_ticker: str) -> str | None:
    raw = raw_ticker.strip().upper()
    for suffix in XSTATION_TO_YAHOO_SUFFIX:
        if raw.endswith(f".{suffix}"):
            return suffix
    for suffix, xstation_suffix in YAHOO_SUFFIX_TO_XSTATION.items():
        if raw.endswith(suffix):
            return xstation_suffix
    return None


def _currency_code(currency: str | None) -> str | None:
    if not currency:
        return None
    code = currency.strip()
    if code in {"GBp", "GBX"}:
        return "GBP"
    if code == "ZAc":
        return "ZAR"
    if code == "ILA":
        return "ILS"
    return code.upper()


def _search_by_isin(isin: str) -> dict | None:
    try:
        results = yf.Search(
            isin,
            max_results=10,
            news_count=0,
            lists_count=0,
            include_cb=False,
        ).quotes
    except Exception:
        logger.warning("Yahoo search failed for ISIN %s; trying exchange-symbol resolution", isin, exc_info=True)
        return None
    return next(
        (
            quote
            for quote in results
            if quote.get("symbol") and quote.get("quoteType") in {"EQUITY", "ETF", "MUTUALFUND"}
        ),
        None,
    )


def _fast_currency(symbol: str) -> str | None:
    try:
        currency = yf.Ticker(symbol).fast_info.get("currency")
    except Exception:
        logger.warning("Yahoo currency lookup failed for %s", symbol, exc_info=True)
        return None
    return _currency_code(currency)


def _exchange_details(
    raw_ticker: str | None,
    quote: dict | None,
) -> tuple[str, str, str, str, str]:
    raw = (raw_ticker or "").strip().upper()
    ticker = normalise_ticker(raw) or ""
    suffix = _exchange_suffix(raw)
    quote_symbol = (quote or {}).get("symbol")

    if suffix == "PL":
        quote_type = (quote or {}).get("quoteType")
        return (
            ticker,
            "WSE",
            "etf" if quote_type in {"ETF", "MUTUALFUND"} else "stock_pl",
            "stooq",
            STOOQ_SYMBOL_ALIASES.get(ticker, ticker.lower()),
        )

    exchange = str((quote or {}).get("exchange") or (quote or {}).get("exchDisp") or "")
    quote_type = (quote or {}).get("quoteType")
    if exchange.upper() in {"WSE", "WAR"}:
        if not ticker and quote_symbol:
            ticker = normalise_ticker(quote_symbol) or quote_symbol.split(".", 1)[0]
        return (
            ticker,
            "WSE",
            "etf" if quote_type in {"ETF", "MUTUALFUND"} else "stock_pl",
            "stooq",
            STOOQ_SYMBOL_ALIASES.get(ticker, ticker.lower()),
        )

    if quote_symbol:
        symbol = YAHOO_SYMBOL_ALIASES.get(quote_symbol.upper(), quote_symbol)
    elif suffix:
        symbol = YAHOO_SYMBOL_ALIASES.get(
            raw, f"{ticker}{XSTATION_TO_YAHOO_SUFFIX[suffix]}"
        )
        symbol = YAHOO_SYMBOL_ALIASES.get(symbol.upper(), symbol)
    else:
        return ticker, "", "", "", ""

    if quote_type in {"ETF", "MUTUALFUND"}:
        instrument_type = "etf"
    elif suffix == "US" or exchange.upper() in {
        "NMS", "NGM", "NCM", "NAS", "NYQ", "NYS", "ASE", "PCX",
    }:
        instrument_type = "stock_us_nyse" if exchange.upper() in {"NYQ", "NYS"} else "stock_us"
    else:
        instrument_type = "stock_intl"
    if suffix:
        exchange = exchange or suffix
    if not ticker and quote_symbol:
        ticker = normalise_ticker(quote_symbol) or quote_symbol.split(".", 1)[0]
    return ticker, exchange, instrument_type, "yahoo", symbol


def _existing_resolution(instrument: Instrument) -> ResolvedInstrument:
    return ResolvedInstrument(
        ticker=instrument.ticker,
        type=instrument.type,
        provider=instrument.provider,
        symbol=instrument.symbol,
        currency=instrument.currency,
        exchange="",
        instrument_id=instrument.id,
    )


def resolve(
    db: Session,
    raw_ticker: str | None,
    isin: str | None,
    name: str | None,
    category: str | None,
    currency_hint: str | None,
) -> ResolvedInstrument | ResolutionError:
    if isin:
        existing = db.scalar(
            select(Instrument)
            .where(Instrument.isin == isin.strip().upper())
            .order_by(Instrument.id)
            .limit(1)
        )
        if existing:
            return _existing_resolution(existing)

    quote = _search_by_isin(isin.strip().upper()) if isin else None
    ticker, exchange, instrument_type, provider, symbol = _exchange_details(raw_ticker, quote)
    if (
        not instrument_type
        and ticker in POLISH_MARKET_TICKERS
    ):
        exchange = "WSE"
        instrument_type = "etf" if category == "etf" else "stock_pl"
        provider = "stooq"
        symbol = STOOQ_SYMBOL_ALIASES.get(ticker, ticker.lower())
    if quote is None and category == "etf" and ticker:
        raw = (raw_ticker or "").strip().upper()
        suffix = _exchange_suffix(raw)
        if suffix:
            exchange = suffix
            instrument_type = "etf"
            if suffix == "PL":
                provider = "stooq"
                symbol = STOOQ_SYMBOL_ALIASES.get(ticker, ticker.lower())
            else:
                provider = "yahoo"
                symbol = YAHOO_SYMBOL_ALIASES.get(
                    raw, f"{ticker}{XSTATION_TO_YAHOO_SUFFIX[suffix]}"
                )
                symbol = YAHOO_SYMBOL_ALIASES.get(symbol.upper(), symbol)

    if not instrument_type:
        if ticker:
            candidates = list(
                db.scalars(
                    select(Instrument).where(Instrument.ticker == ticker).order_by(Instrument.id)
                ).all()
            )
            if len(candidates) == 1:
                return _existing_resolution(candidates[0])
        label = raw_ticker or isin or name or "instrument"
        return ResolutionError(f"Nie można rozpoznać giełdy ani typu instrumentu: {label}")

    existing = db.scalar(
        select(Instrument)
        .where(
            Instrument.ticker == ticker,
            Instrument.provider == provider,
            Instrument.symbol == symbol,
        )
        .order_by(Instrument.id)
        .limit(1)
    )
    if existing:
        return _existing_resolution(existing)

    suffix = _exchange_suffix((raw_ticker or "").strip().upper())
    currency = "PLN" if provider == "stooq" else _fast_currency(symbol)
    if currency is None and suffix:
        currency = XSTATION_SUFFIX_CURRENCIES.get(suffix)
    if currency is None:
        currency = _currency_code(currency_hint)
    if currency is None:
        return ResolutionError(f"Nie udało się ustalić waluty notowania dla {ticker or raw_ticker or isin}")

    return ResolvedInstrument(
        ticker=ticker,
        type=instrument_type,
        provider=provider,
        symbol=symbol,
        currency=currency,
        exchange=exchange,
    )


def bossa_alias(name: str) -> dict | None:
    normalized = name.strip().lower()
    for source, target in (
        ("ł", "l"), ("ą", "a"), ("ę", "e"), ("ó", "o"),
        ("ś", "s"), ("ź", "z"), ("ż", "z"), ("ć", "c"), ("ń", "n"),
    ):
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return BOSSA_NAME_ALIASES.get(normalized)
