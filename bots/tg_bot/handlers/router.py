from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from application.market_subscriptions import MarketSubscriptionSyncService
from application.watchlist import WatchlistService
from bots.tg_bot.handlers.callbacks import clear_inline_keyboard
from bots.tg_bot.keyboards.kb_account import kb_list_accounts, kb_list_accounts_delete
from bots.tg_bot.messages.accounts import (
    text_add_account_message,
    text_delete_account_message,
)
from bots.tg_bot.messages.static import HELP_TEXT, START_TEXT
from bots.tg_bot.sending import answer_text, send_text
from clients.tinkoff.client import TClient
from clients.tinkoff.mappers import portfolio_positions_to_candidates
from clients.tinkoff.name_service import NameService
from database.pgsql.repository import Repository

router = Router()


@router.message(CommandStart())
async def command_start(message: types.Message, state: FSMContext):
    """Приветственное сообщение."""
    await state.clear()
    await send_text(message.bot, chat_id=message.chat.id, text=START_TEXT)


@router.message(Command('help'))
async def command_help(message: types.Message):
    """Список команд бота."""
    await answer_text(message, HELP_TEXT)


class AddAccount(StatesGroup):
    start = State()


@router.message(Command('add_account_check'))
async def add_account_check(message: types.Message, state: FSMContext, tclient: TClient):
    """Выбрать и добавить аккаунт для отслеживания."""
    await state.clear()
    accounts = await tclient.get_accounts()

    # сохраняем соответствие id → название
    acc_map = {acc.id: acc.name for acc in accounts}
    await state.update_data(acc_map=acc_map)

    await message.answer(text="Выберите аккаунт: \n", reply_markup=kb_list_accounts(accounts))
    await state.set_state(AddAccount.start)


@router.callback_query(F.data, AddAccount.start)
async def add_account_id(call: types.CallbackQuery, state: FSMContext, tclient: TClient,
                         db: Repository, name_service: NameService,
                         watchlist_svc: WatchlistService | None = None,
                         market_subscription_svc: MarketSubscriptionSyncService | None = None):
    if call.data == "cancel":
        await clear_inline_keyboard(call)
        await state.clear()
        await call.message.answer(text="Отменено")
        return
    await clear_inline_keyboard(call)
    account_name_by_id = (await state.get_data()).get("acc_map", {})
    portfolio = await tclient.get_portfolio(account_id=call.data)
    name = account_name_by_id.get(call.data, call.data)
    account_id = portfolio.account_id

    positions = list(portfolio.positions) or []
    if not positions:
        await call.message.answer("У аккаунта нет открытых позиций.")
        await state.clear()
        return

    watch_positions = portfolio_positions_to_candidates(positions)
    if not watch_positions:
        await call.message.answer("В портфеле нет торговых инструментов для отслеживания.")
        await state.clear()
        return

    service = watchlist_svc or WatchlistService(db, tclient)
    result = await service.add_account(
        account_id=account_id,
        account_name=name,
        positions=watch_positions,
    )

    subscription_svc = market_subscription_svc or MarketSubscriptionSyncService(tclient, db)
    subscription_svc.subscribe_last_prices_if_running(result.instrument_ids)
    await subscription_svc.recreate_portfolio_stream_from_db()

    await send_text(
        call.bot,
        chat_id=call.message.chat.id,
        text=await text_add_account_message(result.positions, name_service),
    )
    await state.clear()


class RemoveAccount(StatesGroup):
    start = State()


@router.message(Command('remove_account_check'))
async def remove_account_check(message: types.Message, state: FSMContext,
                               db: Repository):
    """Удалить ранее добавленный аккаунт."""
    await state.clear()
    async with db.session_factory() as session:
        accounts = await db.list_accounts(session)
    await message.answer(text="Выберите аккаунт: \n",
                         reply_markup=kb_list_accounts_delete(accounts))
    await state.set_state(RemoveAccount.start)


@router.callback_query(F.data, RemoveAccount.start)
async def remove_account_id(call: types.CallbackQuery, state: FSMContext, tclient: TClient,
                            db: Repository, name_service: NameService,
                            watchlist_svc: WatchlistService | None = None,
                            market_subscription_svc: MarketSubscriptionSyncService | None = None):
    if call.data == "cancel":
        await clear_inline_keyboard(call)
        await call.message.answer(text="Отменено")
        await state.clear()
        return

    await clear_inline_keyboard(call)
    service = watchlist_svc or WatchlistService(db, tclient)
    result = await service.remove_account(call.data)
    subscription_svc = market_subscription_svc or MarketSubscriptionSyncService(tclient, db)
    subscription_svc.unsubscribe_last_prices_if_running(result.detached_instrument_ids)
    await subscription_svc.recreate_portfolio_stream_from_db()

    await send_text(
        call.bot,
        chat_id=call.message.chat.id,
        text=await text_delete_account_message(
            result.detached_instrument_ids,
            name_service=name_service,
        )
    )
    await state.clear()
