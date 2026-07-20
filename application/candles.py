from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from domain.stream_events import CandleEvent


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


def candle_row_from_event(event: CandleEvent) -> dict[str, Any] | None:
    if not isinstance(event.time, datetime):
        return None

    return {
        "instrument_id": event.instrument_id,
        "timeframe": normalize_timeframe(event.interval),
        "time": event.time,
        "open": _decimal_price(event.open),
        "high": _decimal_price(event.high),
        "low": _decimal_price(event.low),
        "close": _decimal_price(event.close),
        "volume": event.volume,
        "is_complete": event.is_complete,
    }


def normalize_timeframe(interval: Any) -> str:
    value = getattr(interval, "name", None) or str(interval)
    value = value.lower()
    value = value.rsplit(".", maxsplit=1)[-1]
    value = value.replace("candle_interval_", "")

    return {
        "1_min": "1min",
        "2_min": "2min",
        "3_min": "3min",
        "5_min": "5min",
        "10_min": "10min",
        "15_min": "15min",
        "30_min": "30min",
        "hour": "hour",
        "2_hour": "2hour",
        "4_hour": "4hour",
        "day": "day",
        "week": "week",
        "month": "month",
    }.get(value, value)


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
