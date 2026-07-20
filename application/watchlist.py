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
    StrategyBindingConfig,
    UncheckInstrumentsResult,
    WatchAccountResult,
    WatchFavoritesResult,
)
from application.ports import MarketDataClient, WatchlistRepository
from application.strategy_bindings import (
    default_watchlist_strategy_configs,
    strategy_binding_payloads,
)
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
            default_strategy_configs: Sequence[StrategyBindingConfig] | None = None,
            tz: ZoneInfo = ZoneInfo("Europe/Moscow"),
            concurrency: int = CONCURRENCY_CANDLES,
    ):
        self._db = db
        self._market_data_client = market_data_client
        if default_strategy_configs is None:
            default_strategy_configs = default_watchlist_strategy_configs()
        self._default_strategy_configs = tuple(default_strategy_configs)
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
        type_by_id = _type_by_id(positions)
        direction_by_id = {p.instrument_id: p.direction for p in positions}
        rows, _ = await self._build_instrument_rows(
            instrument_ids=instrument_ids,
            ticker_by_id=ticker_by_id,
            type_by_id=type_by_id,
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
            await self._upsert_default_strategy_bindings(
                instrument_ids,
                session=session,
                account_id=account_id,
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
        type_by_id = _type_by_id(instruments)
        futures_ids = _futures_ids(instruments)
        rows, message_instruments = await self._build_instrument_rows(
            instrument_ids=instrument_ids,
            ticker_by_id=ticker_by_id,
            type_by_id=type_by_id,
            futures_instrument_ids=futures_ids,
        )
        refreshed_ids = {row["instrument_id"] for row in rows}
        only_check_ids = [uid for uid in instrument_ids if uid not in refreshed_ids]

        async with self._db.session_factory() as session:
            if rows:
                await self._db.upsert_instruments_bulk_data(rows, session=session)
            if only_check_ids:
                await self._db.set_checked_bulk(only_check_ids, session)
            await self._upsert_default_strategy_bindings(
                instrument_ids,
                session=session,
                account_id=None,
            )
            await session.commit()

        return WatchFavoritesResult(
            instrument_ids=instrument_ids,
            message_instruments=message_instruments,
        )

    async def add_favorites_quick(
            self,
            instruments: Sequence[InstrumentCandidate],
    ) -> WatchFavoritesResult:
        instrument_ids = _ordered_ids(instruments)
        if not instrument_ids:
            return WatchFavoritesResult(instrument_ids=[], message_instruments=[])

        ticker_by_id = {i.instrument_id: i.ticker for i in instruments}
        type_by_id = _type_by_id(instruments)
        async with self._db.session_factory() as session:
            existing_by_id = {
                inst.instrument_id: inst
                for inst in await self._db.list_instruments_by_ids(list(instrument_ids), session=session)
            }
            rows = [
                self._payload_from_existing(
                    instrument_id=instrument_id,
                    ticker=ticker_by_id[instrument_id],
                    instrument_type=type_by_id.get(instrument_id),
                    existing=existing_by_id.get(instrument_id),
                    last_update=None,
                )
                for instrument_id in instrument_ids
            ]
            await self._db.upsert_instruments_bulk_data(
                rows,
                session=session,
                update_ts=False,
            )
            await self._upsert_default_strategy_bindings(
                instrument_ids,
                session=session,
                account_id=None,
            )
            await session.commit()

        return WatchFavoritesResult(
            instrument_ids=instrument_ids,
            message_instruments=[_snapshot_from_payload(row) for row in rows],
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
            await self._db.set_strategy_bindings_enabled(
                instrument_ids=instrument_ids,
                enabled=False,
                session=session,
                account_id=None,
            )
            await session.commit()

        return UncheckInstrumentsResult(instrument_ids=instrument_ids)

    async def _upsert_default_strategy_bindings(
            self,
            instrument_ids: Sequence[str],
            *,
            session: Any,
            account_id: Optional[str],
    ) -> None:
        await self._db.upsert_strategy_bindings(
            strategy_binding_payloads(
                instrument_ids,
                self._default_strategy_configs,
                account_id=account_id,
            ),
            session=session,
        )

    async def _build_instrument_rows(
            self,
            *,
            instrument_ids: Sequence[str],
            ticker_by_id: dict[str, str],
            type_by_id: dict[str, str],
            futures_instrument_ids: Optional[set[str]] = None,
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
            instrument_id
            for instrument_id in instrument_ids
            if (
                instrument_id not in existing_by_id
                and (
                    futures_instrument_ids is None
                    or instrument_id in futures_instrument_ids
                )
            )
        }
        need_instrument_type = {
            instrument_id
            for instrument_id in instrument_ids
            if (
                not type_by_id.get(instrument_id)
                and not getattr(existing_by_id.get(instrument_id), "type", None)
            )
        }
        load_ids = [
            instrument_id
            for instrument_id in instrument_ids
            if (
                instrument_id in need_candles
                or instrument_id in need_expiration_date
                or instrument_id in need_instrument_type
            )
        ]
        candles_by_id, expiration_dates, loaded_types = await self._load_market_data(
            load_ids,
            need_candles=set(need_candles),
            need_expiration_date=need_expiration_date,
            need_instrument_type=need_instrument_type,
        )

        now_utc = datetime.now(timezone.utc)
        rows: list[dict[str, Any]] = []
        message_instruments: list[InstrumentSnapshot] = []
        for instrument_id in instrument_ids:
            ticker = ticker_by_id[instrument_id]
            existing = existing_by_id.get(instrument_id)
            instrument_type = (
                type_by_id.get(instrument_id)
                or loaded_types.get(instrument_id)
                or getattr(existing, "type", None)
            )
            if instrument_id in candles_by_id:
                payload = self._payload_from_candles(
                    instrument_id=instrument_id,
                    ticker=ticker,
                    instrument_type=instrument_type,
                    candles=candles_by_id[instrument_id],
                    last_update=now_utc,
                    expiration_date=expiration_dates.get(instrument_id),
                )
                rows.append(payload)
            else:
                payload = self._payload_from_existing(
                    instrument_id=instrument_id,
                    ticker=ticker,
                    instrument_type=instrument_type,
                    existing=existing,
                    last_update=now_utc,
                )
                if instrument_type and instrument_type != getattr(existing, "type", None):
                    rows.append(payload)

            message_instruments.append(_snapshot_from_payload(payload))

        return rows, message_instruments

    async def _load_market_data(
            self,
            instrument_ids: Iterable[str],
            *,
            need_candles: set[str],
            need_expiration_date: set[str],
            need_instrument_type: set[str],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
        candles_by_id: dict[str, Any] = {}
        expiration_dates: dict[str, Any] = {}
        loaded_types: dict[str, str] = {}
        semaphore = asyncio.Semaphore(self._concurrency)

        async def _fetch_one(instrument_id: str) -> None:
            async with semaphore:
                if instrument_id in need_candles:
                    candles_by_id[
                        instrument_id
                    ] = await self._market_data_client.get_days_candles_for_2_months(instrument_id)
                if instrument_id in need_expiration_date:
                    response = await self._market_data_client.get_futures_response(instrument_id)
                    if response:
                        expiration_dates[instrument_id] = response.instrument.expiration_date
                        loaded_types[instrument_id] = "future"
                if instrument_id in need_instrument_type and instrument_id not in loaded_types:
                    loaded_types[instrument_id] = await self._market_data_client.get_instrument_type(
                        instrument_id
                    )

        await asyncio.gather(*[_fetch_one(instrument_id) for instrument_id in instrument_ids])
        return candles_by_id, expiration_dates, loaded_types

    @staticmethod
    def _payload_from_candles(
            *,
            instrument_id: str,
            ticker: str,
            instrument_type: Optional[str],
            candles: Any,
            last_update: datetime,
            expiration_date: Any = None,
    ) -> dict[str, Any]:
        indicator = IndicatorCalculator(candles_resp=candles).build_instrument_update()
        return {
            "instrument_id": instrument_id,
            "ticker": ticker,
            "type": instrument_type,
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
            instrument_type: Optional[str],
            existing: Optional[Any],
            last_update: Optional[datetime],
    ) -> dict[str, Any]:
        return {
            "instrument_id": instrument_id,
            "ticker": ticker,
            "type": instrument_type or getattr(existing, "type", None),
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


def _futures_ids(instruments: Sequence[InstrumentCandidate]) -> set[str]:
    return {
        instrument.instrument_id
        for instrument in instruments
        if instrument.instrument_type.lower() in {"future", "futures"}
    }


def _type_by_id(instruments: Sequence[InstrumentCandidate]) -> dict[str, str]:
    return {
        instrument.instrument_id: instrument.instrument_type
        for instrument in instruments
        if instrument.instrument_type
    }


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
        instrument_type=payload.get("type"),
        donchian_long_55=payload.get("donchian_long_55"),
        donchian_short_55=payload.get("donchian_short_55"),
        donchian_long_20=payload.get("donchian_long_20"),
        donchian_short_20=payload.get("donchian_short_20"),
        atr14=payload.get("atr14"),
        last_update=payload.get("last_update"),
        expiration_date=payload.get("expiration_date"),
    )
