from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bots.tg_bot.bot import bot
router = Router()

@router.message(CommandStart())
async def command_start(message: types.Message, state: FSMContext):
    await state.clear()
    await bot.send_message(chat_id=message.chat.id, text="Hello! I am a TradingTMasterBot")


class AuthorizeStates(StatesGroup):
    start = State()
    token = State()
    account = State()

@router.message(Command('authorize'))
async def authorize(message: types.Message, state: FSMContext):
    await state.clear()
    await bot.send_message(chat_id=message.chat.id, text="Для авторизации пришлите токен для TinkoffInvest Api")
    await state.set_state(AuthorizeStates.start)

@router.message(F.text, AuthorizeStates.start)
async def read_token(message: types.Message, state: FSMContext):
    if message.text == "":
        await bot.send_message(chat_id=message.chat.id, text="")

class GetAccounts(StatesGroup):
    answer_list_account = State()
    get_list_account = State()


@router.message(Command("get_accounts"))
async def get_accounts(message: types.Message, state: FSMContext):
    await state.clear()
    pass
