import asyncio
import logging

from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import tinkoff.invest as ti

from bots.tg_bot.keyboards.kb_account import kb_list_accounts
from bots.tg_bot.messages.messages_const import text_add_account_message
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
    await message.bot.send_message(chat_id=message.chat.id, text="Hello! I am a TradingTMasterBot")


class AddAccount(StatesGroup):
    start = State()


@router.message(Command('add_account_check'))
async def add_account_check(message: types.Message, state: FSMContext, tclient: TClient):
    await state.clear()
    accounts = await tclient.get_accounts()
    await message.answer(text="Выберите аккаунт: \n", reply_markup=kb_list_accounts(accounts))
    await state.set_state(AddAccount.start)


@router.callback_query(F.data, AddAccount.start)
async def add_account_id(call: types.CallbackQuery, state: FSMContext, tclient: TClient, db: Repository):
    await state.update_data(account_id=call.data)
    portfolio = await tclient.get_portfolio(account_id=call.data)
    await db.add_portfolio(
        Account.from_dict(**{
            'account_id': portfolio.account_id,
            'check': True
        })
    )
    instruments_id = []
    indicators = []
    for position in portfolio.positions:
        instruments_id.append(position.instrument_uid)
        instrument = {
            "instrument_id": position.instrument_uid,
            "ticker": position.ticker,
            "in_position": True,
            "direction": Direction.LONG if position.quantity_lots.units > 0 else Direction.SHORT,
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
    tasks_add = [db.add_instrument(Instrument.from_dict(**i)) for i in indicators]
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

    await message.answer(text="Выберите аккаунт: \n", reply_markup=kb_list_accounts(accounts))
    await state.set_state(AddAccount.start)


@router.callback_query(F.data, RemoveAccount.start)
async def add_account_id(call: types.CallbackQuery, state: FSMContext, tclient: TClient, db: Repository):
    await state.update_data(account_id=call.data)
    portfolio = await tclient.get_portfolio(account_id=call.data)
    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=add_account_message(portfolio)
    )


class GetAccounts(StatesGroup):
    answer_list_account = State()
    get_list_account = State()


@router.message(Command("get_accounts"))
async def get_accounts(message: types.Message, state: FSMContext):
    await state.clear()
    pass
