import logging

from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bots.tg_bot.keyboards.kb_account import kb_list_accounts
from bots.tg_bot.messages.messages_const import add_account_message
from clients.tinkoff.client import TClient

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
async def add_account_id(call: types.CallbackQuery, state: FSMContext, tclient: TClient):
    await state.update_data(account_id=call.data)
    portfolio = await tclient.get_portfolio(account_id=call.data)
    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=add_account_message(portfolio)
    )

class RemoveAccount(StatesGroup):
    start = State()

@router.message(Command('remove_account_check'))
async def add_account_check(message: types.Message, state: FSMContext, tclient: TClient):
    await state.clear()
    accounts = await tclient.get_accounts()
    await message.answer(text="Выберите аккаунт: \n", reply_markup=kb_list_accounts(accounts))
    await state.set_state(AddAccount.start)

@router.callback_query(F.data, AddAccount.start)
async def add_account_id(call: types.CallbackQuery, state: FSMContext, tclient: TClient):
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
