from __future__ import annotations

from typing import Any


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
