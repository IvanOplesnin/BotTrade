from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from redis.exceptions import ResponseError

from core.domains.event_codec import decode_event, encode_event
from core.domains.redis_stream_bus import RedisStreamBus
from domain.stream_events import (
    LastPriceEvent,
    PortfolioPositionEvent,
    PortfolioSnapshotEvent,
)

pytestmark = pytest.mark.asyncio


class FakeRedis:
    def __init__(self):
        self.xadds = []
        self.groups = []
        self.acks = []
        self.group_error = None
        self.xreadgroup_response = []
        self.xreadgroup_effects = []

    async def xadd(self, name, fields, maxlen, approximate):
        self.xadds.append(
            {
                "name": name,
                "fields": fields,
                "maxlen": maxlen,
                "approximate": approximate,
            }
        )

    async def xgroup_create(self, name, groupname, id, mkstream):
        self.groups.append(
            {
                "name": name,
                "groupname": groupname,
                "id": id,
                "mkstream": mkstream,
            }
        )
        if self.group_error is not None:
            raise self.group_error

    async def xack(self, name, groupname, message_id):
        self.acks.append((name, groupname, message_id))

    async def xreadgroup(self, groupname, consumername, **kwargs):
        if self.xreadgroup_effects:
            effect = self.xreadgroup_effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            return effect
        return self.xreadgroup_response


class FakeRedisClient:
    def __init__(self, client):
        self._client = client

    @property
    def client(self):
        return self._client


def _bus(fake):
    return RedisStreamBus(
        FakeRedisClient(fake),
        stream_prefix="bt:bus",
        group_name="group1",
        consumer_name="consumer1",
        start_id="$",
        maxlen=42,
    )


async def test_publish_writes_serialized_event_to_topic_stream():
    fake = FakeRedis()
    bus = _bus(fake)
    event = LastPriceEvent(
        instrument_id="UID1",
        price=Decimal("123.45"),
        time=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )

    await bus.publish("market_data_stream", event)

    assert len(fake.xadds) == 1
    call = fake.xadds[0]
    assert call["name"] == "bt:bus:market_data_stream"
    assert call["maxlen"] == 42
    assert call["approximate"] is True
    assert decode_event(call["fields"]) == event


async def test_handle_message_runs_handlers_and_acks_message():
    fake = FakeRedis()
    bus = _bus(fake)
    seen = []
    event = PortfolioSnapshotEvent(
        account_id="ACC1",
        positions=(PortfolioPositionEvent("UID1", "SBER", 2),),
    )

    async def handler(event):
        seen.append(event)

    bus.subscribe("portfolio_stream", handler)

    await bus._handle_message(
        "portfolio_stream",
        "bt:bus:portfolio_stream",
        "1-0",
        encode_event(event),
    )

    assert seen == [event]
    assert fake.acks == [("bt:bus:portfolio_stream", "group1", "1-0")]


async def test_ensure_group_ignores_existing_group_error():
    fake = FakeRedis()
    fake.group_error = ResponseError("BUSYGROUP Consumer Group name already exists")
    bus = _bus(fake)

    await bus._ensure_group("market_data_stream")

    assert fake.groups == [
        {
            "name": "bt:bus:market_data_stream",
            "groupname": "group1",
            "id": "$",
            "mkstream": True,
        }
    ]


async def test_read_messages_filters_empty_stream_batches():
    fake = FakeRedis()
    fake.xreadgroup_response = [["bt:bus:market_data_stream", []]]
    bus = _bus(fake)

    messages = await bus._read_messages(
        "bt:bus:market_data_stream",
        "0",
        block_ms=None,
    )

    assert messages == []


async def test_worker_recreates_group_when_redis_reports_nogroup():
    fake = FakeRedis()
    fake.xreadgroup_effects = [
        ResponseError(
            "NOGROUP No such key 'bt:bus:market_data_stream' "
            "or consumer group 'group1' in XREADGROUP with GROUP option"
        ),
        asyncio.CancelledError(),
    ]
    bus = _bus(fake)

    with pytest.raises(asyncio.CancelledError):
        await bus._worker("market_data_stream")

    assert fake.groups == [
        {
            "name": "bt:bus:market_data_stream",
            "groupname": "group1",
            "id": "$",
            "mkstream": True,
        }
    ]
