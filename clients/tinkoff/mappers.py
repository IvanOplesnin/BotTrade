from __future__ import annotations

from collections.abc import Iterable
from logging import Logger
from typing import Any, Optional

from application.dto import InstrumentCandidate, PositionCandidate
from clients.tinkoff.sdk import sdk_instrument_ticker, sdk_instrument_uid


def portfolio_positions_to_candidates(
        positions: Iterable[Any],
        *,
        log: Optional[Logger] = None,
) -> list[PositionCandidate]:
    candidates: list[PositionCandidate] = []
    for position in positions:
        uid = sdk_instrument_uid(position)
        if not uid:
            if log:
                log.warning("Portfolio position without instrument uid", extra={"position": position})
            continue

        candidates.append(
            PositionCandidate(
                instrument_id=uid,
                ticker=sdk_instrument_ticker(position, default=uid),
                direction=(
                    "long"
                    if position.quantity_lots.units > 0
                    else "short"
                ),
            )
        )
    return candidates


def instruments_to_candidates(instruments: Iterable[Any]) -> list[InstrumentCandidate]:
    return [
        InstrumentCandidate(
            instrument_id=uid,
            ticker=sdk_instrument_ticker(instrument, default=uid),
        )
        for instrument in instruments
        if (uid := sdk_instrument_uid(instrument))
    ]


def flatten_favorite_groups(groups: Iterable[Any]) -> list[Any]:
    instruments: list[Any] = []
    for group in groups:
        instruments.extend(group.favorite_instruments)
    return instruments
