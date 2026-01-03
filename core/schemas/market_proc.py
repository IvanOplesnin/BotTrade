import asyncio
import logging
from typing import Tuple, Optional, Any

from aiogram import Bot
import tinkoff.invest as ti
from tinkoff.invest import GetFuturesMarginResponse
from tinkoff.invest.utils import quotation_to_decimal as q2d

from bots.tg_bot.messages.messages_const import text_favorites_breakout, text_stop_long_position, \
    text_stop_short_position
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from clients.tinkoff.portfolio_svc import PortfolioService, PortfolioOut
from database.pgsql.enums import Direction
from database.pgsql.repository import Repository
from database.redis.client import RedisClient


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

    async def execute(self, resp: ti.MarketDataResponse) -> None:
        self.log.debug("Executing %s", resp.__class__.__name__)
        name, payload = self._extract(resp)
        if payload is None:
            return

        if isinstance(payload, ti.LastPrice):
            await self._on_last_price(payload)
        elif isinstance(payload, ti.SubscribeLastPriceResponse):
            self.log.info("LastPrice subscribed: %s", [
                s.instrument_uid for s in payload.last_price_subscriptions
            ])
        elif isinstance(payload, ti.Candle):
            await self._on_candle(payload)
        elif isinstance(payload, ti.Trade):
            await self._on_trade(payload)
        else:
            self.log.debug("Unhandled market event %s: %r", name, payload)

    @staticmethod
    def _extract(resp: ti.MarketDataResponse) -> Tuple[str, Optional[Any]]:
        if resp.subscribe_last_price_response is not None:
            return "subscribe_last_price_response", resp.subscribe_last_price_response
        if resp.subscribe_trades_response is not None:
            return "subscribe_trades_response", resp.subscribe_trades_response
        if resp.subscribe_info_response is not None:
            return "subscribe_info_response", resp.subscribe_info_response
        if resp.subscribe_order_book_response is not None:
            return "subscribe_order_book_response", resp.subscribe_order_book_response
        if resp.subscribe_candles_response is not None:
            return "subscribe_candles_response", resp.subscribe_candles_response

        if resp.last_price is not None:
            return "last_price", resp.last_price
        if resp.trade is not None:
            return "trade", resp.trade
        if resp.candle is not None:
            return "candle", resp.candle
        if resp.orderbook is not None:
            return "orderbook", resp.orderbook
        if resp.trading_status is not None:
            return "trading_status", resp.trading_status
        if resp.ping is not None:
            return "ping_result", resp.ping
        if resp.open_interest is not None:
            return "open_interest", resp.open_interest
        return "unknown", None

    async def _on_last_price(self, lp: ti.LastPrice) -> None:
        uid = lp.instrument_uid
        price = float(q2d(lp.price))
        await self._redis.set_last_price_if_newer(uid, str(q2d(lp.price)), ts_ms=int(lp.time.timestamp() * 1000))
        async with self._db.session_factory() as s:
            row = await self._db.get_instrument_with_positions(uid, s)
            if not row:
                self.log.debug("No instrument in DataBase for %s", uid)
                return
            indicators, position = row
            self.log.debug("Last price %s = %s", uid, price)
            self.log.debug("Position: %s\nIndicators: %s", position, indicators)
            if not indicators.check or not indicators.to_notify:
                return
            if position:
                direction = position.direction
                if direction == Direction.LONG.value:
                    if price <= indicators.donchian_short_20:
                        await self._bot.send_message(
                            self._chat_id,
                            await text_stop_long_position(indicators, last_price=price,
                                                          name_service=self._name_service)
                        )
                        await self._db.set_notify(indicators.instrument_id, notify=False, session=s)
                        await s.commit()
                        return
                if direction == Direction.SHORT.value:
                    if price >= indicators.donchian_long_20:
                        await self._bot.send_message(
                            self._chat_id,
                            await text_stop_short_position(indicators, last_price=price,
                                                           name_service=self._name_service)
                        )
                        await self._db.set_notify(indicators.instrument_id, notify=False, session=s)
                        await s.commit()
                        return
            else:
                if not indicators.donchian_long_55:
                    return
                if price >= indicators.donchian_long_55:
                    await self._db.set_notify(indicators.instrument_id, notify=False, session=s)
                    margin_response = await self._tclient.get_min_price_increment_amount(
                        uid=str(indicators.instrument_id)
                    )
                    price_point_value = None
                    if margin_response:
                        price_point_value = self.price_point(margin_response)

                    portfolio: PortfolioOut | None = await self._portfolio_svc.get_portfolio(self._acc_id)
                    await self._bot.send_message(
                        self._chat_id,
                        await text_favorites_breakout(indicators, 'long',
                                                      last_price=price,
                                                      name_service=self._name_service,
                                                      price_point_value=price_point_value,
                                                      portfolio=portfolio)
                    )
                    await s.commit()
                    return
                elif price <= indicators.donchian_short_55:
                    await self._db.set_notify(indicators.instrument_id, notify=False, session=s)
                    margin_response = await self._tclient.get_min_price_increment_amount(
                        str(indicators.instrument_id)
                    )
                    price_point_value = None
                    if margin_response:
                        price_point_value = self.price_point(margin_response)

                    portfolio: PortfolioOut | None = await self._portfolio_svc.get_portfolio(self._acc_id)
                    await self._bot.send_message(
                        self._chat_id,
                        await text_favorites_breakout(indicators, 'short',
                                                      last_price=price,
                                                      name_service=self._name_service,
                                                      price_point_value=price_point_value,
                                                      portfolio=portfolio)
                    )
                    await s.commit()
                    return

    @staticmethod
    def price_point(margin_response: GetFuturesMarginResponse) -> float:
        price_point_value = float(q2d(margin_response.min_price_increment_amount) / q2d(
            margin_response.min_price_increment))
        return price_point_value

    async def _on_candle(self, c: ti.Candle) -> None:
        uid = c.instrument_uid or c.figi
        o, h, l, cl = map(lambda q: float(q2d(q)), (c.open, c.high, c.low, c.close))
        self.log.debug("Candle %s %s O:%.2f H:%.2f L:%.2f C:%.2f",
                       uid, c.interval, o, h, l, cl)

    async def _on_trade(self, t: ti.Trade) -> None:
        uid = t.instrument_uid or t.figi
        price = float(q2d(t.price))
        qty = t.quantity
        self.log.debug("Trade %s: %s x %s", uid, qty, price)
