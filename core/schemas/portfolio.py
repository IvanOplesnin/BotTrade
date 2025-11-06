import logging
from datetime import datetime, timezone
from typing import Tuple, Optional, Any, Set, Dict, List
from zoneinfo import ZoneInfo

from aiogram import Bot
import tinkoff.invest as ti
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tinkoff.invest import PortfolioPosition

from bots.tg_bot.messages.messages_const import msg_portfolio_notify
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from database.pgsql.enums import Direction
from database.pgsql.models import AccountInstrument, Instrument
from database.pgsql.repository import Repository
from database.pgsql.schemas import InstrumentIn
from services.historic_service.historic_service import IndicatorCalculator
from utils import is_updated_today

TZ_MOSCOW = ZoneInfo("Europe/Moscow")


class PortfolioHandler:
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
        add_for_msg: List[Dict[str, Any]] = []
        delete_for_msg: Set[str] = set()
        ids_portfolio: Set[str] = {p.instrument_uid for p in portfolio.positions}
        if not ids_portfolio:
            # если в ответе пусто — просто снимем все позиции аккаунта
            async with self._db.session_factory() as s:
                await self._db.delete_all_positions_for_account(
                    account_id=portfolio.account_id,
                    session=s,
                )
                await s.commit()
            return
        portfolio_map = {p.instrument_uid: p for p in portfolio.positions}
        now = datetime.now(tz=timezone.utc)
        async with self._db.session_factory() as s:
            stmt = (
                select(AccountInstrument.instrument_id)
                .where(AccountInstrument.account_id == portfolio.account_id)
            )
            ids_db = {i for i in (await s.execute(stmt)).scalars().all()}
            need_delete = ids_db - ids_portfolio
            need_add = ids_portfolio - ids_db

            res_ins = await s.execute(
                select(Instrument).where(Instrument.instrument_id.in_(ids_portfolio))
            )
            existing_by_id: Dict[str, Instrument] = {
                i.instrument_id: i for i in res_ins.scalars().all()
            }

            # Решаем, кому нужно обновить индикаторы (новые или не за сегодня)
            need_indicators: List[str] = []
            for uid in ids_portfolio:
                inst = existing_by_id.get(uid)
                if inst is None or not is_updated_today(inst.last_update, tz=TZ_MOSCOW):
                    need_indicators.append(uid)

            if need_indicators:
                rows: List[InstrumentIn] = []
                for uid in need_indicators:
                    candles = await self._tclient.get_days_candles_for_2_months(uid)
                    indicators = IndicatorCalculator(candles_resp=candles).build_instrument_update()
                    pos = portfolio_map[uid]
                    ticker = pos.ticker
                    rows.append(
                        InstrumentIn(
                            instrument_id=uid,
                            ticker=ticker,
                            check=True,
                            to_notify=True,
                            **indicators,
                        )
                    )
                await self._db.upsert_instruments_bulk_data(rows, session=s, update_ts=True)

            if need_delete:
                self.log.info("Delete positions: %s", need_delete)
                await self._db.delete_positions_bulk(account_id=portfolio.account_id,
                                                     instrument_ids=need_delete, session=s)
                delete_for_msg = need_delete

            if need_add:
                rows_links = [
                    {
                        "account_id": portfolio.account_id,
                        "instrument_id": uid,
                        "direction": (
                            Direction.LONG.value
                            if portfolio_map[uid].quantity_lots.units > 0
                            else Direction.SHORT.value
                        ),
                    }
                    for uid in need_add
                ]
                add_for_msg = rows_links
                await self._db.set_position_bulk(rows_links, session=s)
            await s.commit()
        if add_for_msg or delete_for_msg:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=await msg_portfolio_notify(add_for_msg, delete_for_msg, self._name_service)
            )
