from __future__ import annotations

import asyncio

from runtime.context import AppContext, build_app_context
from runtime.stream_handlers import (
    MarketStreamHandlers,
    build_market_stream_handlers,
    register_market_stream_handlers,
)
from utils.logger import get_logger


class MarketWorkerService:
    """Consumes market-data events from the message bus and runs strategy logic."""

    def __init__(
            self,
            config_path: str = "config.yaml",
            *,
            context: AppContext | None = None,
            message_bus_consumer: str | None = None,
    ):
        self.context = context or build_app_context(
            config_path,
            message_bus_consumer=message_bus_consumer,
        )
        self.config = self.context.config
        self.db_repo = self.context.db_repo
        self.redis = self.context.redis
        self.stream_bus = self.context.stream_bus
        self.handlers: MarketStreamHandlers | None = None
        self.log = get_logger(self.__class__.__name__)
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        await self.db_repo.create_schema_if_not_exists()
        self.handlers = await build_market_stream_handlers(self.context)
        register_market_stream_handlers(self.stream_bus, self.handlers)
        await self.redis.connect()
        await self.stream_bus.start()
        self.log.info("Started market worker")

    async def run_until_stopped(self) -> None:
        await self._stop_event.wait()

    async def run(self) -> None:
        await self.start()
        try:
            await self.run_until_stopped()
        finally:
            await self.stop()

    def request_stop(self) -> None:
        self._stop_event.set()

    async def stop(self) -> None:
        await self.stream_bus.stop()
        await self.redis.close()
        self.log.info("Stopped market worker")
