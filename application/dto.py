from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from domain.instrument_links import tbank_instrument_link


@dataclass(frozen=True)
class InstrumentCandidate:
    instrument_id: str
    ticker: str
    instrument_type: str = field(default="", kw_only=True)


@dataclass(frozen=True)
class PositionCandidate(InstrumentCandidate):
    direction: str


@dataclass(frozen=True)
class PositionLink:
    account_id: str
    instrument_id: str
    direction: str


@dataclass(frozen=True)
class StrategyBindingConfig:
    code: str
    version: int = 1
    enabled: bool = True
    mode: str = "notify"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InstrumentSnapshot:
    instrument_id: str
    ticker: str
    check: bool
    to_notify: bool
    instrument_type: Optional[str] = None
    donchian_long_55: Optional[float] = None
    donchian_short_55: Optional[float] = None
    donchian_long_20: Optional[float] = None
    donchian_short_20: Optional[float] = None
    atr14: Optional[float] = None
    last_update: Optional[datetime] = None
    expiration_date: Optional[datetime] = None

    @property
    def link(self) -> str:
        return tbank_instrument_link(self.ticker, self.instrument_type)


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
