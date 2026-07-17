from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class InstrumentCandidate:
    instrument_id: str
    ticker: str


@dataclass(frozen=True)
class PositionCandidate(InstrumentCandidate):
    direction: str


@dataclass(frozen=True)
class PositionLink:
    account_id: str
    instrument_id: str
    direction: str


@dataclass(frozen=True)
class InstrumentSnapshot:
    instrument_id: str
    ticker: str
    check: bool
    to_notify: bool
    donchian_long_55: Optional[float] = None
    donchian_short_55: Optional[float] = None
    donchian_long_20: Optional[float] = None
    donchian_short_20: Optional[float] = None
    atr14: Optional[float] = None
    last_update: Optional[datetime] = None
    expiration_date: Optional[datetime] = None


@dataclass(frozen=True)
class WatchAccountResult:
    instrument_ids: list[str]
    positions: list[PositionLink]


@dataclass(frozen=True)
class WatchFavoritesResult:
    instrument_ids: list[str]
    message_instruments: list[InstrumentSnapshot]


@dataclass(frozen=True)
class RemoveAccountResult:
    instrument_ids: list[str]
    detached_instrument_ids: list[str]


@dataclass(frozen=True)
class UncheckInstrumentsResult:
    instrument_ids: list[str]
