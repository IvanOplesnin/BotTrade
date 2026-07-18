from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from application.dto import InstrumentCandidate
from clients.tinkoff.sdk import (
    sdk_instrument_name,
    sdk_instrument_ticker,
    sdk_instrument_uid,
    sdk_text,
)


@dataclass(frozen=True)
class FavoriteInstrumentFSM:
    instrument_id: str
    ticker: str
    name: str
    instrument_type: str = ""

    @classmethod
    def from_sdk(cls, instrument: Any) -> "FavoriteInstrumentFSM":
        instrument_id = sdk_instrument_uid(instrument)
        ticker = sdk_instrument_ticker(instrument, default=instrument_id)
        return cls(
            instrument_id=instrument_id,
            ticker=ticker,
            name=sdk_instrument_name(instrument, default=ticker),
            instrument_type=sdk_text(instrument, "instrument_type"),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FavoriteInstrumentFSM":
        return cls(
            instrument_id=str(data["instrument_id"]),
            ticker=str(data["ticker"]),
            name=str(data.get("name") or data["ticker"]),
            instrument_type=str(data.get("instrument_type") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "instrument_id": self.instrument_id,
            "ticker": self.ticker,
            "name": self.name,
            "instrument_type": self.instrument_type,
        }

    def to_candidate(self) -> InstrumentCandidate:
        return InstrumentCandidate(
            instrument_id=self.instrument_id,
            ticker=self.ticker,
            instrument_type=self.instrument_type,
        )


@dataclass(frozen=True)
class InstrumentFSM:
    instrument_id: str
    ticker: str
    instrument_type: Optional[str] = None

    @classmethod
    def from_model(cls, instrument: Any) -> "InstrumentFSM":
        return cls(
            instrument_id=instrument.instrument_id,
            ticker=instrument.ticker,
            instrument_type=getattr(instrument, "type", None),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InstrumentFSM":
        return cls(
            instrument_id=str(data["instrument_id"]),
            ticker=str(data["ticker"]),
            instrument_type=data.get("instrument_type"),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "instrument_id": self.instrument_id,
            "ticker": self.ticker,
            "instrument_type": self.instrument_type,
        }


def favorite_instruments_to_state(instruments: Iterable[Any]) -> list[dict[str, str]]:
    return [
        item.to_dict()
        for instrument in instruments
        if (item := FavoriteInstrumentFSM.from_sdk(instrument)).instrument_id
    ]


def favorite_instruments_from_state(
        items: Iterable[dict[str, Any]],
) -> list[FavoriteInstrumentFSM]:
    return [FavoriteInstrumentFSM.from_dict(item) for item in items]


def instruments_to_state(instruments: Iterable[Any]) -> list[dict[str, str | None]]:
    return [InstrumentFSM.from_model(instrument).to_dict() for instrument in instruments]


def instruments_from_state(items: Iterable[dict[str, Any]]) -> list[InstrumentFSM]:
    return [InstrumentFSM.from_dict(item) for item in items]

