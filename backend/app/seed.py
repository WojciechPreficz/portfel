import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Instrument

GPW_STOCK_TICKERS = """
06MAGNA 08OCTAVA 11BIT 3RGAMES 4MASS ABPL ACAUTOGAZ ACTION ADIUVO AGORA AGROTON AIGAMES AILLERON AIRWAY ALIOR ALLEGRO ALTA ALTUS AMBRA AMICA AMPLI AMREST ANSWEAR APATOR APLISENS APSENERGY ARCHICOM ARCTIC ARLEN ARTIFEX ASBIS ASMGROUP ASSECOBS ASSECOPOL ASSECOSEE ASTARTA ATAL ATENDE ATLANTAPL ATLANTIS ATMGRUPA ATREM AUTOPARTN BBIDEV BENEFIT BEST BETACOM BIGCHEESE BIOCELTIX BIOPLANET BIOTON BLOOBER BNPPPL BOGDANKA BOOMBIT BORYSZEW BOS BOWIM BUDIMEX BUMECH BUMECHDEF CAPITEA CAPTORTX CASPAR CAVATINA CCENERGY CDPROJEKT CDRL CELTIC CEZ CFI CIGAMES CITYSERV CLNPHARMA CLOUD COALENERG COGNOR COLUMBUS COMP COMPERIA COMPREMUM CORMAY CPIEUROPE CREEPYJAR CREOTECH CRQUANTUM CYBERFLKS CYFRPLSAT CZTOREBKA DADELO DATAWALK DBENERGY DEBICA DECORA DEKPOL DELKO DEVELIA DGA DIAG DIGITANET DIGITREE DINOPL DMGROUP DOMDEV DRAGOENT ECBSA ECHO EDINVEST EFEKT ELEKTROTI ELKOP EMPLOCITY ENEA ENELMED ENERGA ENERGOINS ENTER EQUNICO ERBUD ERSTEPL ESOTIQ ESTAR EUROCASH EUROHOLD EUROTEL FABRITY FASING FASTFIN FEERUM FERRO FMG FON FOODHUB FORTE GAMEOPS GAMFACTOR GENOMTEC GETIN GOBARTO GREENX GRODNO GRUPAAZOTY GRUPRACUJ GTC HANDLOWY HARPER HELIO HERKULES HUUUGE HYDROTOR IBSM IDMSA IFIRMA IFSA IMCOMPANY IMMOBILE IMPERIO IMS INC INGBSK INPOST INPRO INSTALKRK INTERBUD INTERCARS INTERSPPL INTROL IPOPEMA IZOBLOK IZOLACJA IZOSTAL JRH JSW JWWINVEST KCI KERNEL KETY KGHM KGL KINOPOL KOGENERA KOMPAP KOMPUTRON KPPD KRAKCHEM KRKA KRUK KRVITAMIN KSGAGRO LARQ LENA LENTEX LESS LIBET LMCU LOKUM LPP LSISOFT LUBAWA MABION MAKARONPL MANGATA MANYDEV MARVIPOL MAXCOM MBANK MBWS MCI MCR MDIENERGIA MEDICALG MEDINICE MEGARON MENNICA MERCATOR MEXPOLSKA MFO MILKILAND MILLENNIUM MIRACULUM MIRBUD MLPGROUP MLSYSTEM MOBRUK MODIVO MOL MOLECURE MONNARI MOSTALPLC MOSTALWAR MOSTALZAB MOVIEGAMES MULTIQURE MURAPOL MWTRADE NANOGROUP NEUCA NEWAG NEXITY NOTORIA NOTOWANIA NOVATURAS NOVAVISGR NOVITA NTCAPITAL NTTSYSTEM ODLEWNIE ONDE ONESANO OPONEO.PL OPTEAM ORANGEPL OTLOG OTMUCHOW PANOVA PASSUS PATENTUS PBG PBSFINANSE PCCEXOL PCCROKITA PCFGROUP PEKABEX PEKAO PEP PEPCO PEPEES PGE PGFGROUP PHARMENA PHN PHOTON PJPMAKRUM PKNORLEN PKOBP PKPCARGO PLAYWAY PLAZACNTR PMPG POLICE POLIMEXMS POLTREG POLWAX PRAGMAINK PRIMAMODA PROCHEM PROMISE PROTEKTOR PTWP PULAWY PZU QUANTUM QUERCUS RAFAMET RAINBOW RANKPROGR RAWLPLUG REGNON REINHOLD REINO RELPOL REMAK RENDER REX ROBYG ROPCZYCE RYVU SANOK SANTANDER SANWIL SCPFL SECOGROUP SEKO SELENAFM SELVITA SFINKS SILVAIR-REGS SILVANO SIMFABRIC SKARBIEC SKYLINE SNIEZKA SNTVERSE SOHODEV SONEL SOPHARMA SPYROSOFT STALEXP STALPROD STALPROFI STAPORKOW STARHEDGE SUNEX SYGNITY SYN2BIO SYNEKTIK TALEX TARCZYNSKI TATRY TAURONPE TBULL TENDERHUT TERMOREX TESGAS TEXT TORPOL TOWERINVT TOYA TRAKCJA TRANSPOL TRITON TSGAMES ULMA ULTGAMES UNFOLD UNIBEP UNICREDIT UNIMOT URTESTE VERCOM VIGOPHOTN VINDEXUS VIRTUS VIVID VOTUM VOXEL VRG WARIMPEX WASKO WAWEL WIELTON WIKANA WIRTUALNA WITTCHEN XPLUS XTB XTPL YANOSIK YARRL ZABKA ZAMET ZEPAK ZREMB ZUE
""".split()

CURATED_STOCK_TICKERS = {
    "ALR", "BEN", "BHW", "CCC", "CDR", "CIE", "DNP", "EAT", "GTC", "JSW",
    "KGH", "LPP", "MBK", "MCR", "ATT", "PGE", "PKN", "PKO", "PZU", "SPL",
    "TPE", "PEO", "ALE", "ACP", "FTE", "ING", "MIL", "OPL", "PEP", "BOS",
    "BRS", "MKT", "QRS", "ATC", "NXT", "KTY", "KRU", "FSA", "HEX", "CDP",
    "TMR", "XTB", "ZAB", "MVP", "WSE", "TES", "R22", "BFT", "GRA", "VRC",
}

STOOQ_SYMBOL_OVERRIDES = {
    "11BIT": "11b",
}

POLISH_MARKET_INSTRUMENTS = {
    "stock_pl": [
        {"ticker": "ALE", "name": "Allegro.eu", "type": "stock_pl"},
        {"ticker": "CCC", "name": "CCC", "type": "stock_pl"},
        {"ticker": "CDR", "name": "CD Projekt", "type": "stock_pl"},
        {"ticker": "CIE", "name": "CIECH", "type": "stock_pl"},
        {"ticker": "DNP", "name": "Dino Polska", "type": "stock_pl"},
        {"ticker": "EAT", "name": "AmRest", "type": "stock_pl"},
        {"ticker": "GTC", "name": "Globe Trade Centre", "type": "stock_pl"},
        {"ticker": "JSW", "name": "JSW", "type": "stock_pl"},
        {"ticker": "KGH", "name": "KGHM Polska Miedź", "type": "stock_pl"},
        {"ticker": "LPP", "name": "LPP", "type": "stock_pl"},
        {"ticker": "MBK", "name": "mBank", "type": "stock_pl"},
        {"ticker": "MCR", "name": "MCR Capital", "type": "stock_pl"},
        {"ticker": "ATT", "name": "Grupa Azoty", "type": "stock_pl"},
        {"ticker": "PGE", "name": "PGE Polska Grupa Energetyczna", "type": "stock_pl"},
        {"ticker": "PKN", "name": "PKN Orlen", "type": "stock_pl"},
        {"ticker": "PKO", "name": "PKO BP", "type": "stock_pl"},
        {"ticker": "PZU", "name": "PZU", "type": "stock_pl"},
        {"ticker": "SPL", "name": "Santander Bank Polska", "type": "stock_pl"},
        {"ticker": "TPE", "name": "TPE", "type": "stock_pl"},
        {"ticker": "PEO", "name": "PEKAO SA", "type": "stock_pl"},
        {"ticker": "ACP", "name": "Asseco Poland", "type": "stock_pl"},
        {"ticker": "FTE", "name": "Forte", "type": "stock_pl"},
        {"ticker": "ING", "name": "ING Bank Śląski", "type": "stock_pl"},
        {"ticker": "MIL", "name": "Millenium", "type": "stock_pl"},
        {"ticker": "OPL", "name": "Orange Polska", "type": "stock_pl"},
        {"ticker": "PEP", "name": "Polenergia", "type": "stock_pl"},
        {"ticker": "BOS", "name": "Bank Ochrony Środowiska", "type": "stock_pl"},
        {"ticker": "BRS", "name": "Boryszew", "type": "stock_pl"},
        {"ticker": "MKT", "name": "MKT", "type": "stock_pl"},
        {"ticker": "QRS", "name": "Quercus TFI", "type": "stock_pl"},
        {"ticker": "ATC", "name": "Arctic Paper", "type": "stock_pl"},
        {"ticker": "NXT", "name": "Nexter", "type": "stock_pl"},
        {"ticker": "KTY", "name": "Grupa Kęty", "type": "stock_pl"},
        {"ticker": "KRU", "name": "Kruk", "type": "stock_pl"},
        {"ticker": "FSA", "name": "FSA", "type": "stock_pl"},
        {"ticker": "HEX", "name": "Hexagon", "type": "stock_pl"},
        {"ticker": "CDP", "name": "CDP", "type": "stock_pl"},
        {"ticker": "TMR", "name": "Tatry Mountain Resorts", "type": "stock_pl"},
        {"ticker": "XTB", "name": "XTB", "type": "stock_pl"},
        {"ticker": "ZAB", "name": "Zabka", "type": "stock_pl"},
        {"ticker": "MVP", "name": "MVP", "type": "stock_pl"},
        {"ticker": "WSE", "name": "WSE", "type": "stock_pl"},
        {"ticker": "TES", "name": "Tesco Polska", "type": "stock_pl"},
        {"ticker": "R22", "name": "R22", "type": "stock_pl"},
        {"ticker": "BFT", "name": "Benefit Systems", "type": "stock_pl"},
        {"ticker": "GRA", "name": "GRA", "type": "stock_pl"},
        {"ticker": "VRC", "name": "VRC", "type": "stock_pl"},
        *[
            {"ticker": ticker, "name": ticker, "type": "stock_pl"}
            for ticker in GPW_STOCK_TICKERS
            if ticker not in CURATED_STOCK_TICKERS
        ],
    ],
    "etf": [
        {"ticker": "C6E", "isin": "LU0908500753", "name": "Amundi Core Stoxx Europe 600 UCITS ETF Acc EUR", "type": "etf", "currency": "EUR", "provider": "yahoo", "symbol": "LYP6.DE", "unit": "share"},
        {"ticker": "V80A", "isin": "IE00BMVB5R75", "name": "Vanguard LifeStrategy 80% Equity UCITS ETF Acc EUR", "type": "etf", "currency": "EUR", "provider": "yahoo", "symbol": "V80A.DE", "unit": "share"},
        {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "type": "etf", "currency": "USD", "provider": "yahoo", "symbol": "SPY", "unit": "share"},
        {"ticker": "QQQ", "name": "Invesco NASDAQ 100 ETF", "type": "etf", "currency": "USD", "provider": "yahoo", "symbol": "QQQ", "unit": "share"},
        {"ticker": "IVV", "name": "iShares Core S&P 500 ETF", "type": "etf", "currency": "USD", "provider": "yahoo", "symbol": "IVV", "unit": "share"},
        {"ticker": "VGK", "name": "Vanguard FTSE Europe ETF", "type": "etf", "currency": "USD", "provider": "yahoo", "symbol": "VGK", "unit": "share"},
    ],
}

NASDAQ_STOCKS_PATH = Path(__file__).resolve().parents[2] / "data" / "nasdaq_stocks.json"
NYSE_STOCKS_PATH = Path(__file__).resolve().parents[2] / "data" / "nyse_stocks.json"

with NASDAQ_STOCKS_PATH.open(encoding="utf-8") as nasdaq_file:
    NASDAQ_STOCKS = json.load(nasdaq_file)
with NYSE_STOCKS_PATH.open(encoding="utf-8") as nyse_file:
    NYSE_STOCKS = [{**item, "type": "stock_us_nyse"} for item in json.load(nyse_file)]

SEED = [
    *[
        {
            **item,
            "currency": "PLN",
            "provider": "stooq",
            "symbol": STOOQ_SYMBOL_OVERRIDES.get(item["ticker"], item["ticker"].lower()),
            "unit": "share",
        }
        for item in POLISH_MARKET_INSTRUMENTS["stock_pl"]
    ],
    *[
        {**item, "currency": item.get("currency", "EUR"), "provider": item.get("provider", "yahoo"), "symbol": item.get("symbol", item["ticker"]), "unit": item.get("unit", "share")}
        for item in POLISH_MARKET_INSTRUMENTS["etf"]
    ],
    *NASDAQ_STOCKS,
    *NYSE_STOCKS,
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
    elif itype in {"stock_us", "stock_us_nyse"}:
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
    existing_rows = {row.isin or row.ticker: row for row in db.scalars(select(Instrument)).all()}
    for item in SEED:
        key = item.get("isin") or item["ticker"]
        if item["ticker"] == "KTY" and "GKP" in existing_rows:
            existing_rows["GKP"].ticker = "KTY"
            existing_rows["GKP"].symbol = "kty"
            existing_rows["GKP"].name = item["name"]
            existing_rows["KTY"] = existing_rows["GKP"]
        if key in existing_rows:
            row = existing_rows[key]
            override_symbol = STOOQ_SYMBOL_OVERRIDES.get(row.ticker)
            if override_symbol:
                row.symbol = override_symbol
            if row.isin == "LU0908500753" and row.symbol == "C6E.DE":
                row.symbol = item["symbol"]
            continue
        db.add(Instrument(**item))
    db.commit()
