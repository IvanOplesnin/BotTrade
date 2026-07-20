from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Sequence
from zoneinfo import ZoneInfo

from application.candles import candle_rows_from_response
from application.dto import PortfolioSyncResult, PositionLink, StrategyBindingConfig
from application.ports import MarketDataClient, PortfolioSyncRepository
from application.strategy_bindings import (
    default_watchlist_strategy_configs,
    strategy_binding_payloads,
)
from domain.stream_events import PortfolioPositionEvent, PortfolioSnapshotEvent
from services.historic_service.indicators import IndicatorCalculator
from utils import is_updated_today


class PortfolioSyncService:
    """Application use case for synchronizing streamed portfolio snapshots."""

    def __init__(
            self,
            db: PortfolioSyncRepository,
            market_data_client: MarketDataClient,
            *,
            default_strategy_configs: Sequence[StrategyBindingConfig] | None = None,
            tz: ZoneInfo = ZoneInfo("Europe/Moscow"),
    ):
        self._db = db
        self._market_data_client = market_data_client
        if default_strategy_configs is None:
            default_strategy_configs = default_watchlist_strategy_configs()
        self._default_strategy_configs = tuple(default_strategy_configs)
        self._tz = tz

    async def sync(self, snapshot: PortfolioSnapshotEvent) -> PortfolioSyncResult:
        portfolio_positions = _positions_by_id(snapshot.positions)
        async with self._db.session_factory() as session:
            current_positions = await self._db.list_positions_for_account(
                snapshot.account_id,
                session=session,
            )
            current_ids = _instrument_ids_from_position_rows(current_positions)

            if not portfolio_positions:
                await self._remove_all_positions(
                    snapshot.account_id,
                    current_ids,
                    session=session,
                )
                await session.commit()
                return PortfolioSyncResult(added_positions=[], deleted_instrument_ids=[])

            portfolio_ids = set(portfolio_positions)
            need_delete = sorted(current_ids - portfolio_ids)
            need_add = sorted(portfolio_ids - current_ids)

            await self._refresh_missing_or_stale_instruments(
                portfolio_positions,
                session=session,
            )

            if need_delete:
                await self._db.delete_positions_bulk(
                    account_id=snapshot.account_id,
                    instrument_ids=need_delete,
                    session=session,
                )
                await self._db.set_strategy_bindings_enabled(
                    instrument_ids=need_delete,
                    enabled=False,
                    session=session,
                    account_id=snapshot.account_id,
                )

            position_links = [
                _position_link(snapshot.account_id, position)
                for position in portfolio_positions.values()
            ]
            await self._db.set_position_bulk(
                [_position_payload(position) for position in position_links],
                session=session,
            )
            await self._upsert_default_strategy_bindings(
                sorted(portfolio_ids),
                account_id=snapshot.account_id,
                session=session,
            )
            await session.commit()

        added_positions = [
            position
            for position in position_links
            if position.instrument_id in need_add
        ]
        return PortfolioSyncResult(
            added_positions=added_positions,
            deleted_instrument_ids=need_delete,
        )

    async def _remove_all_positions(
            self,
            account_id: str,
            instrument_ids: set[str],
            *,
            session: Any,
    ) -> None:
        if instrument_ids:
            await self._db.set_strategy_bindings_enabled(
                instrument_ids=sorted(instrument_ids),
                enabled=False,
                session=session,
                account_id=account_id,
            )
        await self._db.delete_all_positions_for_account(
            account_id=account_id,
            session=session,
        )

    async def _refresh_missing_or_stale_instruments(
            self,
            positions_by_id: dict[str, PortfolioPositionEvent],
            *,
            session: Any,
    ) -> None:
        existing_by_id = {
            instrument.instrument_id: instrument
            for instrument in await self._db.list_instruments_by_ids(
                list(positions_by_id),
                session=session,
            )
        }
        need_indicators = [
            instrument_id
            for instrument_id in positions_by_id
            if (
                instrument_id not in existing_by_id
                or not is_updated_today(existing_by_id[instrument_id].last_update, tz=self._tz)
            )
        ]
        if not need_indicators:
            return

        rows = []
        candle_rows = []
        now_utc = datetime.now(timezone.utc)
        for instrument_id in need_indicators:
            candles = await self._market_data_client.get_days_candles_for_2_months(instrument_id)
            indicators = IndicatorCalculator(candles_resp=candles).build_instrument_update()
            position = positions_by_id[instrument_id]
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "ticker": position.ticker or instrument_id,
                    "check": True,
                    "to_notify": True,
                    "last_update": now_utc,
                    **indicators,
                }
            )
            candle_rows.extend(
                candle_rows_from_response(
                    instrument_id=instrument_id,
                    timeframe="day",
                    candles_response=candles,
                )
            )
        await self._db.upsert_instruments_bulk_data(rows, session=session, update_ts=True)
        if candle_rows:
            await self._db.upsert_candles(candle_rows, session=session)

    async def _upsert_default_strategy_bindings(
            self,
            instrument_ids: Sequence[str],
            *,
            account_id: str,
            session: Any,
    ) -> None:
        await self._db.upsert_strategy_bindings(
            strategy_binding_payloads(
                instrument_ids,
                self._default_strategy_configs,
                account_id=account_id,
            ),
            session=session,
        )


def _positions_by_id(
        positions: Iterable[PortfolioPositionEvent],
) -> dict[str, PortfolioPositionEvent]:
    return {
        position.instrument_id: position
        for position in positions
        if position.instrument_id
    }


def _instrument_ids_from_position_rows(rows: Sequence[Any]) -> set[str]:
    return {
        row[0].instrument_id
        for row in rows
    }


def _position_link(account_id: str, position: PortfolioPositionEvent) -> PositionLink:
    return PositionLink(
        account_id=account_id,
        instrument_id=position.instrument_id,
        direction="long" if position.quantity_lots > 0 else "short",
    )


def _position_payload(position: PositionLink) -> dict[str, str]:
    return {
        "account_id": position.account_id,
        "instrument_id": position.instrument_id,
        "direction": position.direction,
    }
