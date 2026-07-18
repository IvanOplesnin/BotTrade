from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from collections import defaultdict
from typing import Any

from redis.exceptions import ResponseError

from core.domains.event_codec import decode_event, encode_event
from core.domains.message_bus import Handler
from database.redis.client import RedisClient


class RedisStreamBus:
    """Redis Streams message bus with consumer-group based distribution."""

    def __init__(
            self,
            redis: RedisClient,
            *,
            stream_prefix: str = "bottrade:bus",
            group_name: str = "bottrade",
            consumer_name: str | None = None,
            start_id: str = "$",
            batch_size: int = 10,
            block_ms: int = 1000,
            maxlen: int = 10000,
    ):
        self._redis = redis
        self._stream_prefix = stream_prefix.rstrip(":")
        self._group_name = group_name
        self._consumer_name = consumer_name or self._make_consumer_name()
        self._start_id = start_id
        self._batch_size = batch_size
        self._block_ms = block_ms
        self._maxlen = maxlen
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._tasks: dict[str, asyncio.Task] = {}
        self._started = False
        self._log = logging.getLogger(self.__class__.__name__)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)

    async def publish(self, topic: str, data: Any) -> None:
        await self._redis.client.xadd(
            self._stream_key(topic),
            encode_event(data),
            maxlen=self._maxlen,
            approximate=True,
        )

    async def start(self) -> None:
        if self._started:
            return

        for topic in self._handlers:
            await self._ensure_group(topic)
            self._tasks[topic] = asyncio.create_task(
                self._worker(topic),
                name=f"redis-stream-bus:{topic}",
            )
        self._started = True
        self._log.info(
            "Redis stream bus started",
            extra={
                "group": self._group_name,
                "consumer": self._consumer_name,
                "topics": ",".join(sorted(self._handlers)),
            },
        )

    async def stop(self) -> None:
        if not self._started:
            return

        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        self._started = False

    async def _worker(self, topic: str) -> None:
        stream_key = self._stream_key(topic)
        while True:
            try:
                messages = await self._read_messages(stream_key, "0", block_ms=None)
                if not messages:
                    messages = await self._read_messages(stream_key, ">", block_ms=self._block_ms)
            except ResponseError as exc:
                if "NOGROUP" not in str(exc):
                    raise
                self._log.warning(
                    "Redis stream group is missing, recreating",
                    extra={"topic": topic, "group": self._group_name},
                )
                await self._ensure_group(topic)
                continue
            await self._handle_messages(topic, stream_key, messages)

    async def _read_messages(
            self,
            stream_key: str,
            start_id: str,
            block_ms: int | None,
    ) -> list:
        kwargs = {
            "streams": {stream_key: start_id},
            "count": self._batch_size,
        }
        if block_ms is not None:
            kwargs["block"] = block_ms
        messages = await self._redis.client.xreadgroup(
            self._group_name,
            self._consumer_name,
            **kwargs,
        )
        return [
            (stream_name, stream_messages)
            for stream_name, stream_messages in messages
            if stream_messages
        ]

    async def _handle_messages(self, topic: str, stream_key: str, messages: list) -> None:
        for _, stream_messages in messages:
            for message_id, fields in stream_messages:
                await self._handle_message(topic, stream_key, message_id, fields)

    async def _handle_message(
            self,
            topic: str,
            stream_key: str,
            message_id: str,
            fields: dict,
    ) -> None:
        try:
            event = decode_event(fields)
        except Exception:
            self._log.exception(
                "Failed to decode Redis stream event",
                extra={"topic": topic, "message_id": message_id},
            )
            await self._ack(stream_key, message_id)
            return

        for handler in self._handlers.get(topic, []):
            try:
                await handler(event)
            except Exception:
                self._log.exception(
                    "Redis stream handler failed",
                    extra={
                        "topic": topic,
                        "handler": getattr(handler, "__name__", repr(handler)),
                        "message_id": message_id,
                    },
                )

        await self._ack(stream_key, message_id)

    async def _ack(self, stream_key: str, message_id: str) -> None:
        await self._redis.client.xack(stream_key, self._group_name, message_id)

    async def _ensure_group(self, topic: str) -> None:
        try:
            await self._redis.client.xgroup_create(
                self._stream_key(topic),
                self._group_name,
                id=self._start_id,
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _stream_key(self, topic: str) -> str:
        return f"{self._stream_prefix}:{topic.strip(':')}"

    @staticmethod
    def _make_consumer_name() -> str:
        return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
