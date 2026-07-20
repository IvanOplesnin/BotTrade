from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.domains.topics import SUBSCRIPTION_REFRESH_REQUEST_TOPIC
from runtime import stream_producer as stream_producer_mod
from runtime.stream_producer import StreamProducerService

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


class FakeRuntime:
    trading_time_value = False
    instances = []

    def __init__(self, context):
        self.context = context
        self.started = []
        self.stopped = 0
        self.handled = []
        FakeRuntime.instances.append(self)

    def trading_time(self):
        return self.trading_time_value

    async def start_streams(self, **kwargs):
        self.started.append(dict(kwargs))

    async def stop_streams(self):
        self.stopped += 1

    async def handle_subscription_refresh(self, event):
        self.handled.append(event)


class FakeScheduler:
    def __init__(self, timezone=None):
        self.timezone = timezone
        self.jobs = []
        self.started = False
        self.shutdown_calls = []

    def add_job(self, func, trigger, id, replace_existing):
        self.jobs.append(
            {
                "func": func,
                "trigger": trigger,
                "id": id,
                "replace_existing": replace_existing,
            }
        )

    def start(self):
        self.started = True

    def shutdown(self, wait=False):
        self.shutdown_calls.append(wait)


def _context():
    return SimpleNamespace(
        config=SimpleNamespace(
            scheduler_trading=SimpleNamespace(
                start="09:00",
                close="23:50",
            )
        ),
        db_repo=FakeDb(),
        redis=FakeRedis(),
        stream_bus=FakeBus(),
    )


async def test_stream_producer_starts_bus_and_registers_refresh_consumer(monkeypatch):
    FakeRuntime.instances = []
    monkeypatch.setattr(stream_producer_mod, "TinkoffStreamRuntime", FakeRuntime)
    monkeypatch.setattr(stream_producer_mod, "AsyncIOScheduler", FakeScheduler)
    context = _context()
    service = StreamProducerService(context=context)

    await service.start()
    await service.stop()

    runtime = FakeRuntime.instances[0]
    assert context.db_repo.created is True
    assert context.redis.connected is True
    assert context.stream_bus.started is True
    assert context.stream_bus.stopped is True
    assert context.stream_bus.subscriptions == [
        (SUBSCRIPTION_REFRESH_REQUEST_TOPIC, runtime.handle_subscription_refresh),
    ]
    assert service.scheduler.started is True
    assert [job["id"] for job in service.scheduler.jobs] == [
        "open_if_needed",
        "close_and_stop",
    ]
    assert service.scheduler.shutdown_calls == [False]
    assert runtime.started == []
    assert runtime.stopped == 1


async def test_stream_producer_starts_tinkoff_streams_during_trading_time(monkeypatch):
    FakeRuntime.instances = []

    class TradingRuntime(FakeRuntime):
        trading_time_value = True

    monkeypatch.setattr(stream_producer_mod, "TinkoffStreamRuntime", TradingRuntime)
    monkeypatch.setattr(stream_producer_mod, "AsyncIOScheduler", FakeScheduler)
    service = StreamProducerService(context=_context())

    await service.start()
    await service.stop()

    runtime = FakeRuntime.instances[0]
    assert runtime.started == [{"update_notify": True}]
