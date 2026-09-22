from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Instrument

POLISH_MARKET_INSTRUMENTS = {
    "stock_pl": [
        {"ticker": "ALR", "name": "Allegro", "type": "stock_pl"},
        {"ticker": "BEN", "name": "Benefit Systems", "type": "stock_pl"},
        {"ticker": "BHW", "name": "Boryszew", "type": "stock_pl"},
        {"ticker": "CCC", "name": "CCC", "type": "stock_pl"},
        {"ticker": "CDR", "name": "CD Projekt", "type": "stock_pl"},
        {"ticker": "CIE", "name": "CIECH", "type": "stock_pl"},
        {"ticker": "DNP", "name": "Dino Polska", "type": "stock_pl"},
        {"ticker": "EAT", "name": "EATON", "type": "stock_pl"},
        {"ticker": "GTC", "name": "Grupa Azoty", "type": "stock_pl"},
        {"ticker": "JSW", "name": "JSW", "type": "stock_pl"},
        {"ticker": "KGH", "name": "KGHM Polska Miedź", "type": "stock_pl"},
        {"ticker": "LPP", "name": "LPP", "type": "stock_pl"},
        {"ticker": "MBK", "name": "mBank", "type": "stock_pl"},
        {"ticker": "MCR", "name": "MCR Capital", "type": "stock_pl"},
        {"ticker": "OAT", "name": "PGE Polska Grupa Energetyczna", "type": "stock_pl"},
        {"ticker": "ORB", "name": "Orange Polska", "type": "stock_pl"},
        {"ticker": "PGE", "name": "PGE Polska Grupa Energetyczna", "type": "stock_pl"},
        {"ticker": "PKN", "name": "PKN Orlen", "type": "stock_pl"},
        {"ticker": "PKO", "name": "PKO BP", "type": "stock_pl"},
        {"ticker": "PZU", "name": "PZU", "type": "stock_pl"},
        {"ticker": "SAN", "name": "Santander Bank Polska", "type": "stock_pl"},
        {"ticker": "TPE", "name": "TPE", "type": "stock_pl"},
        {"ticker": "PEO", "name": "PEKAO SA", "type": "stock_pl"},
        {"ticker": "AME", "name": "AmRest", "type": "stock_pl"},
        {"ticker": "ACP", "name": "Asseco Poland", "type": "stock_pl"},
        {"ticker": "AAT", "name": "AAT Holding", "type": "stock_pl"},
        {"ticker": "FTE", "name": "Forte", "type": "stock_pl"},
        {"ticker": "ING", "name": "ING Bank Śląski", "type": "stock_pl"},
        {"ticker": "MIL", "name": "Millenium", "type": "stock_pl"},
        {"ticker": "OPL", "name": "Orange Polska", "type": "stock_pl"},
        {"ticker": "PLW", "name": "Polenergia", "type": "stock_pl"},
        {"ticker": "BOS", "name": "BOSSA", "type": "stock_pl"},
        {"ticker": "BRS", "name": "BRS", "type": "stock_pl"},
        {"ticker": "MKT", "name": "MKT", "type": "stock_pl"},
        {"ticker": "QRS", "name": "QRS", "type": "stock_pl"},
        {"ticker": "ATC", "name": "ATC", "type": "stock_pl"},
        {"ticker": "NXT", "name": "Nexter", "type": "stock_pl"},
        {"ticker": "GKP", "name": "Grupa Kęty", "type": "stock_pl"},
        {"ticker": "KRK", "name": "Kruk", "type": "stock_pl"},
        {"ticker": "FSA", "name": "FSA", "type": "stock_pl"},
        {"ticker": "HEX", "name": "Hexagon", "type": "stock_pl"},
        {"ticker": "CDP", "name": "CDP", "type": "stock_pl"},
        {"ticker": "TMR", "name": "TMR", "type": "stock_pl"},
        {"ticker": "XTB", "name": "XTB", "type": "stock_pl"},
        {"ticker": "ZAB", "name": "Zabka", "type": "stock_pl"},
        {"ticker": "MVP", "name": "MVP", "type": "stock_pl"},
        {"ticker": "WSE", "name": "WSE", "type": "stock_pl"},
        {"ticker": "TES", "name": "Tesco Polska", "type": "stock_pl"},
        {"ticker": "R22", "name": "R22", "type": "stock_pl"},
        {"ticker": "BFT", "name": "BFT", "type": "stock_pl"},
        {"ticker": "GRA", "name": "GRA", "type": "stock_pl"},
        {"ticker": "VRC", "name": "VRC", "type": "stock_pl"},
    ],
    "etf": [
        {"ticker": "C6E", "isin": "LU0908500753", "name": "Amundi Core Stoxx Europe 600 UCITS ETF Acc EUR", "type": "etf", "currency": "EUR", "provider": "yahoo", "symbol": "C6E.DE", "unit": "share"},
        {"ticker": "V80A", "isin": "IE00BMVB5R75", "name": "Vanguard LifeStrategy 80% Equity UCITS ETF Acc EUR", "type": "etf", "currency": "EUR", "provider": "yahoo", "symbol": "V80A.DE", "unit": "share"},
        {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "type": "etf", "currency": "USD", "provider": "yahoo", "symbol": "SPY", "unit": "share"},
        {"ticker": "QQQ", "name": "Invesco NASDAQ 100 ETF", "type": "etf", "currency": "USD", "provider": "yahoo", "symbol": "QQQ", "unit": "share"},
        {"ticker": "IVV", "name": "iShares Core S&P 500 ETF", "type": "etf", "currency": "USD", "provider": "yahoo", "symbol": "IVV", "unit": "share"},
        {"ticker": "VGK", "name": "Vanguard FTSE Europe ETF", "type": "etf", "currency": "USD", "provider": "yahoo", "symbol": "VGK", "unit": "share"},
    ],
}

SEED = [
    *[
        {**item, "currency": "PLN", "provider": "stooq", "symbol": item["ticker"].lower(), "unit": "share"}
        for item in POLISH_MARKET_INSTRUMENTS["stock_pl"]
    ],
    *[
        {**item, "currency": item.get("currency", "EUR"), "provider": item.get("provider", "yahoo"), "symbol": item.get("symbol", item["ticker"]), "unit": item.get("unit", "share")}
        for item in POLISH_MARKET_INSTRUMENTS["etf"]
    ],
    {
        "ticker": "XAU",
        "isin": None,
        "name": "Złoto (NBP, PLN/g)",
        "type": "gold",
        "currency": "PLN",
        "provider": "nbp",
        "symbol": "XAU",
        "unit": "gram",
    },
]


def apply_instrument_defaults(payload: dict) -> dict:
    data = dict(payload)
    ticker = data["ticker"].strip().upper()
    itype = data["type"]
    data["ticker"] = ticker
    if itype == "stock_pl":
        data.setdefault("currency", "PLN")
        data.setdefault("provider", "stooq")
        data.setdefault("symbol", ticker.lower())
        data.setdefault("unit", "share")
        data.setdefault("name", ticker)
    elif itype == "stock_us":
        data.setdefault("currency", "USD")
        data.setdefault("provider", "yahoo")
        data.setdefault("symbol", ticker)
        data.setdefault("unit", "share")
        data.setdefault("name", ticker)
    elif itype == "etf":
        data.setdefault("currency", "EUR")
        data.setdefault("provider", "yahoo")
        data.setdefault("symbol", data.get("symbol") or ticker)
        data.setdefault("unit", "share")
        data.setdefault("name", data.get("name") or ticker)
    elif itype == "gold":
        data.setdefault("currency", "PLN")
        data.setdefault("provider", "nbp")
        data.setdefault("symbol", "XAU")
        data.setdefault("unit", "gram")
        data.setdefault("name", data.get("name") or "Złoto")
    else:
        raise ValueError(f"Nieobsługiwany typ instrumentu: {itype}")
    return data


def seed_instruments(db: Session) -> None:
    existing = {row.isin or row.ticker for row in db.scalars(select(Instrument)).all()}
    for item in SEED:
        key = item.get("isin") or item["ticker"]
        if key in existing:
            continue
        db.add(Instrument(**item))
    db.commit()
