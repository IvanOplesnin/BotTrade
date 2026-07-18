from __future__ import annotations

from typing import Optional

TYPE_TO_TBANK_SECTION = {
    "share": "stocks",
    "stock": "stocks",
    "etf": "etfs",
    "currency": "currencies",
    "bond": "bonds",
    "future": "futures",
    "futures": "futures",
}


def tbank_instrument_link(ticker: str, instrument_type: Optional[str]) -> str:
    if not ticker or not instrument_type:
        return ""

    section = TYPE_TO_TBANK_SECTION.get(
        instrument_type.lower(),
        instrument_type.lower(),
    )
    normalized_ticker = ticker.rstrip("@")
    return f"https://www.tbank.ru/invest/{section}/{normalized_ticker}/"
