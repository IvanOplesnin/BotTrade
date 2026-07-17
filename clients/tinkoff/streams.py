from __future__ import annotations

import asyncio
from typing import Optional

from clients.tinkoff.sdk import AsyncMarketDataStreamManager, AsyncServices, ti
from clients.tinkoff.stream_mappers import (
    market_data_response_to_event,
    portfolio_stream_response_to_event,
)
from core.domains.message_bus import MessageBus
from utils import logger as app_logger


class TinkoffStreamManager:
    """Owns T-Bank stream tasks and subscriptions.

    The manager does not open or close the SDK client. It works with an already
    entered AsyncServices instance supplied by TClient.
    """

    def __init__(
            self,
            *,
            stream_bus: Optional[MessageBus] = None,
            sandbox: bool = False,
            log=None,
    ):
        self._stream_bus = stream_bus
        self._sandbox = sandbox
        self._api: Optional[AsyncServices] = None
        self._stream_market: Optional[AsyncMarketDataStreamManager] = None
        self.market_stream_task: Optional[asyncio.Task] = None
        self.portfolio_stream_task: Optional[asyncio.Task] = None
        self.subscribes: dict[str, set[str]] = {}
        self.logger = log or app_logger.get_logger(self.__class__.__name__)

    async def start(self, api: AsyncServices, accounts: list[str]) -> None:
        self._api = api
        self._stream_market = None
        self.market_stream_task = asyncio.create_task(self._listen_market_stream())
        if accounts and not self._sandbox:
            self.portfolio_stream_task = asyncio.create_task(
                self._listen_portfolio_stream(accounts=accounts)
            )
        self.logger.info("Started Tinkoff streams")

    async def stop(self) -> None:
        await self._cancel_task("market", "market_stream_task")

        if self._stream_market is not None:
            self._stream_market.stop()
            self._stream_market = None

        await self._cancel_task("portfolio", "portfolio_stream_task")
        self._api = None
        self.logger.info("Stopped Tinkoff streams")

    async def recreate_portfolio_stream(self, accounts: list[str]) -> None:
        if self._sandbox:
            return

        await self._cancel_task("portfolio", "portfolio_stream_task")
        if accounts and self._api is not None:
            self.portfolio_stream_task = asyncio.create_task(
                self._listen_portfolio_stream(accounts=accounts)
            )

    def subscribe_to_instrument_last_price(self, *instruments_id: str) -> None:
        if not instruments_id:
            return

        self.logger.debug(
            "Subscribing to instrument_last_price",
            extra={"instruments_ids": ", ".join(instruments_id)},
        )
        self.subscribes.setdefault("last_price", set()).update(instruments_id)

        if self._stream_market is not None:
            self._stream_market.last_price.subscribe(
                instruments=[
                    ti.LastPriceInstrument(instrument_id=instrument_id)
                    for instrument_id in instruments_id
                ]
            )

    def unsubscribe_to_instrument_last_price(self, *instruments_id: str) -> None:
        if not instruments_id:
            return

        self.logger.debug(
            "Unsubscribing to instrument_last_price",
            extra={"instruments_ids": ", ".join(instruments_id)},
        )
        subscribed = self.subscribes.get("last_price")
        if subscribed is not None:
            for instrument_id in instruments_id:
                subscribed.discard(instrument_id)

        if self._stream_market is not None:
            self._stream_market.last_price.unsubscribe(
                instruments=[
                    ti.LastPriceInstrument(instrument_id=instrument_id)
                    for instrument_id in instruments_id
                ]
            )

    async def _listen_market_stream(self) -> None:
        backoff = 1
        while self._api is not None:
            try:
                if self._stream_market is None:
                    self._stream_market = self._api.create_market_data_stream()
                    self._apply_last_price_subscriptions()

                async for response in self._stream_market:
                    await self._publish_market_response(response)
                backoff = 1

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.error("Stream MarketDS error", extra={"exception": exc})
                try:
                    if self._stream_market is not None:
                        self._stream_market.stop()
                finally:
                    self._stream_market = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _listen_portfolio_stream(self, accounts: list[str]) -> None:
        backoff = 1
        while self._api is not None:
            try:
                self.logger.info(
                    "Start portfolio stream for accounts",
                    extra={"account_id": ",".join(accounts)},
                )
                async for response in self._api.operations_stream.portfolio_stream(
                        accounts=accounts
                ):
                    await self._publish_portfolio_response(response)
                backoff = 1

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.error("Portfolio Stream error", extra={"exception": exc})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _publish_market_response(self, response: ti.MarketDataResponse) -> None:
        event = market_data_response_to_event(response)
        if event is None:
            self.logger.debug(
                "Skip market stream response",
                extra={"response": response.__class__.__name__},
            )
            return

        if self._stream_bus is None:
            self.logger.debug(
                "Received market event",
                extra={"event": event.__class__.__name__},
            )
            return

        try:
            await self._stream_bus.publish("market_data_stream", event)
        except asyncio.QueueFull:
            self.logger.warning(
                "Queue full, drop market event",
                extra={"event": event.__class__.__name__},
            )

    async def _publish_portfolio_response(self, response: ti.PortfolioStreamResponse) -> None:
        event = portfolio_stream_response_to_event(response)
        if event is None:
            self.logger.debug(
                "Skip portfolio stream response",
                extra={"response": response.__class__.__name__},
            )
            return

        if self._stream_bus is None:
            self.logger.debug(
                "Received portfolio event",
                extra={"event": event.__class__.__name__},
            )
            return

        try:
            await self._stream_bus.publish("portfolio_stream", event)
        except asyncio.QueueFull:
            self.logger.warning(
                "Queue full, drop portfolio event",
                extra={"event": event.__class__.__name__},
            )

    def _apply_last_price_subscriptions(self) -> None:
        instrument_ids = sorted(self.subscribes.get("last_price", set()))
        if not instrument_ids or self._stream_market is None:
            return

        self.logger.info(
            "Subscribing to instrument_last_price",
            extra={"instruments_id": ", ".join(instrument_ids)},
        )
        self._stream_market.last_price.subscribe(
            instruments=[
                ti.LastPriceInstrument(instrument_id=instrument_id)
                for instrument_id in instrument_ids
            ]
        )

    async def _cancel_task(self, title: str, attr_name: str) -> None:
        task = getattr(self, attr_name)
        if task is None:
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            self.logger.info("%s stream stopping", title)
        finally:
            setattr(self, attr_name, None)
