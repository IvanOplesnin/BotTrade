from typing import Optional

from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select, Sequence, Row
from sqlalchemy.sql.elements import or_

from bots.tg_bot.messages.messages_const import info_notify_message, info_database_message
from clients.tinkoff.name_service import NameService
from database.pgsql.models import AccountInstrument, Instrument
from database.pgsql.repository import Repository

info_rout = Router()


@info_rout.message(Command('check_notify'))
async def check_notify_(msg: types.Message, db: Repository,
                        name_service: NameService):
    '''Просмотреть информацию об оповещениях.'''
    async with db.session_factory() as session:
        instruments = await db.list_instruments(session=session)

    await msg.answer(await info_notify_message(instruments, name_service))


@info_rout.message(Command('info'))
async def info_(msg: types.Message, db: Repository, name_service: NameService):
    '''Показывает информацию об отслеживаемых инструментах.'''
    async with db.session_factory() as s:
        stmt = (
            select(Instrument, AccountInstrument).
            outerjoin(
                AccountInstrument, AccountInstrument.instrument_id == Instrument.instrument_id
            ).where(or_(Instrument.check == True,
                        AccountInstrument.instrument_id.isnot(None)))
        )
        row: Sequence[Row[tuple[Instrument, Optional[AccountInstrument]]]] = (
            await s.execute(stmt)
        ).unique().all()

    if not row:
        await msg.answer('Вы не следите за инструментами')
        return

    await msg.answer(await info_database_message(row, name_service))
