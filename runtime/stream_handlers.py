from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from aiogram import Bot

from bots.tg_bot.signal_notifications import TelegramSignalNotificationHandler
from core.domains.message_bus import MessageBus
from core.domains.topics import (
    MARKET_DATA_STREAM_TOPIC,
    PORTFOLIO_STREAM_TOPIC,
    STRATEGY_SIGNAL_TOPIC,
)
from core.schemas.market_proc import MarketDataHandler
from core.schemas.portfolio import PortfolioHandler
from runtime.context import AppContext

TelegramStreamConsumer = Literal["market_data", "portfolio", "strategy_signals"]
DEFAULT_TELEGRAM_STREAM_CONSUMERS: tuple[TelegramStreamConsumer, ...] = (
    "market_data",
    "portfolio",
    "strategy_signals",
)


@dataclass
class MarketStreamHandlers:
    market_data_processor: MarketDataHandler


@dataclass
class TelegramStreamHandlers(MarketStreamHandlers):
    portfolio_handler: PortfolioHandler
    signal_notification_handler: TelegramSignalNotificationHandler


async def build_market_stream_handlers(context: AppContext) -> MarketStreamHandlers:
    return MarketStreamHandlers(
        market_data_processor=await MarketDataHandler.create(
            db=context.db_repo,
            redis=context.redis,
            candle_service=context.market_candle_svc,
            notification_bus=context.stream_bus,
        )
    )


async def build_telegram_stream_handlers(
        context: AppContext,
        bot: Bot,
) -> TelegramStreamHandlers:
    market_handlers = await build_market_stream_handlers(context)
    return TelegramStreamHandlers(
        market_data_processor=market_handlers.market_data_processor,
        signal_notification_handler=TelegramSignalNotificationHandler(
            bot,
            chat_id=context.config.tg_bot.chat_id,
            db=context.db_repo,
            name_service=context.name_service,
            tclient=context.tclient,
            portfolio_svc=context.portfolio_svc,
        ),
        portfolio_handler=PortfolioHandler(
            bot,
            chat_id=context.config.tg_bot.chat_id,
            db=context.db_repo,
            name_service=context.name_service,
            tclient=context.tclient,
            portfolio_sync_svc=context.portfolio_sync_svc,
        ),
    )


def register_market_stream_handlers(
        bus: MessageBus,
        handlers: MarketStreamHandlers,
) -> None:
    bus.subscribe(MARKET_DATA_STREAM_TOPIC, handlers.market_data_processor.execute)


def register_telegram_stream_handlers(
        bus: MessageBus,
        handlers: TelegramStreamHandlers,
        *,
        consumers: Sequence[TelegramStreamConsumer] = DEFAULT_TELEGRAM_STREAM_CONSUMERS,
) -> None:
    consumer_set = set(consumers)
    if "market_data" in consumer_set:
        register_market_stream_handlers(bus, handlers)
    if "portfolio" in consumer_set:
        bus.subscribe(PORTFOLIO_STREAM_TOPIC, handlers.portfolio_handler.execute)
    if "strategy_signals" in consumer_set:
        bus.subscribe(STRATEGY_SIGNAL_TOPIC, handlers.signal_notification_handler.execute)
