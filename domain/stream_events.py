from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class LastPriceEvent:
    instrument_id: str
    price: Decimal
    time: datetime


@dataclass(frozen=True, slots=True)
class LastPriceSubscriptionEvent:
    instrument_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandleEvent:
    instrument_id: str
    interval: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    time: datetime | None = None
    volume: int | None = None
    is_complete: bool = False


@dataclass(frozen=True, slots=True)
class TradeEvent:
    instrument_id: str
    price: Decimal
    quantity: int


@dataclass(frozen=True, slots=True)
class PortfolioPositionEvent:
    instrument_id: str
    ticker: str
    quantity_lots: int


@dataclass(frozen=True, slots=True)
class PortfolioSnapshotEvent:
    account_id: str
    positions: tuple[PortfolioPositionEvent, ...]


@dataclass(frozen=True, slots=True)
class StrategySignalCreatedEvent:
    instrument_id: str
    ticker: str
    instrument_type: str | None
    position_direction: str | None
    last_price: Decimal
    signal_kind: str
    signal_side: str | None
    signal_boundary: Decimal | None
    strategy_code: str
    strategy_version: int
    payload: dict[str, object] = field(default_factory=dict)
    indicators: dict[str, float | None] = field(default_factory=dict)
    event_time: datetime | None = None


MarketDataEvent: TypeAlias = (
    LastPriceEvent
    | LastPriceSubscriptionEvent
    | CandleEvent
    | TradeEvent
)
StreamEvent: TypeAlias = MarketDataEvent | PortfolioSnapshotEvent | StrategySignalCreatedEvent
