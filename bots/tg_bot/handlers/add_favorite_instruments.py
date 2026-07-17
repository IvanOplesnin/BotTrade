from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from application.watchlist import WatchlistService
from bots.tg_bot.handlers.callbacks import clear_inline_keyboard
from bots.tg_bot.handlers.streaming import subscribe_last_prices_if_running
from bots.tg_bot.keyboards.kb_account import kb_list_favorites
from bots.tg_bot.messages.instruments import text_add_favorites_instruments
from clients.tinkoff.client import TClient
from clients.tinkoff.mappers import flatten_favorite_groups, instruments_to_candidates
from clients.tinkoff.name_service import NameService
from clients.tinkoff.sdk import sdk_instrument_uid, ti
from database.pgsql.repository import Repository

rout_add_favorites = Router()


class SetFavorites(StatesGroup):
    start = State()


@rout_add_favorites.message(Command('add_instruments_for_check'))
async def add_instruments_for_check(message: types.Message, tclient: TClient, state: FSMContext,
                                    db: Repository):
    '''Добавить избранные инструменты для отслеживания.'''
    await state.clear()
    favorite_groups = await tclient.get_favorites_instruments()
    async with db.session_factory() as session:
        check_instruments = await db.list_instruments_checked(session)
    checked_id = [i.instrument_id for i, ai in check_instruments]
    instruments = flatten_favorite_groups(favorite_groups)
    instruments = [
        i for i in instruments
        if sdk_instrument_uid(i) and sdk_instrument_uid(i) not in checked_id
    ]
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
    await clear_inline_keyboard(call)
    await state.clear()
    await call.message.answer("Отменено")


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

    instruments = [i for i in instruments if f"set:{sdk_instrument_uid(i)}" in set_instruments]
    await add_favorites_instruments(call, db, instruments, state, tclient, name_service)


async def add_favorites_instruments(
        call: types.CallbackQuery,
        db: Repository,
        instruments: list[ti.FavoriteInstrument],
        state: FSMContext,
        tclient: TClient,
        name_service: NameService,
):
    await clear_inline_keyboard(call)
    watch_instruments = instruments_to_candidates(instruments)
    if not watch_instruments:
        await call.message.answer("Список пуст.")
        await state.clear()
        return

    result = await WatchlistService(db, tclient).add_favorites(watch_instruments)

    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=await text_add_favorites_instruments(result.message_instruments, name_service),
    )

    subscribe_last_prices_if_running(tclient, result.instrument_ids)

    await state.clear()
