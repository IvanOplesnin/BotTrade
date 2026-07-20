from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from domain.stream_events import SubscriptionRefreshRequestedEvent
from runtime.context import AppContext
from services.scheduler.scheduler import TZ_DEFAULT, parse_hhmm
from utils.logger import get_logger


class TinkoffStreamRuntime:
    """Core runtime for Tinkoff streams and live market subscriptions."""

    def __init__(self, context: AppContext):
        self.context = context
        self.config = context.config
        self.db_repo = context.db_repo
        self.tclient = context.tclient
        self.strategy_subscription_svc = context.strategy_subscription_svc
        self.market_data_refresh_svc = context.market_data_refresh_svc
        self.market_subscription_svc = context.market_subscription_svc
        self.tz = TZ_DEFAULT
        self._running = False
        self._lock = asyncio.Lock()
        self.log = get_logger(self.__class__.__name__)

    @property
    def is_running(self) -> bool:
        return self._running

    async def start_streams(self, *, update_notify: bool = True) -> None:
        async with self._lock:
            if self._running:
                return
            async with self.db_repo.session_factory() as session:
                accounts = [
                    account.account_id
                    for account in await self.db_repo.list_accounts(session=session)
                ]
            await self.tclient.start(accounts=accounts)
            self._running = True
            await self.refresh_indicators_and_subscriptions(update_notify=update_notify)

    async def stop_streams(self) -> None:
        async with self._lock:
            if not self._running:
                return
            await self.tclient.stop()
            self._running = False

    async def refresh_indicators_and_subscriptions(self, update_notify: bool = False) -> None:
        plan = await self.strategy_subscription_svc.build_plan()
        await self.market_data_refresh_svc.refresh(
            update_notify=update_notify,
            subscription_plan=plan,
        )
        self.market_subscription_svc.apply_plan(plan)

    async def apply_current_subscription_plan(self) -> None:
        plan = await self.strategy_subscription_svc.build_plan()
        self.market_subscription_svc.apply_plan(plan)

    async def handle_subscription_refresh(self, event: Any) -> None:
        if not isinstance(event, SubscriptionRefreshRequestedEvent):
            self.log.debug("Skip unsupported subscription refresh event: %r", event)
            return

        if event.reload_indicators:
            await self.refresh_indicators_and_subscriptions(
                update_notify=event.update_notify,
            )
        else:
            await self.apply_current_subscription_plan()

        if event.refresh_portfolio_stream:
            await self.market_subscription_svc.recreate_portfolio_stream_from_db()

    def trading_time(self) -> bool:
        now = datetime.now(self.tz).time()
        start_t = parse_hhmm(self.config.scheduler_trading.start)
        close_t = parse_hhmm(self.config.scheduler_trading.close)
        return start_t <= now <= close_t
