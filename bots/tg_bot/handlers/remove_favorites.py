from typing import Any, Sequence

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from application.watchlist import WatchlistService
from bots.tg_bot.fsm_data import instruments_from_state, instruments_to_state
from bots.tg_bot.handlers.callbacks import clear_inline_keyboard
from bots.tg_bot.handlers.streaming import unsubscribe_last_prices_if_running
from bots.tg_bot.keyboards.kb_account import kb_list_uncheck
from bots.tg_bot.messages.instruments import text_uncheck_favorites_instruments
from bots.tg_bot.sending import answer_text
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from database.pgsql.repository import Repository

rout_remove_favorites = Router()


class RemoveFavorites(StatesGroup):
    start = State()


@rout_remove_favorites.message(Command("uncheck_instruments"))
async def remove_favorites(message: types.Message, state: FSMContext, db: Repository,
                           name_service: NameService):
    '''Перестать отслеживать выбранные инструменты.'''
    await state.clear()
    async with db.session_factory() as session:
        instruments = await db.list_instruments_checked(session=session)
        instruments = [i for (i, ai) in instruments if (ai is None)]
    instruments_state = instruments_to_state(instruments)
    await state.update_data(
        instruments=instruments_state
    )
    await state.update_data(unset=[])
    if instruments:
        await state.set_state(RemoveFavorites.start)
        await message.answer(
            text="Выберите инструменты, которые нужно <b>перестать отслеживать</b>:",
            reply_markup=await kb_list_uncheck(
                instruments_from_state(instruments_state),
                set(),
                name_service=name_service,
            )
        )
    else:
        await state.clear()
        await message.answer(
            text="В данный момент мы не следим за какими-либо инструментами. "
                 "Не считая тех что в позициях"
        )


@rout_remove_favorites.callback_query(RemoveFavorites.start, F.data.startswith("unset:"))
async def toggle_unset(call: types.CallbackQuery, state: FSMContext, name_service: NameService):
    data = await state.get_data()
    selected = set(data.get('unset', []))
    key = call.data
    if key in selected:
        selected.remove(key)
    else:
        selected.add(key)
    await state.update_data(unset=sorted(selected))

    # перерисовываем клавиатуру
    instruments = instruments_from_state(data["instruments"])
    # восстановим простые объекты с теми же полями, что ждёт клавиатура
    await call.message.edit_reply_markup(
        reply_markup=await kb_list_uncheck(instruments, selected, name_service)
    )


@rout_remove_favorites.callback_query(RemoveFavorites.start, F.data == "cancel")
async def cancel(call: types.CallbackQuery, state: FSMContext):
    await clear_inline_keyboard(call)
    await state.clear()
    await call.message.answer("Отменено")


@rout_remove_favorites.callback_query(RemoveFavorites.start, F.data == "remove_all")
async def remove_all(call: types.CallbackQuery, state: FSMContext, db: Repository,
                     tclient: TClient, name_service: NameService):
    data = await state.get_data()
    instruments = instruments_from_state(data["instruments"])
    await _apply_uncheck_and_unsubscribe(call, db, tclient, instruments, name_service)
    await state.clear()


@rout_remove_favorites.callback_query(RemoveFavorites.start, F.data == "remove")
async def remove_selected(call: types.CallbackQuery, state: FSMContext, db: Repository,
                          tclient: TClient, name_service: NameService):
    data = await state.get_data()
    selected: set[str] = set(data.get("unset", set()))
    if not selected:
        await call.answer("Ничего не выбрано", show_alert=False)
        return
    # извлечём uid из "unset:<uid>"
    instruments = instruments_from_state(data["instruments"])
    ids = [instr for instr in instruments if f"unset:{instr.instrument_id}" in selected]
    await _apply_uncheck_and_unsubscribe(call, db, tclient, ids, name_service=name_service)
    await state.clear()


async def _apply_uncheck_and_unsubscribe(
        call: types.CallbackQuery,
        db: Repository,
        tclient: TClient,
        instruments: Sequence[Any],
        name_service: NameService
):
    await clear_inline_keyboard(call)
    try:
        result = await WatchlistService(db, tclient).uncheck_instruments(instruments)
    except Exception as e:
        await call.message.answer(f"⚠️ Ошибка при обновлении БД: {e}")
        return

    try:
        unsubscribe_last_prices_if_running(tclient, result.instrument_ids)
    except Exception as e:
        await call.message.answer(f"Ошибка при попытке отписаться: {e}")

    await answer_text(
        call.message,
        await text_uncheck_favorites_instruments(instruments=instruments, name_service=name_service)
    )
