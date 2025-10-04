from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from bots.tg_bot.bot import bot
router = Router()

@router.message(CommandStart())
async def command_start(message: types.Message, state: FSMContext):
    await state.clear()
    await bot.send_message(chat_id=message.chat.id, text="Hello!")