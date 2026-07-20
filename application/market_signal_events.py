from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from application.dto import MarketSignalDecision
from domain.stream_events import StrategySignalCreatedEvent

INDICATOR_FIELDS = (
    "donchian_long_55",
    "donchian_short_55",
    "donchian_long_20",
    "donchian_short_20",
    "atr14",
)


def strategy_signal_event_from_decision(
        decision: MarketSignalDecision,
        *,
        event_time: datetime,
) -> StrategySignalCreatedEvent:
    instrument = decision.instrument
    signal = decision.signal
    return StrategySignalCreatedEvent(
        instrument_id=str(getattr(instrument, "instrument_id")),
        ticker=str(getattr(instrument, "ticker", "")),
        instrument_type=_optional_text(
            getattr(instrument, "type", None)
            or getattr(instrument, "instrument_type", None)
        ),
        position_direction=decision.position_direction,
        last_price=_decimal(decision.last_price),
        signal_kind=signal.kind.value,
        signal_side=signal.side,
        signal_boundary=_decimal(signal.boundary),
        strategy_code=signal.strategy_code,
        strategy_version=signal.strategy_version,
        payload=dict(signal.payload),
        indicators={
            field: _optional_float(getattr(instrument, field, None))
            for field in INDICATOR_FIELDS
        },
        event_time=event_time,
    )


def _decimal(value: float | int | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
