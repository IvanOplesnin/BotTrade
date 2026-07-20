import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import LinkPreviewOptions

from application.dto import MarketSignalDecision
from application.market_signal_events import strategy_signal_event_from_decision
from application.market_candles import MarketCandleService
from application.market_signals import MarketSignalService
from application.strategy_state import StrategyStateService
from bots.tg_bot.messages.instruments import text_favorites_breakout, text_stop_long_position, \
    text_stop_short_position
from bots.tg_bot.sending import send_text
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from clients.tinkoff.portfolio_svc import PortfolioService, PortfolioOut
from clients.tinkoff.sdk import GetFuturesMarginResponse, q2d
from core.domains.message_bus import MessageBus
from core.schemas.signal_notifications import STRATEGY_SIGNAL_TOPIC
from database.pgsql.enums import Direction  # noqa: F401 - kept for existing tests monkeypatching
from database.pgsql.repository import Repository
from database.redis.client import RedisClient
from domain.strategies import (
    SignalKind,
    Strategy,
    StrategyRegistry,
)
from domain.stream_events import (
    CandleEvent,
    LastPriceEvent,
    LastPriceSubscriptionEvent,
    MarketDataEvent,
    TradeEvent,
)


class MarketDataHandler:
    def __init__(self, bot: Bot, chat_id: int, db: Repository, name_service: NameService,
                 portfolio_svc: PortfolioService,
                 tclient: TClient, redis: RedisClient, acc_id: str,
                 strategy: Strategy | None = None,
                 signal_service: MarketSignalService | None = None,
                 candle_service: MarketCandleService | None = None,
                 notification_bus: MessageBus | None = None):
        self._bot = bot
        self._chat_id = chat_id
        self.log = logging.getLogger(self.__class__.__name__)
        self._db = db
        self._name_service = name_service
        self._tclient = tclient
        self._redis = redis
        self._portfolio_svc = portfolio_svc
        self._acc_id = acc_id
        self._notification_bus = notification_bus
        strategy_registry = StrategyRegistry([strategy]) if strategy is not None else None
        self._signal_service = signal_service or MarketSignalService(
            db,
            strategy_registry=strategy_registry,
            fallback_strategy=strategy,
        )
        self._candle_service = candle_service or MarketCandleService(
            db,
            StrategyStateService(db),
        )

    @classmethod
    async def create(cls, bot: Bot, chat_id: int, db: Repository, name_service: NameService,
                     tclient: TClient, redis: RedisClient, portfolio_svc: PortfolioService,
                     candle_service: MarketCandleService | None = None,
                     notification_bus: MessageBus | None = None, ):
        acc_id = await cls._get_main_acc_id(db)
        return cls(
            bot,
            chat_id,
            db,
            name_service,
            portfolio_svc,
            tclient,
            redis,
            acc_id,
            candle_service=candle_service,
            notification_bus=notification_bus,
        )

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
        decision = await self._signal_service.process_last_price(event)
        if decision is None:
            return
        await self._publish_or_send_signal(decision, event)

    async def _publish_or_send_signal(
            self,
            decision: MarketSignalDecision,
            event: LastPriceEvent,
    ) -> None:
        signal_event = strategy_signal_event_from_decision(
            decision,
            event_time=event.time,
        )
        if self._notification_bus is not None:
            await self._notification_bus.publish(STRATEGY_SIGNAL_TOPIC, signal_event)
            return
        await self._send_signal(decision)

    async def _cache_last_price(self, event: LastPriceEvent) -> None:
        await self._redis.set_last_price_if_newer(
            event.instrument_id,
            str(event.price),
            ts_ms=int(event.time.timestamp() * 1000),
        )

    async def _send_signal(self, decision: MarketSignalDecision) -> None:
        text = await self._build_signal_text(decision)
        await send_text(
            self._bot,
            chat_id=self._chat_id,
            text=text,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    async def _build_signal_text(self, decision: MarketSignalDecision) -> str:
        signal = decision.signal
        if signal.kind == SignalKind.STOP_LONG:
            return await text_stop_long_position(
                decision.instrument,
                last_price=decision.last_price,
                name_service=self._name_service,
            )
        if signal.kind == SignalKind.STOP_SHORT:
            return await text_stop_short_position(
                decision.instrument,
                last_price=decision.last_price,
                name_service=self._name_service,
            )
        return await self._build_breakout_text(decision)

    async def _build_breakout_text(self, decision: MarketSignalDecision) -> str:
        margin_response = await self._tclient.get_min_price_increment_amount(
            uid=str(decision.instrument.instrument_id)
        )
        price_point_value = self.price_point(margin_response) if margin_response else None
        portfolios = await _portfolios(self._db, self._portfolio_svc)
        return await text_favorites_breakout(
            decision.instrument,
            decision.signal.side,
            last_price=decision.last_price,
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
        result = await self._candle_service.process_candle(event)
        if result.strategy_state is not None:
            self.log.debug(
                "Strategy state refreshed from candle",
                extra={
                    "instrument_id": event.instrument_id,
                    "refreshed": result.strategy_state.refreshed_count,
                    "warming": result.strategy_state.warming_count,
                    "skipped": result.strategy_state.skipped_count,
                },
            )

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
