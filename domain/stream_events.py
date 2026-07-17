from __future__ import annotations

from dataclasses import dataclass
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


MarketDataEvent: TypeAlias = (
    LastPriceEvent
    | LastPriceSubscriptionEvent
    | CandleEvent
    | TradeEvent
)
StreamEvent: TypeAlias = MarketDataEvent | PortfolioSnapshotEvent
