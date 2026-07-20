from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.domains.topics import (
    MARKET_DATA_STREAM_TOPIC,
    PORTFOLIO_STREAM_TOPIC,
    STRATEGY_SIGNAL_TOPIC,
)
from runtime.stream_handlers import (
    MarketStreamHandlers,
    TelegramStreamHandlers,
    build_telegram_stream_handlers,
    register_market_stream_handlers,
    register_telegram_stream_handlers,
)


class FakeBus:
    def __init__(self):
        self.subscriptions = []

    def subscribe(self, topic, handler):
        self.subscriptions.append((topic, handler))


class FakeHandler:
    async def execute(self, event):
        pass


def test_register_market_stream_handlers_subscribes_market_topic():
    bus = FakeBus()
    handlers = MarketStreamHandlers(market_data_processor=FakeHandler())

    register_market_stream_handlers(bus, handlers)

    assert bus.subscriptions == [
        (MARKET_DATA_STREAM_TOPIC, handlers.market_data_processor.execute),
    ]


def test_register_telegram_stream_handlers_subscribes_runtime_topics():
    bus = FakeBus()
    handlers = TelegramStreamHandlers(
        market_data_processor=FakeHandler(),
        portfolio_handler=FakeHandler(),
        signal_notification_handler=FakeHandler(),
    )

    register_telegram_stream_handlers(bus, handlers)

    assert bus.subscriptions == [
        (MARKET_DATA_STREAM_TOPIC, handlers.market_data_processor.execute),
        (PORTFOLIO_STREAM_TOPIC, handlers.portfolio_handler.execute),
        (STRATEGY_SIGNAL_TOPIC, handlers.signal_notification_handler.execute),
    ]


def test_register_telegram_stream_handlers_can_skip_market_topic():
    bus = FakeBus()
    handlers = TelegramStreamHandlers(
        market_data_processor=FakeHandler(),
        portfolio_handler=FakeHandler(),
        signal_notification_handler=FakeHandler(),
    )

    register_telegram_stream_handlers(
        bus,
        handlers,
        consumers=["portfolio", "strategy_signals"],
    )

    assert bus.subscriptions == [
        (PORTFOLIO_STREAM_TOPIC, handlers.portfolio_handler.execute),
        (STRATEGY_SIGNAL_TOPIC, handlers.signal_notification_handler.execute),
    ]


@pytest.mark.asyncio
async def test_build_telegram_stream_handlers_wires_context_dependencies():
    bot = object()
    context = SimpleNamespace(
        config=SimpleNamespace(tg_bot=SimpleNamespace(chat_id=42)),
        db_repo=object(),
        redis=object(),
        stream_bus=object(),
        market_candle_svc=object(),
        name_service=object(),
        tclient=object(),
        portfolio_svc=object(),
        portfolio_sync_svc=object(),
    )

    handlers = await build_telegram_stream_handlers(context, bot)

    assert handlers.market_data_processor._db is context.db_repo
    assert handlers.market_data_processor._redis is context.redis
    assert handlers.market_data_processor._notification_bus is context.stream_bus
    assert handlers.market_data_processor._candle_service is context.market_candle_svc
    assert handlers.portfolio_handler._bot is bot
    assert handlers.portfolio_handler._chat_id == 42
    assert handlers.portfolio_handler._sync_svc is context.portfolio_sync_svc
    assert handlers.signal_notification_handler._bot is bot
    assert handlers.signal_notification_handler._chat_id == 42
    assert handlers.signal_notification_handler._portfolio_svc is context.portfolio_svc
