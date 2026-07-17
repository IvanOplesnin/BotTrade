import logging

from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from application.dto import PositionCandidate
from application.watchlist import WatchlistService
from bots.tg_bot.handlers.callbacks import clear_inline_keyboard
from bots.tg_bot.keyboards.kb_account import kb_list_accounts, kb_list_accounts_delete
from bots.tg_bot.messages.messages_const import (
    text_add_account_message,
    text_delete_account_message,
    START_TEXT,
    HELP_TEXT
)
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from clients.tinkoff.sdk import sdk_instrument_ticker, sdk_instrument_uid
from database.pgsql.enums import Direction
from database.pgsql.repository import Repository

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def command_start(message: types.Message, state: FSMContext):
    """Приветственное сообщение."""
    await state.clear()
    await message.bot.send_message(chat_id=message.chat.id,
                                   text=START_TEXT)


@router.message(Command('help'))
async def command_help(message: types.Message):
    """Список команд бота."""
    await message.answer(text=HELP_TEXT)


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
                         db: Repository, name_service: NameService):
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
    logger.debug(positions)
    if not positions:
        await call.message.answer("У аккаунта нет открытых позиций.")
        await state.clear()
        return

    watch_positions: list[PositionCandidate] = []
    for p in positions:
        uid = sdk_instrument_uid(p)
        if not uid:
            logger.warning("Portfolio position without instrument uid", extra={"position": p})
            continue
        watch_positions.append(
            PositionCandidate(
                instrument_id=uid,
                ticker=sdk_instrument_ticker(p, default=uid),
                direction=(
                    Direction.LONG.value
                    if p.quantity_lots.units > 0
                    else Direction.SHORT.value
                ),
            )
        )

    if not watch_positions:
        await call.message.answer("Не удалось определить инструменты в открытых позициях.")
        await state.clear()
        return

    result = await WatchlistService(db, tclient).add_account(
        account_id=account_id,
        account_name=name,
        positions=watch_positions,
    )

    if result.instrument_ids and tclient.market_stream_task:
        tclient.subscribe_to_instrument_last_price(*result.instrument_ids)

    async with db.session_factory() as session:
        accounts_ids = [a.account_id for a in await db.list_accounts(session=session)]
    if tclient.portfolio_stream_task:
        await tclient.recreate_portfolio_stream(accounts_ids)

    await call.bot.send_message(
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
                            db: Repository, name_service: NameService):
    if call.data == "cancel":
        await clear_inline_keyboard(call)
        await call.message.answer(text="Отменено")
        await state.clear()
        return

    await clear_inline_keyboard(call)
    async with db.session_factory() as s:
        positions = await db.list_positions_for_account(account_id=call.data, session=s)
        instruments_id = [position.instrument_id for position, _ in positions]

        await db.delete_account(account_id=call.data, session=s)
        await s.commit()

    if instruments_id and tclient.market_stream_task:
        tclient.unsubscribe_to_instrument_last_price(*instruments_id)

    async with db.session_factory() as session:
        accounts_ids = [a.account_id for a in await db.list_accounts(session=session)]
    if tclient.portfolio_stream_task:
        await tclient.recreate_portfolio_stream(accounts_ids)

    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=await text_delete_account_message(instruments_id, name_service=name_service)
    )
    await state.clear()
