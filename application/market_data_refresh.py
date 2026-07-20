from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from application.candles import candle_rows_from_response
from application.dto import MarketDataRefreshResult
from application.ports import MarketDataClient, MarketDataRefreshRepository
from application.strategy_state import StrategyStateService
from services.historic_service.indicators import IndicatorCalculator
from utils import is_updated_today


class MarketDataRefreshService:
    """Application use case for refreshing indicators, candles and strategy state."""

    def __init__(
            self,
            db: MarketDataRefreshRepository,
            market_data_client: MarketDataClient,
            strategy_state_svc: StrategyStateService,
            *,
            tz: ZoneInfo = ZoneInfo("Europe/Moscow"),
    ):
        self._db = db
        self._market_data_client = market_data_client
        self._strategy_state_svc = strategy_state_svc
        self._tz = tz

    async def refresh(
            self,
            *,
            update_notify: bool = False,
    ) -> MarketDataRefreshResult:
        async with self._db.session_factory() as session:
            instruments = await self._db.list_instruments(session)
            refreshed_ids = []
            now = datetime.now(self._tz)
            for instrument in instruments:
                if is_updated_today(instrument.last_update, now, self._tz):
                    continue
                await self._recalc_and_update(
                    instrument.instrument_id,
                    update_notify=update_notify,
                    session=session,
                )
                refreshed_ids.append(instrument.instrument_id)
            await session.commit()

        strategy_state = await self._strategy_state_svc.refresh_all()
        return MarketDataRefreshResult(
            refreshed_instrument_ids=refreshed_ids,
            active_instrument_ids=[
                instrument.instrument_id
                for instrument in instruments
                if instrument.check
            ],
            strategy_state=strategy_state,
        )

    async def _recalc_and_update(
            self,
            instrument_id: str,
            *,
            update_notify: bool,
            session: Any,
    ) -> None:
        candles = await self._market_data_client.get_days_candles_for_2_months(instrument_id)
        indicators = IndicatorCalculator(candles).build_instrument_update()
        if update_notify:
            indicators["to_notify"] = True
        await self._db.update_instrument_from_patch(
            instrument_id=instrument_id,
            patch=indicators,
            touch_ts=True,
            session=session,
        )
        await self._db.upsert_candles(
            candle_rows_from_response(
                instrument_id=instrument_id,
                timeframe="day",
                candles_response=candles,
            ),
            session=session,
        )
