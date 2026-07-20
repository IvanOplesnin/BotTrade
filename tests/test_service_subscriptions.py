from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.domains.topics import (
    MARKET_DATA_STREAM_TOPIC,
    PORTFOLIO_STREAM_TOPIC,
    STRATEGY_SIGNAL_TOPIC,
)
from domain.strategies import CandleSubscription, MarketSubscriptionPlan
from main import Service
from runtime.stream_handlers import TelegramStreamHandlers

pytestmark = pytest.mark.asyncio


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

    def apply_plan(self, plan):
        self.plans.append(plan)


class FakeStreamBus:
    def __init__(self):
        self.subscriptions = []

    def subscribe(self, topic, handler):
        self.subscriptions.append((topic, handler))


class FakeHandler:
    async def execute(self, event):
        pass


async def test_refresh_indicators_builds_plan_before_refresh_and_applies_subscriptions():
    plan = MarketSubscriptionPlan(
        last_price_instrument_ids=("UID1",),
        candle_subscriptions=(
            CandleSubscription(instrument_id="UID1", timeframe="day", warmup=10),
        ),
    )
    service = Service.__new__(Service)
    service.strategy_subscription_svc = FakeStrategySubscriptionService(plan)
    service.market_data_refresh_svc = FakeMarketDataRefreshService()
    service.market_subscription_svc = FakeMarketSubscriptionService()

    await service._refresh_indicators_and_subscriptions(update_notify=True)

    assert service.strategy_subscription_svc.calls == 1
    assert service.market_data_refresh_svc.calls == [
        {
            "update_notify": True,
            "subscription_plan": plan,
        }
    ]
    assert service.market_subscription_svc.plans == [plan]


async def test_register_stream_handlers_subscribes_runtime_topics():
    service = Service.__new__(Service)
    service.stream_bus = FakeStreamBus()
    service.config = SimpleNamespace(
        runtime=SimpleNamespace(
            telegram_consumers=["market_data", "portfolio", "strategy_signals"],
        )
    )
    service.stream_handlers = TelegramStreamHandlers(
        market_data_processor=FakeHandler(),
        portfolio_handler=FakeHandler(),
        signal_notification_handler=FakeHandler(),
    )

    service._register_stream_handlers()

    assert service.stream_bus.subscriptions == [
        (MARKET_DATA_STREAM_TOPIC, service.stream_handlers.market_data_processor.execute),
        (PORTFOLIO_STREAM_TOPIC, service.stream_handlers.portfolio_handler.execute),
        (STRATEGY_SIGNAL_TOPIC, service.stream_handlers.signal_notification_handler.execute),
    ]


async def test_register_stream_handlers_honors_split_runtime_config():
    service = Service.__new__(Service)
    service.stream_bus = FakeStreamBus()
    service.config = SimpleNamespace(
        runtime=SimpleNamespace(
            telegram_consumers=["portfolio", "strategy_signals"],
        )
    )
    service.stream_handlers = TelegramStreamHandlers(
        market_data_processor=FakeHandler(),
        portfolio_handler=FakeHandler(),
        signal_notification_handler=FakeHandler(),
    )

    service._register_stream_handlers()

    assert service.stream_bus.subscriptions == [
        (PORTFOLIO_STREAM_TOPIC, service.stream_handlers.portfolio_handler.execute),
        (STRATEGY_SIGNAL_TOPIC, service.stream_handlers.signal_notification_handler.execute),
    ]


async def test_register_stream_handlers_requires_built_handlers():
    service = Service.__new__(Service)
    service.stream_bus = FakeStreamBus()
    service.stream_handlers = None

    with pytest.raises(RuntimeError, match="Call _build_stream_handlers"):
        service._register_stream_handlers()
