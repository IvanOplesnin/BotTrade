from aiogram import Router, types
from aiogram.filters import Command

from bots.tg_bot.sending import answer_text
from bots.tg_bot.messages.info import info_database_message, info_notify_message
from clients.tinkoff.name_service import NameService
from database.pgsql.repository import Repository

info_rout = Router()


@info_rout.message(Command('check_notify'))
async def check_notify_(msg: types.Message, db: Repository,
                        name_service: NameService):
    '''Просмотреть информацию об оповещениях.'''
    async with db.session_factory() as session:
        instruments = await db.list_instruments(session=session)

    await answer_text(msg, await info_notify_message(instruments, name_service))


@info_rout.message(Command('info'))
async def info_(msg: types.Message, db: Repository, name_service: NameService):
    '''Показывает информацию об отслеживаемых инструментах.'''
    async with db.session_factory() as s:
        row = await db.list_instruments_for_info(s)

    if not row:
        await msg.answer('Вы не следите за инструментами')
        return

    await answer_text(msg, await info_database_message(row, name_service))
