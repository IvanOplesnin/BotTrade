from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from application.candles import candle_rows_from_response
from application.dto import MarketDataRefreshResult
from application.ports import MarketDataClient, MarketDataRefreshRepository
from application.strategy_state import StrategyStateService
from domain.strategies import CandleSubscription, MarketSubscriptionPlan
from domain.timeframes import normalize_timeframe
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
            subscription_plan: MarketSubscriptionPlan | None = None,
    ) -> MarketDataRefreshResult:
        if subscription_plan is None:
            return await self._refresh_legacy(update_notify=update_notify)
        return await self._refresh_by_plan(
            subscription_plan,
            update_notify=update_notify,
        )

    async def _refresh_legacy(
            self,
            *,
            update_notify: bool,
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

    async def _refresh_by_plan(
            self,
            plan: MarketSubscriptionPlan,
            *,
            update_notify: bool,
    ) -> MarketDataRefreshResult:
        async with self._db.session_factory() as session:
            instruments = await self._db.list_instruments(session)
            instruments_by_id = {
                instrument.instrument_id: instrument
                for instrument in instruments
            }
            refreshed_ids: set[str] = set()
            now = datetime.now(self._tz)
            for subscription in plan.candle_subscriptions:
                instrument = instruments_by_id.get(subscription.instrument_id)
                if instrument is None:
                    continue
                if not await self._needs_backfill(
                        instrument,
                        subscription,
                        now=now,
                        session=session,
                ):
                    continue

                await self._backfill_subscription(
                    subscription,
                    update_notify=update_notify,
                    session=session,
                )
                refreshed_ids.add(subscription.instrument_id)
            await session.commit()

        strategy_state = await self._strategy_state_svc.refresh_all()
        return MarketDataRefreshResult(
            refreshed_instrument_ids=sorted(refreshed_ids),
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

    async def _needs_backfill(
            self,
            instrument: Any,
            subscription: CandleSubscription,
            *,
            now: datetime,
            session: Any,
    ) -> bool:
        if not is_updated_today(instrument.last_update, now, self._tz):
            return True

        candles = await self._db.list_candles(
            instrument_id=subscription.instrument_id,
            timeframe=normalize_timeframe(subscription.timeframe),
            limit=subscription.warmup,
            session=session,
        )
        return len(candles) < subscription.warmup

    async def _backfill_subscription(
            self,
            subscription: CandleSubscription,
            *,
            update_notify: bool,
            session: Any,
    ) -> None:
        timeframe = normalize_timeframe(subscription.timeframe)
        candles = await self._market_data_client.get_candles_for_backfill(
            subscription.instrument_id,
            timeframe=timeframe,
            warmup=subscription.warmup,
        )
        await self._db.upsert_candles(
            candle_rows_from_response(
                instrument_id=subscription.instrument_id,
                timeframe=timeframe,
                candles_response=candles,
            ),
            session=session,
        )

        if timeframe != "day":
            return

        indicators = IndicatorCalculator(candles).build_instrument_update()
        if update_notify:
            indicators["to_notify"] = True
        await self._db.update_instrument_from_patch(
            instrument_id=subscription.instrument_id,
            patch=indicators,
            touch_ts=True,
            session=session,
        )
