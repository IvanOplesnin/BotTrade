import logging
from typing import Tuple, Optional, Any

from aiogram import Bot
import tinkoff.invest as ti
from tinkoff.invest.utils import quotation_to_decimal as q2d

from bots.tg_bot.messages.messages_const import text_favorites_breakout, text_stop_long_position, \
    text_stop_short_position
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from database.pgsql.enums import Direction
from database.pgsql.repository import Repository


class MarketDataProcessor:
    def __init__(self, bot: Bot, chat_id: int, db: Repository, name_service: NameService,
                 tclient: TClient):
        self._bot = bot
        self._chat_id = chat_id
        self.log = logging.getLogger(self.__class__.__name__)
        self._db = db
        self._name_service = name_service
        self._tclient = tclient

    async def execute(self, resp: ti.PortfolioStreamResponse) -> None:
        self.log.debug("Executing %s", resp.__class__.__name__)
        portfolio = resp.portfolio
        if portfolio:
            await self._on_portfolio_response(portfolio)

    async def _on_portfolio_response(self, portfolio: ti.PortfolioResponse) -> None:
        pass
