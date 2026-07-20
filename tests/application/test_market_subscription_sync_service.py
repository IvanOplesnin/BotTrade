from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from application.market_subscriptions import (
    MarketSubscriptionRefreshPublisher,
    MarketSubscriptionSyncService,
)
from core.domains.topics import SUBSCRIPTION_REFRESH_REQUEST_TOPIC
from domain.strategies import CandleSubscription, MarketSubscriptionPlan
from domain.stream_events import SubscriptionRefreshRequestedEvent

pytestmark = pytest.mark.asyncio


class FakeTClient:
    def __init__(
            self,
            *,
            subscribes=None,
            market_stream_task=None,
            portfolio_stream_task=None,
    ):
        self.subscribes = subscribes or {}
        self.market_stream_task = market_stream_task
        self.portfolio_stream_task = portfolio_stream_task
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

    async def recreate_portfolio_stream(self, accounts):
        self.calls.append(("recreate_portfolio_stream", tuple(accounts)))


class FakeSession:
    pass


class FakeAccountRepository:
    def __init__(self, account_ids):
        self.account_ids = account_ids
        self.sessions = []

    @asynccontextmanager
    async def session_factory(self):
        session = FakeSession()
        self.sessions.append(session)
        yield session

    async def list_accounts(self, session):
        return [
            SimpleNamespace(account_id=account_id)
            for account_id in self.account_ids
        ]


class FakeBus:
    def __init__(self):
        self.published = []

    def subscribe(self, topic, handler):
        pass

    async def publish(self, topic, data):
        self.published.append((topic, data))

    async def start(self):
        pass

    async def stop(self):
        pass


async def test_apply_plan_adds_missing_and_removes_stale_subscriptions():
    tclient = FakeTClient(
        subscribes={
            "last_price": {"UID1", "OLD_LAST"},
            "candle:day": {"UID1", "OLD_DAY"},
            "candle:5min": {"OLD_5MIN"},
            "trades": {"OLD_TRADE"},
        }
    )
    plan = MarketSubscriptionPlan(
        last_price_instrument_ids=("UID1", "UID2"),
        candle_subscriptions=(
            CandleSubscription(instrument_id="UID1", timeframe="day", warmup=10),
            CandleSubscription(instrument_id="UID3", timeframe="hour", warmup=20),
        ),
        trade_instrument_ids=("UID4",),
    )

    MarketSubscriptionSyncService(tclient).apply_plan(plan)

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


async def test_apply_plan_does_nothing_when_subscriptions_are_current():
    tclient = FakeTClient(
        subscribes={
            "last_price": {"UID1"},
            "candle:day": {"UID1"},
            "trades": {"UID2"},
        }
    )
    plan = MarketSubscriptionPlan(
        last_price_instrument_ids=("UID1",),
        candle_subscriptions=(
            CandleSubscription(instrument_id="UID1", timeframe="day", warmup=10),
        ),
        trade_instrument_ids=("UID2",),
    )

    MarketSubscriptionSyncService(tclient).apply_plan(plan)

    assert tclient.calls == []


async def test_subscribe_last_prices_only_when_market_stream_is_running():
    tclient = FakeTClient(market_stream_task=object())

    MarketSubscriptionSyncService(tclient).subscribe_last_prices_if_running(["UID1"])

    assert tclient.calls == [("subscribe_last_price", ("UID1",))]


async def test_unsubscribe_last_prices_skips_stopped_market_stream():
    tclient = FakeTClient(market_stream_task=None)

    MarketSubscriptionSyncService(tclient).unsubscribe_last_prices_if_running(["UID1"])

    assert tclient.calls == []


async def test_recreate_portfolio_stream_reads_accounts_when_stream_is_running():
    tclient = FakeTClient(portfolio_stream_task=object())
    db = FakeAccountRepository(["ACC1", "ACC2"])

    await MarketSubscriptionSyncService(tclient, db).recreate_portfolio_stream_from_db()

    assert tclient.calls == [("recreate_portfolio_stream", ("ACC1", "ACC2"))]
    assert len(db.sessions) == 1


async def test_recreate_portfolio_stream_skips_stopped_stream():
    tclient = FakeTClient(portfolio_stream_task=None)
    db = FakeAccountRepository(["ACC1"])

    await MarketSubscriptionSyncService(tclient, db).recreate_portfolio_stream_from_db()

    assert tclient.calls == []
    assert db.sessions == []


async def test_refresh_publisher_publishes_subscription_request_event():
    bus = FakeBus()

    await MarketSubscriptionRefreshPublisher(bus).request_refresh(
        reason="account_added",
        instrument_ids=["UID1"],
        account_ids=["ACC1"],
        refresh_portfolio_stream=True,
        reload_indicators=True,
        update_notify=True,
    )

    assert len(bus.published) == 1
    topic, event = bus.published[0]
    assert topic == SUBSCRIPTION_REFRESH_REQUEST_TOPIC
    assert isinstance(event, SubscriptionRefreshRequestedEvent)
    assert event.reason == "account_added"
    assert event.instrument_ids == ("UID1",)
    assert event.account_ids == ("ACC1",)
    assert event.refresh_portfolio_stream is True
    assert event.reload_indicators is True
    assert event.update_notify is True
    assert event.requested_at is not None
