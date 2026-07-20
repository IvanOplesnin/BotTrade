from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from domain.strategies import MarketSubscriptionPlan
from domain.stream_events import LastPriceEvent, SubscriptionRefreshRequestedEvent
from runtime.tinkoff_stream_runtime import TinkoffStreamRuntime

pytestmark = pytest.mark.asyncio


class FakeDb:
    def __init__(self, account_ids=None):
        self.account_ids = account_ids or []
        self.sessions = []

    @asynccontextmanager
    async def session_factory(self):
        session = object()
        self.sessions.append(session)
        yield session

    async def list_accounts(self, session):
        return [
            SimpleNamespace(account_id=account_id)
            for account_id in self.account_ids
        ]


class FakeTClient:
    def __init__(self):
        self.started_accounts = []
        self.stop_calls = 0

    async def start(self, accounts):
        self.started_accounts.append(list(accounts))

    async def stop(self):
        self.stop_calls += 1


class FakeStrategySubscriptionService:
    def __init__(self, plan):
        self.plan = plan
        self.calls = 0

    async def build_plan(self):
        self.calls += 1
        return self.plan


class FakeMarketDataRefreshService:
    def __init__(self):
        self.calls = []

    async def refresh(self, **kwargs):
        self.calls.append(dict(kwargs))


class FakeMarketSubscriptionService:
    def __init__(self):
        self.plans = []
        self.recreate_calls = 0

    def apply_plan(self, plan):
        self.plans.append(plan)

    async def recreate_portfolio_stream_from_db(self):
        self.recreate_calls += 1


def _context(plan):
    return SimpleNamespace(
        config=SimpleNamespace(
            scheduler_trading=SimpleNamespace(
                start="09:00",
                close="23:50",
            )
        ),
        db_repo=FakeDb(["ACC1", "ACC2"]),
        tclient=FakeTClient(),
        strategy_subscription_svc=FakeStrategySubscriptionService(plan),
        market_data_refresh_svc=FakeMarketDataRefreshService(),
        market_subscription_svc=FakeMarketSubscriptionService(),
    )


async def test_start_streams_starts_tclient_and_refreshes_subscriptions():
    plan = MarketSubscriptionPlan(last_price_instrument_ids=("UID1",))
    context = _context(plan)
    runtime = TinkoffStreamRuntime(context)

    await runtime.start_streams(update_notify=True)
    await runtime.start_streams(update_notify=True)

    assert runtime.is_running is True
    assert context.tclient.started_accounts == [["ACC1", "ACC2"]]
    assert context.strategy_subscription_svc.calls == 1
    assert context.market_data_refresh_svc.calls == [
        {
            "update_notify": True,
            "subscription_plan": plan,
        }
    ]
    assert context.market_subscription_svc.plans == [plan]


async def test_stop_streams_stops_tclient_once():
    plan = MarketSubscriptionPlan()
    context = _context(plan)
    runtime = TinkoffStreamRuntime(context)

    await runtime.start_streams()
    await runtime.stop_streams()
    await runtime.stop_streams()

    assert runtime.is_running is False
    assert context.tclient.stop_calls == 1


async def test_handle_subscription_refresh_applies_current_plan_and_recreates_portfolio():
    plan = MarketSubscriptionPlan(last_price_instrument_ids=("UID1",))
    context = _context(plan)
    runtime = TinkoffStreamRuntime(context)

    await runtime.handle_subscription_refresh(
        SubscriptionRefreshRequestedEvent(
            reason="account_added",
            refresh_portfolio_stream=True,
        )
    )

    assert context.strategy_subscription_svc.calls == 1
    assert context.market_data_refresh_svc.calls == []
    assert context.market_subscription_svc.plans == [plan]
    assert context.market_subscription_svc.recreate_calls == 1


async def test_handle_subscription_refresh_can_reload_indicators():
    plan = MarketSubscriptionPlan(last_price_instrument_ids=("UID1",))
    context = _context(plan)
    runtime = TinkoffStreamRuntime(context)

    await runtime.handle_subscription_refresh(
        SubscriptionRefreshRequestedEvent(
            reason="manual",
            reload_indicators=True,
            update_notify=True,
        )
    )

    assert context.market_data_refresh_svc.calls == [
        {
            "update_notify": True,
            "subscription_plan": plan,
        }
    ]
    assert context.market_subscription_svc.plans == [plan]


async def test_handle_subscription_refresh_skips_unknown_events():
    plan = MarketSubscriptionPlan()
    context = _context(plan)
    runtime = TinkoffStreamRuntime(context)

    await runtime.handle_subscription_refresh(LastPriceEvent)

    assert context.strategy_subscription_svc.calls == 0
