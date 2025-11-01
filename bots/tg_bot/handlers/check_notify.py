from aiogram import Router, types
from aiogram.filters import Command

from bots.tg_bot.messages.messages_const import info_notify_message
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from database.pgsql.repository import Repository

check_notify = Router()


@check_notify.message(Command('check_notify'))
async def check_notify_(msg: types.Message, db: Repository, tclient: TClient,
                       name_service: NameService):
    instruments = await db.get_instruments()
    await msg.answer(await info_notify_message(instruments, name_service))
