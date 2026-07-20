from __future__ import annotations

from typing import Any, Optional

from domain.strategies import (
    DonchianBreakoutStrategy,
    MarketSignal,
    SignalKind,
    StrategyContext,
)

_DEFAULT_STRATEGY = DonchianBreakoutStrategy()


def decide_market_signal(
        indicators: Any,
        *,
        position_direction: Optional[str],
        last_price: float,
) -> Optional[MarketSignal]:
    """Compatibility facade for the default Donchian breakout strategy."""
    return _DEFAULT_STRATEGY.decide(
        StrategyContext(
            instrument=indicators,
            position_direction=position_direction,
            last_price=last_price,
        )
    )


__all__ = [
    "MarketSignal",
    "SignalKind",
    "decide_market_signal",
]
