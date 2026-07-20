from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Protocol


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
    strategy_code: str = ""
    strategy_version: int = 1
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandleRequirement:
    timeframe: str
    warmup: int


@dataclass(frozen=True)
class MarketDataRequirements:
    candles: tuple[CandleRequirement, ...] = ()
    last_price: bool = False
    trades: bool = False


@dataclass(frozen=True)
class StrategyContext:
    instrument: Any
    position_direction: Optional[str]
    last_price: float


class Strategy(Protocol):
    code: str
    version: int

    def requirements(self, params: Any = None) -> MarketDataRequirements:
        ...

    def decide(self, context: StrategyContext, params: Any = None) -> Optional[MarketSignal]:
        ...

