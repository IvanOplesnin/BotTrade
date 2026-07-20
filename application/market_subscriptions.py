from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from application.ports import AccountStreamRepository, MarketSubscriptionClient
from domain.strategies import MarketSubscriptionPlan
from domain.timeframes import normalize_timeframe

CANDLE_SUBSCRIBE_PREFIX = "candle:"


class MarketSubscriptionSyncService:
    """Keeps live Tinkoff stream subscriptions aligned with strategy needs."""

    def __init__(
            self,
            tclient: MarketSubscriptionClient,
            db: AccountStreamRepository | None = None,
    ):
        self._tclient = tclient
        self._db = db

    def apply_plan(self, plan: MarketSubscriptionPlan) -> None:
        self._sync_last_price_subscriptions(set(plan.last_price_instrument_ids))
        self._sync_candle_subscriptions(_candle_targets(plan))
        self._sync_trade_subscriptions(set(plan.trade_instrument_ids))

    def subscribe_last_prices_if_running(self, instrument_ids: Sequence[str]) -> None:
        ids = tuple(instrument_ids)
        if ids and self._tclient.market_stream_task:
            self._tclient.subscribe_to_instrument_last_price(*ids)

    def unsubscribe_last_prices_if_running(self, instrument_ids: Sequence[str]) -> None:
        ids = tuple(instrument_ids)
        if ids and self._tclient.market_stream_task:
            self._tclient.unsubscribe_to_instrument_last_price(*ids)

    async def recreate_portfolio_stream_from_db(self) -> None:
        if self._db is None:
            raise RuntimeError("Repository is required to recreate portfolio stream")
        if not self._tclient.portfolio_stream_task:
            return

        async with self._db.session_factory() as session:
            account_ids = [
                account.account_id
                for account in await self._db.list_accounts(session=session)
            ]
        await self._tclient.recreate_portfolio_stream(account_ids)

    def _sync_last_price_subscriptions(self, target: set[str]) -> None:
        subscribed = set(self._tclient.subscribes.get("last_price", set()))
        missing = sorted(target - subscribed)
        extra = sorted(subscribed - target)
        if missing:
            self._tclient.subscribe_to_instrument_last_price(*missing)
        if extra:
            self._tclient.unsubscribe_to_instrument_last_price(*extra)

    def _sync_candle_subscriptions(self, target_by_timeframe: dict[str, set[str]]) -> None:
        existing_timeframes = {
            timeframe
            for key in self._tclient.subscribes
            if (timeframe := candle_timeframe_from_key(key)) is not None
        }
        target_timeframes = set(target_by_timeframe)

        for timeframe in sorted(existing_timeframes | target_timeframes):
            subscribed = set(self._tclient.subscribes.get(candle_subscribe_key(timeframe), set()))
            target = set(target_by_timeframe.get(timeframe, set()))
            missing = sorted(target - subscribed)
            extra = sorted(subscribed - target)
            if missing:
                self._tclient.subscribe_to_instrument_candles(timeframe, *missing)
            if extra:
                self._tclient.unsubscribe_to_instrument_candles(timeframe, *extra)

    def _sync_trade_subscriptions(self, target: set[str]) -> None:
        subscribed = set(self._tclient.subscribes.get("trades", set()))
        missing = sorted(target - subscribed)
        extra = sorted(subscribed - target)
        if missing:
            self._tclient.subscribe_to_instrument_trades(*missing)
        if extra:
            self._tclient.unsubscribe_to_instrument_trades(*extra)


def candle_subscribe_key(timeframe: str) -> str:
    return f"{CANDLE_SUBSCRIBE_PREFIX}{normalize_timeframe(timeframe)}"


def candle_timeframe_from_key(key: str) -> str | None:
    if not key.startswith(CANDLE_SUBSCRIBE_PREFIX):
        return None
    return normalize_timeframe(key.removeprefix(CANDLE_SUBSCRIBE_PREFIX))


def _candle_targets(plan: MarketSubscriptionPlan) -> dict[str, set[str]]:
    candle_ids_by_timeframe = defaultdict(set)
    for subscription in plan.candle_subscriptions:
        candle_ids_by_timeframe[normalize_timeframe(subscription.timeframe)].add(
            subscription.instrument_id
        )
    return candle_ids_by_timeframe
