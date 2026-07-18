import logging
from dataclasses import dataclass
from typing import Any, Optional

from aiogram import Bot
from aiogram.types import LinkPreviewOptions

from bots.tg_bot.messages.instruments import text_favorites_breakout, text_stop_long_position, \
    text_stop_short_position
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from clients.tinkoff.portfolio_svc import PortfolioService, PortfolioOut
from clients.tinkoff.sdk import GetFuturesMarginResponse, q2d
from database.pgsql.enums import Direction  # noqa: F401 - kept for existing tests monkeypatching
from database.pgsql.repository import Repository
from database.redis.client import RedisClient
from domain.signals import MarketSignal, SignalKind, decide_market_signal
from domain.stream_events import (
    CandleEvent,
    LastPriceEvent,
    LastPriceSubscriptionEvent,
    MarketDataEvent,
    TradeEvent,
)


@dataclass(frozen=True)
class _MarketContext:
    indicators: Any
    position_direction: Optional[str]
    last_price: float


class MarketDataHandler:
    def __init__(self, bot: Bot, chat_id: int, db: Repository, name_service: NameService,
                 portfolio_svc: PortfolioService,
                 tclient: TClient, redis: RedisClient, acc_id: str):
        self._bot = bot
        self._chat_id = chat_id
        self.log = logging.getLogger(self.__class__.__name__)
        self._db = db
        self._name_service = name_service
        self._tclient = tclient
        self._redis = redis
        self._portfolio_svc = portfolio_svc
        self._acc_id = acc_id

    @classmethod
    async def create(cls, bot: Bot, chat_id: int, db: Repository, name_service: NameService,
                     tclient: TClient, redis: RedisClient, portfolio_svc: PortfolioService, ):
        acc_id = await cls._get_main_acc_id(db)
        return cls(bot, chat_id, db, name_service, portfolio_svc, tclient, redis, acc_id)

    @classmethod
    async def _get_main_acc_id(cls, db) -> Optional[str]:
        async with db.session_factory() as s:
            acc_list = await db.list_accounts(s)
            if not acc_list:
                return None
            return next(acc.account_id for acc in acc_list)

    async def execute(self, event: MarketDataEvent) -> None:
        self.log.debug("Executing %s", event.__class__.__name__)

        if isinstance(event, LastPriceEvent):
            await self._on_last_price(event)
        elif isinstance(event, LastPriceSubscriptionEvent):
            self.log.info("LastPrice subscribed: %s", list(event.instrument_ids))
        elif isinstance(event, CandleEvent):
            await self._on_candle(event)
        elif isinstance(event, TradeEvent):
            await self._on_trade(event)
        else:
            self.log.debug("Unhandled market event: %r", event)

    async def _on_last_price(self, event: LastPriceEvent) -> None:
        if not event.instrument_id:
            self.log.warning("LastPrice without instrument uid: %r", event)
            return

        await self._cache_last_price(event)
        async with self._db.session_factory() as s:
            context = await self._load_market_context(event, session=s)
            if context is None:
                return

            signal = self._decide_signal(context)
            if signal is None:
                return

            await self._db.set_notify(
                context.indicators.instrument_id,
                notify=False,
                session=s,
            )
            await self._send_signal(context, signal)
            await s.commit()

    async def _cache_last_price(self, event: LastPriceEvent) -> None:
        await self._redis.set_last_price_if_newer(
            event.instrument_id,
            str(event.price),
            ts_ms=int(event.time.timestamp() * 1000),
        )

    async def _load_market_context(
            self,
            event: LastPriceEvent,
            session: Any,
    ) -> Optional[_MarketContext]:
        row = await self._db.get_instrument_with_positions(event.instrument_id, session)
        if not row:
            self.log.debug("No instrument in DataBase for %s", event.instrument_id)
            return None

        indicators, position = row
        price = float(event.price)
        position_direction = getattr(position, "direction", None)
        self.log.debug("Last price %s = %s", event.instrument_id, price)
        self.log.debug("Position: %s\nIndicators: %s", position, indicators)
        return _MarketContext(
            indicators=indicators,
            position_direction=position_direction,
            last_price=price,
        )

    @staticmethod
    def _decide_signal(context: _MarketContext) -> Optional[MarketSignal]:
        return decide_market_signal(
            context.indicators,
            position_direction=context.position_direction,
            last_price=context.last_price,
        )

    async def _send_signal(self, context: _MarketContext, signal: MarketSignal) -> None:
        text = await self._build_signal_text(context, signal)
        await self._bot.send_message(
            self._chat_id,
            text,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    async def _build_signal_text(self, context: _MarketContext, signal: MarketSignal) -> str:
        if signal.kind == SignalKind.STOP_LONG:
            return await text_stop_long_position(
                context.indicators,
                last_price=context.last_price,
                name_service=self._name_service,
            )
        if signal.kind == SignalKind.STOP_SHORT:
            return await text_stop_short_position(
                context.indicators,
                last_price=context.last_price,
                name_service=self._name_service,
            )
        return await self._build_breakout_text(context, signal)

    async def _build_breakout_text(self, context: _MarketContext, signal: MarketSignal) -> str:
        margin_response = await self._tclient.get_min_price_increment_amount(
            uid=str(context.indicators.instrument_id)
        )
        price_point_value = self.price_point(margin_response) if margin_response else None
        portfolios = await _portfolios(self._db, self._portfolio_svc)
        return await text_favorites_breakout(
            context.indicators,
            signal.side,
            last_price=context.last_price,
            name_service=self._name_service,
            price_point_value=price_point_value,
            portfolios=portfolios,
        )

    @staticmethod
    def price_point(margin_response: GetFuturesMarginResponse) -> float:
        price_point_value = float(q2d(margin_response.min_price_increment_amount) / q2d(
            margin_response.min_price_increment))
        return price_point_value

    async def _on_candle(self, event: CandleEvent) -> None:
        self.log.debug("Candle %s %s O:%.2f H:%.2f L:%.2f C:%.2f",
                       event.instrument_id,
                       event.interval,
                       float(event.open),
                       float(event.high),
                       float(event.low),
                       float(event.close))

    async def _on_trade(self, event: TradeEvent) -> None:
        self.log.debug("Trade %s: %s x %s",
                       event.instrument_id,
                       event.quantity,
                       float(event.price))


async def _portfolios(db: Repository, portfolio_svc: PortfolioService) -> list[PortfolioOut]:
    portfolios: list[PortfolioOut] = []
    async with db.session_factory() as s:
        accounts = await db.list_accounts(s)

    for account in accounts:
        portfolios.append(
            await portfolio_svc.get_portfolio(account.account_id, account.name)
        )
    return portfolios
