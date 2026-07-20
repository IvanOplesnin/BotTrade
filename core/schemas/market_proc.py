import logging

from application.dto import MarketSignalDecision
from application.market_candles import MarketCandleService
from application.market_signal_events import strategy_signal_event_from_decision
from application.market_signals import MarketSignalService
from application.strategy_state import StrategyStateService
from core.domains.message_bus import MessageBus
from core.schemas.signal_notifications import STRATEGY_SIGNAL_TOPIC
from database.pgsql.enums import Direction  # noqa: F401 - kept for existing tests monkeypatching
from database.pgsql.repository import Repository
from database.redis.client import RedisClient
from domain.strategies import (
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
    def __init__(
            self,
            *,
            db: Repository,
            redis: RedisClient,
            notification_bus: MessageBus,
            strategy: Strategy | None = None,
            signal_service: MarketSignalService | None = None,
            candle_service: MarketCandleService | None = None,
    ):
        self.log = logging.getLogger(self.__class__.__name__)
        self._db = db
        self._redis = redis
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
    async def create(
            cls,
            *,
            db: Repository,
            redis: RedisClient,
            notification_bus: MessageBus,
            candle_service: MarketCandleService | None = None,
    ):
        return cls(
            db=db,
            redis=redis,
            notification_bus=notification_bus,
            candle_service=candle_service,
        )

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
        await self._publish_signal(decision, event)

    async def _publish_signal(
            self,
            decision: MarketSignalDecision,
            event: LastPriceEvent,
    ) -> None:
        signal_event = strategy_signal_event_from_decision(
            decision,
            event_time=event.time,
        )
        await self._notification_bus.publish(STRATEGY_SIGNAL_TOPIC, signal_event)

    async def _cache_last_price(self, event: LastPriceEvent) -> None:
        await self._redis.set_last_price_if_newer(
            event.instrument_id,
            str(event.price),
            ts_ms=int(event.time.timestamp() * 1000),
        )

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
