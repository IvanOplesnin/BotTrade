from __future__ import annotations

import pytest

from core.domains.topics import MARKET_DATA_STREAM_TOPIC
from runtime.market_worker import MarketWorkerService

pytestmark = pytest.mark.asyncio


class FakeDb:
    def __init__(self):
        self.created = False

    async def create_schema_if_not_exists(self):
        self.created = True


class FakeRedis:
    def __init__(self):
        self.connected = False
        self.closed = False

    async def connect(self):
        self.connected = True

    async def close(self):
        self.closed = True


class FakeBus:
    def __init__(self):
        self.subscriptions = []
        self.started = False
        self.stopped = False

    def subscribe(self, topic, handler):
        self.subscriptions.append((topic, handler))

    async def publish(self, topic, data):
        pass

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


class FakeContext:
    def __init__(self):
        self.config = object()
        self.db_repo = FakeDb()
        self.redis = FakeRedis()
        self.stream_bus = FakeBus()
        self.market_candle_svc = object()


async def test_market_worker_start_registers_market_consumer_and_starts_bus():
    context = FakeContext()
    worker = MarketWorkerService(context=context)

    await worker.start()

    assert context.db_repo.created is True
    assert context.redis.connected is True
    assert context.stream_bus.started is True
    assert worker.handlers is not None
    assert context.stream_bus.subscriptions == [
        (MARKET_DATA_STREAM_TOPIC, worker.handlers.market_data_processor.execute),
    ]


async def test_market_worker_stop_stops_bus_and_closes_redis():
    context = FakeContext()
    worker = MarketWorkerService(context=context)

    await worker.stop()

    assert context.stream_bus.stopped is True
    assert context.redis.closed is True


async def test_market_worker_run_stops_when_requested():
    context = FakeContext()
    worker = MarketWorkerService(context=context)
    worker.request_stop()

    await worker.run()

    assert context.stream_bus.started is True
    assert context.stream_bus.stopped is True
    assert context.redis.closed is True
