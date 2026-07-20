from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any


def candle_rows_from_response(
        *,
        instrument_id: str,
        timeframe: str,
        candles_response: Any,
) -> list[dict[str, Any]]:
    return [
        {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "time": candle.time,
            "open": _decimal_price(candle.open),
            "high": _decimal_price(candle.high),
            "low": _decimal_price(candle.low),
            "close": _decimal_price(candle.close),
            "volume": getattr(candle, "volume", None),
            "is_complete": bool(getattr(candle, "is_complete", False)),
        }
        for candle in getattr(candles_response, "candles", ())
        if isinstance(getattr(candle, "time", None), datetime)
    ]


def _decimal_price(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))

    units = getattr(value, "units", None)
    nano = getattr(value, "nano", None)
    if units is not None and nano is not None:
        return Decimal(units) + Decimal(nano) / Decimal(1_000_000_000)

    return Decimal(str(value))
