import asyncio
import logging
from typing import Sequence

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from application.market_subscriptions import (
    MarketSubscriptionRefreshPublisher,
    MarketSubscriptionSyncService,
)
from application.watchlist import WatchlistService
from bots.tg_bot.fsm_data import (
    FavoriteInstrumentFSM,
    favorite_instruments_from_state,
    favorite_instruments_to_state,
)
from bots.tg_bot.handlers.callbacks import clear_inline_keyboard
from bots.tg_bot.keyboards.kb_account import kb_list_favorites
from bots.tg_bot.messages.formatting import safe_error_text
from bots.tg_bot.messages.instruments import text_add_favorites_instruments
from bots.tg_bot.sending import answer_text
from clients.tinkoff.client import TClient
from clients.tinkoff.mappers import flatten_favorite_groups, instruments_to_candidates
from clients.tinkoff.name_service import NameService
from clients.tinkoff.sdk import sdk_instrument_uid
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
    instruments_state = favorite_instruments_to_state(instruments)
    await state.update_data(instruments=instruments_state)
    await state.update_data(set_favorite=[])
    await state.set_state(SetFavorites.start)
    await message.answer(text="Выберите инструменты для отслеживания: ",
                         reply_markup=kb_list_favorites(
                             favorite_instruments_from_state(instruments_state),
                             set(),
                         ))


@rout_add_favorites.callback_query(SetFavorites.start, F.data.startswith("set:"))
async def replace_kb(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    instruments = favorite_instruments_from_state(data['instruments'])
    set_favorite = set(data.get('set_favorite', []))
    if call.data in set_favorite:
        set_favorite.remove(call.data)
    else:
        set_favorite.add(call.data)
    await state.update_data(set_favorite=sorted(set_favorite))
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
        name_service: NameService,
        watchlist_svc: WatchlistService | None = None,
        market_subscription_svc: MarketSubscriptionSyncService | None = None,
        market_subscription_refresh_publisher: MarketSubscriptionRefreshPublisher | None = None,
):
    await call.answer("Добавляю инструменты...", show_alert=False)
    data = await state.get_data()
    instruments = favorite_instruments_from_state(data['instruments'])
    await add_favorites_instruments(
        call,
        db,
        instruments,
        state,
        tclient,
        name_service,
        watchlist_svc=watchlist_svc,
        market_subscription_svc=market_subscription_svc,
        market_subscription_refresh_publisher=market_subscription_refresh_publisher,
    )


@rout_add_favorites.callback_query(SetFavorites.start, F.data == "add")
async def add_favorite(
        call: types.CallbackQuery,
        state: FSMContext,
        db: Repository,
        tclient: TClient,
        name_service: NameService,
        watchlist_svc: WatchlistService | None = None,
        market_subscription_svc: MarketSubscriptionSyncService | None = None,
        market_subscription_refresh_publisher: MarketSubscriptionRefreshPublisher | None = None,
):
    await call.answer("Добавляю инструменты...", show_alert=False)
    data = await state.get_data()
    instruments = favorite_instruments_from_state(data['instruments'])
    set_instruments = set(data.get('set_favorite', []))

    instruments = [i for i in instruments if f"set:{sdk_instrument_uid(i)}" in set_instruments]
    await add_favorites_instruments(
        call,
        db,
        instruments,
        state,
        tclient,
        name_service,
        watchlist_svc=watchlist_svc,
        market_subscription_svc=market_subscription_svc,
        market_subscription_refresh_publisher=market_subscription_refresh_publisher,
    )


async def add_favorites_instruments(
        call: types.CallbackQuery,
        db: Repository,
        instruments: Sequence[FavoriteInstrumentFSM],
        state: FSMContext,
        tclient: TClient,
        name_service: NameService,
        watchlist_svc: WatchlistService | None = None,
        market_subscription_svc: MarketSubscriptionSyncService | None = None,
        market_subscription_refresh_publisher: MarketSubscriptionRefreshPublisher | None = None,
):
    await clear_inline_keyboard(call)
    watch_instruments = instruments_to_candidates(instruments)
    if not watch_instruments:
        await call.message.answer("Список пуст.")
        await state.clear()
        return

    await call.message.answer("Добавляю инструменты в отслеживание...")

    service = watchlist_svc or WatchlistService(db, tclient)
    try:
        result = await service.add_favorites_quick(watch_instruments)
    except Exception as exc:
        log.exception("Failed to add favorite instruments")
        await answer_text(
            call.message,
            "Не удалось добавить инструменты в отслеживание. "
            f"Ошибка: {safe_error_text(exc)}"
        )
        await state.clear()
        return

    await answer_text(
        call.message,
        await _add_favorites_message(result.message_instruments, name_service),
    )
    _schedule_favorites_refresh(
        db,
        tclient,
        watch_instruments,
        watchlist_svc=service,
    )

    try:
        subscription_svc = market_subscription_svc or MarketSubscriptionSyncService(tclient, db)
        subscription_svc.subscribe_last_prices_if_running(result.instrument_ids)
    except Exception:
        log.exception("Failed to subscribe favorite instruments to last_price stream")

    await _request_subscription_refresh(
        market_subscription_refresh_publisher,
        reason="favorites_added",
        instrument_ids=result.instrument_ids,
    )
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
        *,
        watchlist_svc: WatchlistService | None = None,
) -> asyncio.Task:
    task = asyncio.create_task(
        _refresh_favorites_indicators(
            db,
            tclient,
            instruments,
            watchlist_svc=watchlist_svc,
        )
    )
    task.add_done_callback(_log_refresh_result)
    return task


async def _request_subscription_refresh(
        publisher: MarketSubscriptionRefreshPublisher | None,
        *,
        reason: str,
        instrument_ids: Sequence[str],
) -> None:
    if publisher is None:
        return
    try:
        await publisher.request_refresh(
            reason=reason,
            instrument_ids=instrument_ids,
        )
    except Exception:
        log.exception("Failed to publish subscription refresh request")


async def _refresh_favorites_indicators(
        db: Repository,
        tclient: TClient,
        instruments,
        *,
        watchlist_svc: WatchlistService | None = None,
) -> None:
    service = watchlist_svc or WatchlistService(db, tclient)
    await service.add_favorites(instruments)


def _log_refresh_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        log.info("Favorite instruments refresh task cancelled")
    except Exception:
        log.exception("Failed to refresh favorite instrument indicators")
