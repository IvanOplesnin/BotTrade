from __future__ import annotations

from collections.abc import Iterable
from logging import Logger
from typing import Any, Optional

from application.dto import InstrumentCandidate, PositionCandidate
from clients.tinkoff.sdk import sdk_instrument_ticker, sdk_instrument_uid, sdk_text

CASH_LIKE_INSTRUMENT_TYPES = {"currency"}
CASH_LIKE_TICKERS = {
    "RUB000UTSTOM",
    "TMON",
}


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
        if is_cash_like_position(position):
            if log:
                log.info(
                    "Skip cash-like portfolio position",
                    extra={"instrument_uid": uid, "ticker": sdk_instrument_ticker(position)},
                )
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


def is_cash_like_position(position: Any) -> bool:
    instrument_type = sdk_text(position, "instrument_type").lower()
    if instrument_type in CASH_LIKE_INSTRUMENT_TYPES:
        return True

    ticker = _normalize_ticker(sdk_instrument_ticker(position))
    return ticker in CASH_LIKE_TICKERS


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


def _normalize_ticker(ticker: str) -> str:
    return ticker.upper().rstrip("@")
