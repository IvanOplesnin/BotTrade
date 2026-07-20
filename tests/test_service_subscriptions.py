from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.domains.topics import (
    MARKET_DATA_STREAM_TOPIC,
    PORTFOLIO_STREAM_TOPIC,
    STRATEGY_SIGNAL_TOPIC,
    SUBSCRIPTION_REFRESH_REQUEST_TOPIC,
)
from main import Service
from runtime.stream_handlers import TelegramStreamHandlers

pytestmark = pytest.mark.asyncio


class FakeTinkoffStreamRuntime:
    def __init__(self):
        self.refresh_calls = []
        self.started = 0
        self.stopped = 0

    async def refresh_indicators_and_subscriptions(self, **kwargs):
        self.refresh_calls.append(dict(kwargs))

    async def start_streams(self, **kwargs):
        self.started += 1

    async def stop_streams(self):
        self.stopped += 1

    async def handle_subscription_refresh(self, event):
        pass


class FakeStreamBus:
    def __init__(self):
        self.subscriptions = []

    def subscribe(self, topic, handler):
        self.subscriptions.append((topic, handler))


class FakeHandler:
    async def execute(self, event):
        pass


async def test_refresh_indicators_builds_plan_before_refresh_and_applies_subscriptions():
    service = Service.__new__(Service)
    service.tinkoff_stream_runtime = FakeTinkoffStreamRuntime()

    await service._refresh_indicators_and_subscriptions(update_notify=True)

    assert service.tinkoff_stream_runtime.refresh_calls == [{"update_notify": True}]


async def test_register_stream_handlers_subscribes_runtime_topics():
    service = Service.__new__(Service)
    service.stream_bus = FakeStreamBus()
    service.config = SimpleNamespace(
        runtime=SimpleNamespace(
            telegram_manage_streams=True,
            telegram_consumers=["market_data", "portfolio", "strategy_signals"],
        )
    )
    service.tinkoff_stream_runtime = FakeTinkoffStreamRuntime()
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
        (
            SUBSCRIPTION_REFRESH_REQUEST_TOPIC,
            service.tinkoff_stream_runtime.handle_subscription_refresh,
        ),
    ]


async def test_register_stream_handlers_honors_split_runtime_config():
    service = Service.__new__(Service)
    service.stream_bus = FakeStreamBus()
    service.config = SimpleNamespace(
        runtime=SimpleNamespace(
            telegram_manage_streams=False,
            telegram_consumers=["portfolio", "strategy_signals"],
        )
    )
    service.tinkoff_stream_runtime = FakeTinkoffStreamRuntime()
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
