import asyncio
import logging

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
log = logging.getLogger(__name__)


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
    await call.answer()
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
    await call.answer("Добавляю инструменты...", show_alert=False)
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
    await call.answer("Добавляю инструменты...", show_alert=False)
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

    await call.message.answer("Добавляю инструменты в отслеживание...")

    service = WatchlistService(db, tclient)
    try:
        result = await service.add_favorites_quick(watch_instruments)
    except Exception as exc:
        log.exception("Failed to add favorite instruments")
        await call.message.answer(
            "Не удалось добавить инструменты в отслеживание. "
            f"Ошибка: {exc}"
        )
        await state.clear()
        return

    await call.message.answer(await _add_favorites_message(result.message_instruments, name_service))
    _schedule_favorites_refresh(db, tclient, watch_instruments)

    try:
        subscribe_last_prices_if_running(tclient, result.instrument_ids)
    except Exception:
        log.exception("Failed to subscribe favorite instruments to last_price stream")

    await state.clear()


async def _add_favorites_message(instruments, name_service: NameService) -> str:
    try:
        return await text_add_favorites_instruments(instruments, name_service)
    except Exception:
        log.exception("Failed to build favorite instruments message")
        lines = [
            f"✅ <b>{getattr(item, 'ticker', item.instrument_id)}</b> — {item.instrument_id}"
            for item in instruments
        ]
        return "Добавлены инструменты:\n" + ("\n".join(lines) if lines else "ничего не выбрано.")


def _schedule_favorites_refresh(
        db: Repository,
        tclient: TClient,
        instruments,
) -> asyncio.Task:
    task = asyncio.create_task(_refresh_favorites_indicators(db, tclient, instruments))
    task.add_done_callback(_log_refresh_result)
    return task


async def _refresh_favorites_indicators(
        db: Repository,
        tclient: TClient,
        instruments,
) -> None:
    await WatchlistService(db, tclient).add_favorites(instruments)


def _log_refresh_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        log.info("Favorite instruments refresh task cancelled")
    except Exception:
        log.exception("Failed to refresh favorite instrument indicators")
