import asyncio
import logging

import tinkoff.invest as ti
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bots.tg_bot.keyboards.kb_account import kb_list_accounts, kb_list_accounts_delete, kb_list_favorites
from bots.tg_bot.messages.messages_const import (
    text_add_account_message,
    text_delete_account_message,
    START_TEXT,
    HELP_TEXT
)
from clients.tinkoff.client import TClient
from database.pgsql.enums import Direction
from database.pgsql.models import Instrument, Account
from database.pgsql.repository import Repository
from services.historic_service.historic_service import IndicatorCalculator

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def command_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.bot.send_message(chat_id=message.chat.id, text=START_TEXT)


@router.message(Command('help'))
async def command_help(message: types.Message):
    await message.answer(text=HELP_TEXT)


class AddAccount(StatesGroup):
    start = State()


@router.message(Command('add_account_check'))
async def add_account_check(message: types.Message, state: FSMContext, tclient: TClient):
    await state.clear()
    accounts = await tclient.get_accounts()

    # сохраняем соответствие id → название
    acc_map = {acc.id: acc.name for acc in accounts}
    await state.update_data(acc_map=acc_map)

    await message.answer(text="Выберите аккаунт: \n", reply_markup=kb_list_accounts(accounts))
    await state.set_state(AddAccount.start)


@router.callback_query(F.data, AddAccount.start)
async def add_account_id(call: types.CallbackQuery, state: FSMContext, tclient: TClient, db: Repository):
    if call.data == 'cancel':
        await call.message.delete()
        await state.clear()
        await call.message.answer(text="Отменено")
    portfolio = await tclient.get_portfolio(account_id=call.data)
    name = (await state.get_data()).get('acc_map')[call.data]
    await db.add_portfolio(
        Account.from_dict({'account_id': portfolio.account_id, 'name': name, 'check': True})
    )
    instruments_id = []
    indicators = []
    for position in portfolio.positions:
        instruments_id.append(position.instrument_uid)
        instrument = {
            "instrument_id": position.instrument_uid,
            "ticker": position.ticker,
            "in_position": True,
            "direction": Direction.LONG.value if position.quantity_lots.units > 0 else Direction.SHORT.value,
            "check": True
        }
        candles_resp = await tclient.get_days_candles_for_2_months(position.instrument_uid)
        indicator = IndicatorCalculator(
            ticker=position.ticker,
            candles_resp=candles_resp
        )
        instrument.update(**indicator.build_instrument_update())
        indicators.append(instrument)

    tclient.subscribe_to_instrument_last_price(*instruments_id)
    tasks_add = [db.add_instrument_or_update(Instrument.from_dict(i)) for i in indicators]
    await asyncio.gather(*tasks_add)

    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=text_add_account_message(indicators)
    )
    await state.clear()


class RemoveAccount(StatesGroup):
    start = State()


@router.message(Command('remove_account_check'))
async def add_account_check(message: types.Message, state: FSMContext, tclient: TClient, db: Repository):
    await state.clear()
    accounts = await db.get_accounts()
    await message.answer(text="Выберите аккаунт: \n", reply_markup=kb_list_accounts_delete(accounts))
    await state.set_state(RemoveAccount.start)


@router.callback_query(F.data, RemoveAccount.start)
async def add_account_id(call: types.CallbackQuery, state: FSMContext, tclient: TClient, db: Repository):
    if call.data == "cancel":
        await call.message.answer(text="Отменено")
        await state.clear()
        return

    portfolio = await tclient.get_portfolio(account_id=call.data)
    instruments_id = []
    for position in portfolio.positions:
        await db.check_to_false(position.instrument_uid)
        instruments_id.append(position.instrument_uid)

    await db.delete_account(account_id=call.data)
    tclient.unsubscribe_to_instrument_last_price(*instruments_id)
    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=text_delete_account_message(portfolio)
    )
    await state.clear()


class SetFavorites(StatesGroup):
    start = State()


@router.message(Command('add_instruments_for_check'))
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


@router.callback_query(SetFavorites.start, F.data.startswith("set:"))
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


@router.callback_query(SetFavorites.start, F.data == "cancel")
async def cancel_favorite(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()


@router.callback_query(SetFavorites.start, F.data == "all_add")
async def add_all_favorite(call: types.CallbackQuery, state: FSMContext, db: Repository, tclient: TClient):
    data = await state.get_data()
    instruments: list[ti.FavoriteInstrument] = data['instruments']
    for ins in instruments:
        await db.add_instrument()
