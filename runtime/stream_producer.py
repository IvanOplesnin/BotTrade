from __future__ import annotations

import asyncio
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.domains.topics import SUBSCRIPTION_REFRESH_REQUEST_TOPIC
from runtime.context import AppContext, build_app_context
from runtime.tinkoff_stream_runtime import TinkoffStreamRuntime
from services.scheduler.scheduler import TZ_DEFAULT, parse_hhmm
from utils.logger import get_logger


class StreamProducerService:
    """Owns Tinkoff gRPC streams and publishes domain events to the message bus."""

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
        self.tinkoff_stream_runtime = TinkoffStreamRuntime(self.context)
        self.scheduler: Optional[AsyncIOScheduler] = AsyncIOScheduler(timezone=TZ_DEFAULT)
        self._stop_event = asyncio.Event()
        self.log = get_logger(self.__class__.__name__)
        self._register_jobs_from_config()

    def _register_jobs_from_config(self) -> None:
        start_t = parse_hhmm(self.config.scheduler_trading.start)
        close_t = parse_hhmm(self.config.scheduler_trading.close)
        self.scheduler.add_job(
            self._job_open_if_needed,
            CronTrigger(hour=start_t.hour, minute=start_t.minute),
            id="open_if_needed",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._job_close_and_stop,
            CronTrigger(hour=close_t.hour, minute=close_t.minute),
            id="close_and_stop",
            replace_existing=True,
        )

    async def _job_open_if_needed(self) -> None:
        await self.tinkoff_stream_runtime.start_streams(update_notify=True)

    async def _job_close_and_stop(self) -> None:
        await self.tinkoff_stream_runtime.stop_streams()

    async def start(self) -> None:
        await self.db_repo.create_schema_if_not_exists()
        self.stream_bus.subscribe(
            SUBSCRIPTION_REFRESH_REQUEST_TOPIC,
            self.tinkoff_stream_runtime.handle_subscription_refresh,
        )
        await self.redis.connect()
        await self.stream_bus.start()
        self.scheduler.start()
        if self.tinkoff_stream_runtime.trading_time():
            await self._job_open_if_needed()
        self.log.info("Started stream producer")

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
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
        await self.tinkoff_stream_runtime.stop_streams()
        await self.stream_bus.stop()
        await self.redis.close()
        self.log.info("Stopped stream producer")
