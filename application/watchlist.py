from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

from application.dto import (
    InstrumentCandidate,
    InstrumentSnapshot,
    PositionCandidate,
    PositionLink,
    RemoveAccountResult,
    UncheckInstrumentsResult,
    WatchAccountResult,
    WatchFavoritesResult,
)
from application.ports import MarketDataClient, WatchlistRepository
from services.historic_service.indicators import IndicatorCalculator
from utils import is_updated_today

CONCURRENCY_CANDLES = 12


class WatchlistService:
    """Application use case for bringing instruments into active monitoring."""

    def __init__(
            self,
            db: WatchlistRepository,
            market_data_client: MarketDataClient,
            *,
            tz: ZoneInfo = ZoneInfo("Europe/Moscow"),
            concurrency: int = CONCURRENCY_CANDLES,
    ):
        self._db = db
        self._market_data_client = market_data_client
        self._tz = tz
        self._concurrency = concurrency

    async def add_account(
            self,
            *,
            account_id: str,
            account_name: str,
            positions: Sequence[PositionCandidate],
    ) -> WatchAccountResult:
        instrument_ids = _ordered_ids(positions)
        if not instrument_ids:
            return WatchAccountResult(instrument_ids=[], positions=[])

        ticker_by_id = {p.instrument_id: p.ticker for p in positions}
        direction_by_id = {p.instrument_id: p.direction for p in positions}
        rows, _ = await self._build_instrument_rows(
            instrument_ids=instrument_ids,
            ticker_by_id=ticker_by_id,
        )
        refreshed_ids = {row["instrument_id"] for row in rows}
        only_check_ids = [uid for uid in instrument_ids if uid not in refreshed_ids]
        position_links = [
            PositionLink(
                account_id=account_id,
                instrument_id=instrument_id,
                direction=direction_by_id[instrument_id],
            )
            for instrument_id in instrument_ids
        ]

        async with self._db.session_factory() as session:
            await self._db.upsert_account(
                account_id=account_id,
                name=account_name,
                check=True,
                session=session,
            )
            if rows:
                await self._db.upsert_instruments_bulk_data(rows, session=session)
            if only_check_ids:
                await self._db.set_checked_bulk(only_check_ids, session)
            await self._db.set_position_bulk(
                [_position_payload(p) for p in position_links],
                session=session,
            )
            await session.commit()

        return WatchAccountResult(instrument_ids=instrument_ids, positions=position_links)

    async def add_favorites(
            self,
            instruments: Sequence[InstrumentCandidate],
    ) -> WatchFavoritesResult:
        instrument_ids = _ordered_ids(instruments)
        if not instrument_ids:
            return WatchFavoritesResult(instrument_ids=[], message_instruments=[])

        ticker_by_id = {i.instrument_id: i.ticker for i in instruments}
        rows, message_instruments = await self._build_instrument_rows(
            instrument_ids=instrument_ids,
            ticker_by_id=ticker_by_id,
        )
        refreshed_ids = {row["instrument_id"] for row in rows}
        only_check_ids = [uid for uid in instrument_ids if uid not in refreshed_ids]

        async with self._db.session_factory() as session:
            if rows:
                await self._db.upsert_instruments_bulk_data(rows, session=session)
            if only_check_ids:
                await self._db.set_checked_bulk(only_check_ids, session)
            await session.commit()

        return WatchFavoritesResult(
            instrument_ids=instrument_ids,
            message_instruments=message_instruments,
        )

    async def remove_account(self, account_id: str) -> RemoveAccountResult:
        async with self._db.session_factory() as session:
            positions = await self._db.list_positions_for_account(
                account_id=account_id,
                session=session,
            )
            instrument_ids = [position.instrument_id for position, _ in positions]
            await self._db.delete_account(account_id=account_id, session=session)

            detached_instrument_ids = []
            for instrument_id in instrument_ids:
                active_positions = await self._db.list_position_by_id(
                    instrument_id=instrument_id,
                    session=session,
                )
                if not active_positions:
                    detached_instrument_ids.append(instrument_id)

            if detached_instrument_ids:
                await self._db.set_checked_bulk(
                    detached_instrument_ids,
                    session=session,
                    check=False,
                )

            await session.commit()

        return RemoveAccountResult(
            instrument_ids=instrument_ids,
            detached_instrument_ids=detached_instrument_ids,
        )

    async def uncheck_instruments(self, instruments: Sequence[Any]) -> UncheckInstrumentsResult:
        instrument_ids = [instrument.instrument_id for instrument in instruments]
        async with self._db.session_factory() as session:
            await self._db.set_checked_bulk(instrument_ids, session=session, check=False)
            await session.commit()

        return UncheckInstrumentsResult(instrument_ids=instrument_ids)

    async def _build_instrument_rows(
            self,
            *,
            instrument_ids: Sequence[str],
            ticker_by_id: dict[str, str],
    ) -> tuple[list[dict[str, Any]], list[InstrumentSnapshot]]:
        async with self._db.session_factory() as session:
            existing_by_id = {
                inst.instrument_id: inst
                for inst in await self._db.list_instruments_by_ids(list(instrument_ids), session=session)
            }

        need_candles = [
            instrument_id
            for instrument_id in instrument_ids
            if (
                instrument_id not in existing_by_id
                or not is_updated_today(existing_by_id[instrument_id].last_update, tz=self._tz)
            )
        ]
        need_expiration_date = {
            instrument_id for instrument_id in instrument_ids if instrument_id not in existing_by_id
        }
        candles_by_id, expiration_dates = await self._load_market_data(
            need_candles,
            need_expiration_date=need_expiration_date,
        )

        now_utc = datetime.now(timezone.utc)
        rows: list[dict[str, Any]] = []
        message_instruments: list[InstrumentSnapshot] = []
        for instrument_id in instrument_ids:
            ticker = ticker_by_id[instrument_id]
            existing = existing_by_id.get(instrument_id)
            if instrument_id in candles_by_id:
                payload = self._payload_from_candles(
                    instrument_id=instrument_id,
                    ticker=ticker,
                    candles=candles_by_id[instrument_id],
                    last_update=now_utc,
                    expiration_date=expiration_dates.get(instrument_id),
                )
                rows.append(payload)
            else:
                payload = self._payload_from_existing(
                    instrument_id=instrument_id,
                    ticker=ticker,
                    existing=existing,
                    last_update=now_utc,
                )

            message_instruments.append(_snapshot_from_payload(payload))

        return rows, message_instruments

    async def _load_market_data(
            self,
            instrument_ids: Iterable[str],
            *,
            need_expiration_date: set[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        candles_by_id: dict[str, Any] = {}
        expiration_dates: dict[str, Any] = {}
        semaphore = asyncio.Semaphore(self._concurrency)

        async def _fetch_one(instrument_id: str) -> None:
            async with semaphore:
                candles_by_id[
                    instrument_id
                ] = await self._market_data_client.get_days_candles_for_2_months(instrument_id)
                if instrument_id in need_expiration_date:
                    response = await self._market_data_client.get_futures_response(instrument_id)
                    if response:
                        expiration_dates[instrument_id] = response.instrument.expiration_date

        await asyncio.gather(*[_fetch_one(instrument_id) for instrument_id in instrument_ids])
        return candles_by_id, expiration_dates

    @staticmethod
    def _payload_from_candles(
            *,
            instrument_id: str,
            ticker: str,
            candles: Any,
            last_update: datetime,
            expiration_date: Any = None,
    ) -> dict[str, Any]:
        indicator = IndicatorCalculator(candles_resp=candles).build_instrument_update()
        return {
            "instrument_id": instrument_id,
            "ticker": ticker,
            "check": True,
            "to_notify": True,
            "donchian_long_55": indicator.get("donchian_long_55"),
            "donchian_short_55": indicator.get("donchian_short_55"),
            "donchian_long_20": indicator.get("donchian_long_20"),
            "donchian_short_20": indicator.get("donchian_short_20"),
            "atr14": indicator.get("atr14"),
            "last_update": last_update,
            "expiration_date": expiration_date,
        }

    @staticmethod
    def _payload_from_existing(
            *,
            instrument_id: str,
            ticker: str,
            existing: Optional[Any],
            last_update: datetime,
    ) -> dict[str, Any]:
        return {
            "instrument_id": instrument_id,
            "ticker": ticker,
            "check": True,
            "to_notify": getattr(existing, "to_notify", True),
            "donchian_long_55": getattr(existing, "donchian_long_55", None),
            "donchian_short_55": getattr(existing, "donchian_short_55", None),
            "donchian_long_20": getattr(existing, "donchian_long_20", None),
            "donchian_short_20": getattr(existing, "donchian_short_20", None),
            "atr14": getattr(existing, "atr14", None),
            "last_update": getattr(existing, "last_update", last_update),
            "expiration_date": getattr(existing, "expiration_date", None),
        }


def _ordered_ids(instruments: Sequence[InstrumentCandidate]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for instrument in instruments:
        if instrument.instrument_id in seen:
            continue
        result.append(instrument.instrument_id)
        seen.add(instrument.instrument_id)
    return result


def _position_payload(position: PositionLink) -> dict[str, str]:
    return {
        "account_id": position.account_id,
        "instrument_id": position.instrument_id,
        "direction": position.direction,
    }


def _snapshot_from_payload(payload: dict[str, Any]) -> InstrumentSnapshot:
    return InstrumentSnapshot(
        instrument_id=payload["instrument_id"],
        ticker=payload["ticker"],
        check=payload["check"],
        to_notify=payload["to_notify"],
        donchian_long_55=payload.get("donchian_long_55"),
        donchian_short_55=payload.get("donchian_short_55"),
        donchian_long_20=payload.get("donchian_long_20"),
        donchian_short_20=payload.get("donchian_short_20"),
        atr14=payload.get("atr14"),
        last_update=payload.get("last_update"),
        expiration_date=payload.get("expiration_date"),
    )
