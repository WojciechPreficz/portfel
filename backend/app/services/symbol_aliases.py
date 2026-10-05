XSTATION_TO_YAHOO_SUFFIX = {
    "US": "",
    "PL": ".WA",
    "DE": ".DE",
    "UK": ".L",
    "FR": ".PA",
    "NL": ".AS",
    "IT": ".MI",
    "ES": ".MC",
    "CH": ".SW",
    "BE": ".BR",
    "PT": ".LS",
    "DK": ".CO",
    "SE": ".ST",
    "NO": ".OL",
    "FI": ".HE",
    "AT": ".VI",
    "IE": ".IR",
}

XSTATION_SUFFIX_CURRENCIES = {
    "US": "USD",
    "PL": "PLN",
    "DE": "EUR",
    "UK": "GBP",
    "FR": "EUR",
    "NL": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "CH": "CHF",
    "BE": "EUR",
    "PT": "EUR",
    "DK": "DKK",
    "SE": "SEK",
    "NO": "NOK",
    "FI": "EUR",
    "AT": "EUR",
    "IE": "EUR",
}

YAHOO_SUFFIX_TO_XSTATION = {
    yahoo_suffix: xstation_suffix
    for xstation_suffix, yahoo_suffix in XSTATION_TO_YAHOO_SUFFIX.items()
    if yahoo_suffix
}

YAHOO_SYMBOL_ALIASES = {
    "ASSECOPOL.WA": "ACP.WA",
    "ASSECCOPOL.WA": "ACP.WA",
    "DEBICA.WA": "DBC.WA",
    "11BIT.WA": "11B.WA",
    "AMBRA": "AMB.WA",
    "AMBRA.WA": "AMB.WA",
    "KRUK": "KRU.WA",
    "KRUK.WA": "KRU.WA",
    "ZWC": "ZWC.WA",
    "MEU": "MEUD.MI",
    "MEUD.FR": "MEUD.MI",
}

STOOQ_SYMBOL_ALIASES = {
    "11BIT": "11b",
    "AMBRA": "amb",
    "KRUK": "kru",
    "ZWC": "zwc",
}

BOSSA_NAME_ALIASES = {
    "vanguard lifestrategy 80 equity ucits etf": {
        "ticker": "V80A",
        "raw_ticker": "V80A.AS",
        "isin": "IE00BMVB5R75",
    },
}
