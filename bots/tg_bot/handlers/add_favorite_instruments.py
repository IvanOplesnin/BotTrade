import asyncio

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


async def add_favorites_instruments(call, db, instruments, state, tclient, name_service):
    instruments_db: list[Instrument] = []
    only_check_ids = []
    instruments_for_message = []
    for instr in instruments:
        indicator_data = None
        instr_in_db = await db.get_indicators_by_uid(instr.uid)
        if instr_in_db:
            if not is_updated_today(instr_in_db.last_update):
                candles_resp = await tclient.get_days_candles_for_2_months(instr.uid)
                indicator_data = IndicatorCalculator(candles_resp=candles_resp,
                                                     ticker=instr.ticker).build_instrument_update()
        elif not instr_in_db:
            candles_resp = await tclient.get_days_candles_for_2_months(instr.uid)
            indicator_data = IndicatorCalculator(candles_resp=candles_resp,
                                                 ticker=instr.ticker).build_instrument_update()
        i = {"instrument_id": instr.uid,
             "ticker": instr.ticker,
             "check": True,
             'direction': None,
             'in_position': False}
        if indicator_data:
            i.update(**indicator_data)
            instruments_db.append(Instrument.from_dict(i))
        else:
            only_check_ids.append(instr.uid)

        instruments_for_message.append(Instrument.from_dict(i))

    add_task_db = asyncio.create_task(db.add_instrument_or_update(*instruments_db))
    go_to_check = asyncio.create_task(db.check_to_true(*only_check_ids))
    await call.message.delete()
    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=await text_add_favorites_instruments(instruments_for_message, name_service)
    )
    if tclient.market_stream_task:
        only_check_ids.extend([i.instrument_id for i in instruments_db])
        tclient.subscribe_to_instrument_last_price(
            *[i for i in only_check_ids]
        )
    await state.clear()
    try:
        await add_task_db
        await go_to_check
    except Exception as e:
        await call.bot.send_message(
            chat_id=call.message.chat.id,
            text=f"Не получилось добавить данные в Бд: {e}"
        )
