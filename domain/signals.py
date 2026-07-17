from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class SignalKind(str, Enum):
    STOP_LONG = "stop_long"
    STOP_SHORT = "stop_short"
    BREAKOUT_LONG = "breakout_long"
    BREAKOUT_SHORT = "breakout_short"


@dataclass(frozen=True)
class MarketSignal:
    kind: SignalKind
    boundary: float
    side: Optional[str] = None


def decide_market_signal(
        indicators: Any,
        *,
        position_direction: Optional[str],
        last_price: float,
) -> Optional[MarketSignal]:
    """Return a notification decision without touching IO, DB, or Telegram."""
    if not getattr(indicators, "check", False) or not getattr(indicators, "to_notify", False):
        return None

    if position_direction == "long":
        boundary = _number(getattr(indicators, "donchian_short_20", None))
        if boundary is not None and last_price <= boundary:
            return MarketSignal(SignalKind.STOP_LONG, boundary=boundary)
        return None

    if position_direction == "short":
        boundary = _number(getattr(indicators, "donchian_long_20", None))
        if boundary is not None and last_price >= boundary:
            return MarketSignal(SignalKind.STOP_SHORT, boundary=boundary)
        return None

    long_boundary = _number(getattr(indicators, "donchian_long_55", None))
    if long_boundary is not None and last_price >= long_boundary:
        return MarketSignal(SignalKind.BREAKOUT_LONG, boundary=long_boundary, side="long")

    short_boundary = _number(getattr(indicators, "donchian_short_55", None))
    if short_boundary is not None and last_price <= short_boundary:
        return MarketSignal(SignalKind.BREAKOUT_SHORT, boundary=short_boundary, side="short")

    return None


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)
