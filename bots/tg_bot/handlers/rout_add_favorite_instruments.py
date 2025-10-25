import asyncio

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import tinkoff.invest as ti

from bots.tg_bot.keyboards.kb_account import kb_list_favorites
from bots.tg_bot.messages.messages_const import text_add_favorites_instruments
from clients.tinkoff.client import TClient
from database.pgsql.models import Instrument
from database.pgsql.repository import Repository
from services.historic_service.historic_service import IndicatorCalculator

rout_add_favorites = Router()


class SetFavorites(StatesGroup):
    start = State()


@rout_add_favorites.message(Command('add_instruments_for_check'))
async def add_instruments_for_check(message: types.Message, tclient: TClient, state: FSMContext):
    await state.clear()
    favorite_groups = await tclient.get_favorites_instruments()
    instruments: list[ti.FavoriteInstrument] = []
    for favorite_group in favorite_groups:
        instruments.extend(favorite_group.favorite_instruments)

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
        tclient: TClient
):
    data = await state.get_data()
    instruments: list[ti.FavoriteInstrument] = data['instruments']
    await add_favorites_instruments(call, db, instruments, state, tclient)


@rout_add_favorites.callback_query(SetFavorites.start, F.data == "add")
async def add_favorite(
        call: types.CallbackQuery,
        state: FSMContext,
        db: Repository,
        tclient: TClient
):
    data = await state.get_data()
    instruments: list[ti.FavoriteInstrument] = data['instruments']
    set_instruments: set[str] = data['set_favorite']
    print(set_instruments)

    instruments = [i for i in instruments if f"set:{i.uid}" in set_instruments]
    await add_favorites_instruments(call, db, instruments, state, tclient)


async def add_favorites_instruments(call, db, instruments, state, tclient):
    instruments_db: list[Instrument] = []
    for instr in instruments:
        candles_resp = await tclient.get_days_candles_for_2_months(instr.uid)
        indicator_data = IndicatorCalculator(candles_resp=candles_resp,
                                             ticker=instr.ticker).build_instrument_update()
        i = {"instrument_id": instr.uid, "ticker": instr.ticker, "check": True, 'direction': None,
             'in_position': False}
        i.update(**indicator_data)
        instruments_db.append(Instrument.from_dict(i))
    add_task_db = asyncio.create_task(db.add_instrument_or_update(*instruments_db))
    await call.message.delete()
    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=text_add_favorites_instruments(instruments_db)
    )
    if tclient.market_stream_task:
        tclient.subscribe_to_instrument_last_price(
            *[i.instrument_id for i in instruments_db]
        )
    await state.clear()
    try:
        await add_task_db
    except Exception as e:
        await call.bot.send_message(
            chat_id=call.message.chat.id,
            text=f"Не получилось добавить данные в Бд: {e}"
        )


class RemoveFavorites(StatesGroup):
    start = State()
