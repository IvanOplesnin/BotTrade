import asyncio
from typing import List, Tuple, Iterable
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
    check_instruments = await db.get_checked_instruments()
    checked_id = [i.instrument_id for i in check_instruments]
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


async def add_favorites_instruments(call, db, instruments: Iterable, state, tclient, name_service):
    """
    Для каждого инструмента:
      - если в БД нет или last_update не сегодня -> тянем свечи и считаем индикаторы;
      - иначе только отмечаем check=True.

    Затем:
      - пачкой добавляем/обновляем инструменты в БД,
      - помечаем check=True тем, у кого не считали индикаторы,
      - отправляем сообщение,
      - подписываемся на last_price для всех отмеченных,
      - чистим состояние.
    """

    sem = asyncio.Semaphore(12)

    async def process_one(instr) -> Tuple:
        """
        Возвращает кортеж:
          (instrument_for_db | None, uid_for_only_check | None, instrument_for_message)
        """
        async with sem:
            # базовая запись для сообщения/БД
            base = {
                "instrument_id": instr.uid,
                "ticker": instr.ticker,
                "check": True,
                "direction": None,
                "in_position": False,
            }

            # узнаём, есть ли валидные индикаторы за сегодня
            instr_in_db = await db.get_indicators_by_uid(instr.uid)

            if instr_in_db is None:
                need_refresh = True
            else:
                # если обновляли НЕ сегодня — надо пересчитать
                need_refresh = not is_updated_today(instr_in_db.last_update,
                                                    tz=ZoneInfo("Europe/Moscow"))

            if need_refresh:
                # считаем индикаторы (может падать — позволим пробросить ошибку выше?)
                candles_resp = await tclient.get_days_candles_for_2_months(instr.uid)
                indicator_data = IndicatorCalculator(
                    candles_resp=candles_resp,
                    ticker=instr.ticker
                ).build_instrument_update()

                record = base | indicator_data
                inst_for_db = Instrument.from_dict(record)
                inst_for_message = Instrument.from_dict(record)
                return inst_for_db, None, inst_for_message

            # индикаторы свежие — в БД ничего не пишем, только check=True
            inst_for_message = Instrument.from_dict(base)
            return None, instr.uid, inst_for_message

    # Параллельно обрабатываем все инструменты
    results = await asyncio.gather(*(process_one(i) for i in instruments), return_exceptions=True)

    instruments_db: List[Instrument] = []
    only_check_ids: List[str] = []
    instruments_for_message: List[Instrument] = []

    # Разворачиваем результаты и аккуратно репортим ошибки
    errors = []
    for res in results:
        if isinstance(res, Exception):
            errors.append(res)
            continue
        inst_for_db, uid_only_check, inst_for_msg = res
        if inst_for_db:
            instruments_db.append(inst_for_db)
        if uid_only_check:
            only_check_ids.append(uid_only_check)
        instruments_for_message.append(inst_for_msg)

    # Планируем БД-операции заранее (они сами по себе быстрые, но пусть идут параллельно)
    db_tasks = []
    if instruments_db:
        db_tasks.append(asyncio.create_task(db.add_instrument_or_update(*instruments_db)))
    if only_check_ids:
        db_tasks.append(asyncio.create_task(db.check_to_true(*only_check_ids)))

    # Меняем сообщение пользователю
    try:
        await call.message.delete()
    except Exception:
        # тихо игнорируем, если сообщение уже удалено/недоступно
        pass

    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=await text_add_favorites_instruments(instruments_for_message, name_service)
    )

    # Подписка на цены: подписываемся на всё, что «в наблюдении» (и пересчитанные, и только check=True)
    if tclient.market_stream_task:
        # добавим uid из обоих источников
        subscribed_uids = set(only_check_ids)
        subscribed_uids.update(i.instrument_id for i in instruments_db)
        if subscribed_uids:
            tclient.subscribe_to_instrument_last_price(*subscribed_uids)

    # Чистим состояние
    await state.clear()

    # Дожидаемся завершения БД-операций и репортим ошибку, если была
    try:
        if db_tasks:
            await asyncio.gather(*db_tasks)
    except Exception as e:
        await call.bot.send_message(
            chat_id=call.message.chat.id,
            text=f"Не получилось добавить данные в БД: {e}"
        )

    # Если в обработке инструментов были ошибки — мягко сообщим (без падения всей команды)
    if errors:
        await call.bot.send_message(
            chat_id=call.message.chat.id,
            text=f"Часть инструментов обработать не удалось: {len(errors)} шт."
        )
