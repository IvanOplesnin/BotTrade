from __future__ import annotations

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


class FakeTClient:
    def __init__(self, subscribes=None):
        self.subscribes = subscribes or {}
        self.calls = []

    def subscribe_to_instrument_last_price(self, *instrument_ids):
        self.calls.append(("subscribe_last_price", tuple(instrument_ids)))
        self.subscribes.setdefault("last_price", set()).update(instrument_ids)

    def unsubscribe_to_instrument_last_price(self, *instrument_ids):
        self.calls.append(("unsubscribe_last_price", tuple(instrument_ids)))
        for instrument_id in instrument_ids:
            self.subscribes.setdefault("last_price", set()).discard(instrument_id)

    def subscribe_to_instrument_candles(self, timeframe, *instrument_ids):
        self.calls.append(("subscribe_candles", timeframe, tuple(instrument_ids)))
        self.subscribes.setdefault(f"candle:{timeframe}", set()).update(instrument_ids)

    def unsubscribe_to_instrument_candles(self, timeframe, *instrument_ids):
        self.calls.append(("unsubscribe_candles", timeframe, tuple(instrument_ids)))
        for instrument_id in instrument_ids:
            self.subscribes.setdefault(f"candle:{timeframe}", set()).discard(instrument_id)

    def subscribe_to_instrument_trades(self, *instrument_ids):
        self.calls.append(("subscribe_trades", tuple(instrument_ids)))
        self.subscribes.setdefault("trades", set()).update(instrument_ids)

    def unsubscribe_to_instrument_trades(self, *instrument_ids):
        self.calls.append(("unsubscribe_trades", tuple(instrument_ids)))
        for instrument_id in instrument_ids:
            self.subscribes.setdefault("trades", set()).discard(instrument_id)


def _service_with_tclient(tclient):
    service = Service.__new__(Service)
    service.tclient = tclient
    return service


async def test_apply_market_subscription_plan_adds_missing_and_removes_stale_subscriptions():
    tclient = FakeTClient(
        subscribes={
            "last_price": {"UID1", "OLD_LAST"},
            "candle:day": {"UID1", "OLD_DAY"},
            "candle:5min": {"OLD_5MIN"},
            "trades": {"OLD_TRADE"},
        }
    )
    service = _service_with_tclient(tclient)
    plan = MarketSubscriptionPlan(
        last_price_instrument_ids=("UID1", "UID2"),
        candle_subscriptions=(
            CandleSubscription(instrument_id="UID1", timeframe="day", warmup=10),
            CandleSubscription(instrument_id="UID3", timeframe="hour", warmup=20),
        ),
        trade_instrument_ids=("UID4",),
    )

    service._apply_market_subscription_plan(plan)

    assert tclient.calls == [
        ("subscribe_last_price", ("UID2",)),
        ("unsubscribe_last_price", ("OLD_LAST",)),
        ("unsubscribe_candles", "5min", ("OLD_5MIN",)),
        ("unsubscribe_candles", "day", ("OLD_DAY",)),
        ("subscribe_candles", "hour", ("UID3",)),
        ("subscribe_trades", ("UID4",)),
        ("unsubscribe_trades", ("OLD_TRADE",)),
    ]
    assert tclient.subscribes["last_price"] == {"UID1", "UID2"}
    assert tclient.subscribes["candle:day"] == {"UID1"}
    assert tclient.subscribes["candle:5min"] == set()
    assert tclient.subscribes["candle:hour"] == {"UID3"}
    assert tclient.subscribes["trades"] == {"UID4"}


async def test_apply_market_subscription_plan_does_nothing_when_subscriptions_are_current():
    tclient = FakeTClient(
        subscribes={
            "last_price": {"UID1"},
            "candle:day": {"UID1"},
            "trades": {"UID2"},
        }
    )
    service = _service_with_tclient(tclient)
    plan = MarketSubscriptionPlan(
        last_price_instrument_ids=("UID1",),
        candle_subscriptions=(
            CandleSubscription(instrument_id="UID1", timeframe="day", warmup=10),
        ),
        trade_instrument_ids=("UID2",),
    )

    service._apply_market_subscription_plan(plan)

    assert tclient.calls == []


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
    service = _service_with_tclient(FakeTClient())
    service.strategy_subscription_svc = FakeStrategySubscriptionService(plan)
    service.market_data_refresh_svc = FakeMarketDataRefreshService()

    await service._refresh_indicators_and_subscriptions(update_notify=True)

    assert service.strategy_subscription_svc.calls == 1
    assert service.market_data_refresh_svc.calls == [
        {
            "update_notify": True,
            "subscription_plan": plan,
        }
    ]
    assert service.tclient.calls == [
        ("subscribe_last_price", ("UID1",)),
        ("subscribe_candles", "day", ("UID1",)),
    ]


async def test_register_stream_handlers_subscribes_runtime_topics():
    service = Service.__new__(Service)
    service.stream_bus = FakeStreamBus()
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


async def test_register_stream_handlers_requires_built_handlers():
    service = Service.__new__(Service)
    service.stream_bus = FakeStreamBus()
    service.stream_handlers = None

    with pytest.raises(RuntimeError, match="Call _build_stream_handlers"):
        service._register_stream_handlers()
