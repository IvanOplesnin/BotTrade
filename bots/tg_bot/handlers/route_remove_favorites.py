import asyncio

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bots.tg_bot.keyboards.kb_account import kb_list_uncheck
from bots.tg_bot.messages.messages_const import text_uncheck_favorites_instruments
from clients.tinkoff.client import TClient
from database.pgsql.models import Instrument
from database.pgsql.repository import Repository

rout_remove_favorites = Router()


class RemoveFavorites(StatesGroup):
    start = State()


@rout_remove_favorites.message(Command("uncheck_instruments"))
async def remove_favorites(message: types.Message, state: FSMContext, db: Repository):
    await state.clear()
    instruments = await db.get_checked_instruments()
    await state.update_data(instruments=instruments)
    await state.update_data(unset=set())
    if instruments:
        await state.set_state(RemoveFavorites.start)
        await message.answer(
            text="Выберите инструменты, которые нужно <b>перестать отслеживать</b>:",
            reply_markup=kb_list_uncheck(instruments, set())
        )
    else:
        await state.clear()
        await message.answer(
            text="В данный момент мы не следим за какими-либо инструментами. "
                 "Не считая тех что в позициях"
        )


@rout_remove_favorites.callback_query(RemoveFavorites.start, F.data.startswith("unset:"))
async def toggle_unset(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: set[str] = data.get('unset')
    key = call.data
    if key in selected:
        selected.remove(key)
    else:
        selected.add(key)
    await state.update_data(unset=selected)

    # перерисовываем клавиатуру
    instruments = data["instruments"]
    # восстановим простые объекты с теми же полями, что ждёт клавиатура
    await call.message.edit_reply_markup(
        reply_markup=kb_list_uncheck(instruments, selected)
    )


@rout_remove_favorites.callback_query(RemoveFavorites.start, F.data == "cancel")
async def cancel(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer("Отменено")


@rout_remove_favorites.callback_query(RemoveFavorites.start, F.data == "remove_all")
async def remove_all(call: types.CallbackQuery, state: FSMContext, db: Repository, tclient: TClient):
    data = await state.get_data()
    instruments: list[Instrument] = data["instruments"]
    await _apply_uncheck_and_unsubscribe(call, db, tclient, instruments)
    await state.clear()


@rout_remove_favorites.callback_query(RemoveFavorites.start, F.data == "remove")
async def remove_selected(call: types.CallbackQuery, state: FSMContext, db: Repository, tclient: TClient):
    data = await state.get_data()
    selected: set[str] = set(data.get("unset", set()))
    if not selected:
        await call.answer("Ничего не выбрано", show_alert=False)
        return
    # извлечём uid из "unset:<uid>"
    ids = [s.split(":", 1)[1] for s in selected]
    await _apply_uncheck_and_unsubscribe(call, db, tclient, ids)
    await state.clear()


async def _apply_uncheck_and_unsubscribe(
        call: types.CallbackQuery,
        db: Repository,
        tclient: TClient,
        instruments: list[Instrument],
):
    ids = [i.instrument_id for i in instruments]
    task_db = asyncio.create_task(db.check_to_false(*ids))
    try:
        if tclient.market_stream_task:
            tclient.unsubscribe_to_instrument_last_price(*ids)
    except Exception:
        pass
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(text_uncheck_favorites_instruments(instruments=instruments))
    try:
        await task_db
    except Exception as e:
        await call.message.answer(f"⚠️ Ошибка при обновлении БД: {e}")
