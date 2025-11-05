import asyncio
from datetime import datetime, timezone
from typing import List, Tuple, Iterable, Any
from zoneinfo import ZoneInfo

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import tinkoff.invest as ti

from bots.tg_bot.keyboards.kb_account import kb_list_favorites
from bots.tg_bot.messages.messages_const import text_add_favorites_instruments
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from database.pgsql.models import Instrument
from database.pgsql.repository import Repository
from database.pgsql.schemas import InstrumentIn
from services.historic_service.historic_service import IndicatorCalculator
from utils import is_updated_today

rout_add_favorites = Router()


class SetFavorites(StatesGroup):
    start = State()


@rout_add_favorites.message(Command('add_instruments_for_check'))
async def add_instruments_for_check(message: types.Message, tclient: TClient, state: FSMContext,
                                    db: Repository):
    await state.clear()
    favorite_groups = await tclient.get_favorites_instruments()
    async with db.session_factory() as session:
        check_instruments = await db.list_instruments_checked(session)
    checked_id = [i.instrument_id for i, ai in check_instruments]
    instruments: list[ti.FavoriteInstrument] = []
    for favorite_group in favorite_groups:
        instruments.extend(favorite_group.favorite_instruments)

    instruments = [i for i in instruments if i.uid not in checked_id]
    await state.update_data(instruments=instruments)
    await state.update_data(set_favorite=set())
    await state.set_state(SetFavorites.start)
    await message.answer(text="Выберите инструменты для отслеживания: ",
                         reply_markup=kb_list_favorites(instruments, set()))


@rout_add_favorites.callback_query(SetFavorites.start, F.data.startswith("set:"))
async def replace_kb(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    instruments: list[ti.FavoriteInstrument] = data['instruments']
    set_favorite: set[str] = data['set_favorite']
    if call.data in set_favorite:
        set_favorite.remove(call.data)
    else:
        set_favorite.add(call.data)
    await state.update_data(set_favorite=set_favorite)
    await call.message.edit_reply_markup(
        reply_markup=kb_list_favorites(instruments, set_favorite)
    )


@rout_add_favorites.callback_query(SetFavorites.start, F.data == "cancel")
async def cancel_favorite(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()


@rout_add_favorites.callback_query(SetFavorites.start, F.data == "add_all")
async def add_all_favorite(
        call: types.CallbackQuery,
        state: FSMContext,
        db: Repository,
        tclient: TClient,
        name_service: NameService
):
    data = await state.get_data()
    instruments: list[ti.FavoriteInstrument] = data['instruments']
    await add_favorites_instruments(call, db, instruments, state, tclient, name_service)


@rout_add_favorites.callback_query(SetFavorites.start, F.data == "add")
async def add_favorite(
        call: types.CallbackQuery,
        state: FSMContext,
        db: Repository,
        tclient: TClient,
        name_service: NameService
):
    data = await state.get_data()
    instruments: list[ti.FavoriteInstrument] = data['instruments']
    set_instruments: set[str] = data['set_favorite']
    print(set_instruments)

    instruments = [i for i in instruments if f"set:{i.uid}" in set_instruments]
    await add_favorites_instruments(call, db, instruments, state, tclient, name_service)


async def add_favorites_instruments(
        call: types.CallbackQuery,
        db: Repository,
        instruments: Iterable[ti.FavoriteInstrument],  # объекты с .uid, .ticker
        state: FSMContext,
        tclient: TClient,
        name_service: NameService,
):
    """
    Для каждого инструмента:
      - если в БД нет или last_update не сегодня -> тянем свечи и считаем индикаторы;
      - иначе только отмечаем check=True.

    Затем:
      - пачкой upsert’им инструменты (без обнулений),
      - пачкой выставляем check=True там, где индикаторы не считали,
      - отправляем сообщение,
      - подписываемся на last_price,
      - чистим состояние.
    """
    tz = ZoneInfo("Europe/Moscow")

    # 0) Список uid/ticker
    src = [(i.uid, i.ticker) for i in instruments]
    if not src:
        await call.message.answer("Список пуст.")
        await state.clear()
        return
    uids = [u for u, _ in src]
    ticker_by_uid = {u: t for u, t in src}

    # 1) Одна сессия, заранее тянем, что уже есть в БД
    async with db.session_factory() as session:
        existing = {
            inst.instrument_id: inst
            for inst in await db.list_instruments_by_ids(uids, session=session)
        }

        # 2) Решаем, кому нужны свечи
        need_candles = [
            uid for uid in uids
            if (uid not in existing) or not is_updated_today(existing[uid].last_update, tz=tz)
        ]

        # 3) Параллельно тянем свечи с ограничением
        candles: dict[str, Any] = {}

        async def _fetch_one(uid: str):
            candles[uid] = await tclient.get_days_candles_for_2_months(uid)
        if need_candles:
            async def _guard(uid: str):
                await _fetch_one(uid)
            await asyncio.gather(*[_guard(uid) for uid in need_candles])

        # 4) Готовим батч для upsert и список для простого check=True
        rows_for_upsert: List[InstrumentIn] = []
        only_check_ids: List[str] = []
        instruments_for_message: List[Instrument] = []

        now_utc = datetime.now(timezone.utc)

        for uid in uids:
            ticker = ticker_by_uid[uid]
            if uid in candles:
                # пересчитываем индикаторы
                indicator = IndicatorCalculator(
                    candles_resp=candles[uid],
                ).build_instrument_update()

                payload = {
                    "instrument_id": uid,
                    "ticker": ticker,
                    "check": True,
                    "to_notify": True,
                    "donchian_long_55": indicator.get("donchian_long_55"),
                    "donchian_short_55": indicator.get("donchian_short_55"),
                    "donchian_long_20": indicator.get("donchian_long_20"),
                    "donchian_short_20": indicator.get("donchian_short_20"),
                    "atr14": indicator.get("atr14"),
                    "last_update": now_utc,
                }
                rows_for_upsert.append(InstrumentIn(**payload))
                instruments_for_message.append(Instrument.from_dict(payload))
            else:
                only_check_ids.append(uid)
                payload_msg = {
                    "instrument_id": uid,
                    "ticker": ticker,
                    "check": True,
                    "to_notify": True,
                    "donchian_long_55": getattr(existing.get(uid), "donchian_long_55", None),
                    "donchian_short_55": getattr(existing.get(uid), "donchian_short_55", None),
                    "donchian_long_20": getattr(existing.get(uid), "donchian_long_20", None),
                    "donchian_short_20": getattr(existing.get(uid), "donchian_short_20", None),
                    "atr14": getattr(existing.get(uid), "atr14", None),
                    "last_update": getattr(existing.get(uid), "last_update", now_utc),
                }
                instruments_for_message.append(Instrument.from_dict(payload_msg))

        # 5) БД-операции (один commit)
        # 5.1 upsert индикаторов тем, кому пересчитывали
        if rows_for_upsert:
            await db.upsert_instruments_bulk_data(rows_for_upsert, session=session)

        # 5.2 пометить check=True тем, кому не пересчитывали (bulk)
        if only_check_ids:
            await db.set_checked_bulk(only_check_ids, session)

        await session.commit()

    # 6) Обновляем сообщение
    try:
        await call.message.delete()
    except Exception:
        pass

    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=await text_add_favorites_instruments(instruments_for_message, name_service),
    )

    # 7) Подписка на цены
    if tclient.market_stream_task:
        tclient.subscribe_to_instrument_last_price(*uids)

    # 8) Чистим состояние
    await state.clear()
