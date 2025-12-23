import logging
from typing import Literal

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery

from bots.tg_bot.keyboards.kb_account import kb_instr_info, kb_short_long
from bots.tg_bot.messages.messages_const import text_favorites_breakout
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from database.pgsql.models import Instrument
from database.pgsql.repository import Repository
from database.redis.client import RedisClient
from utils.utils import price_point

instr_info = Router()


class InstrumentInfo(StatesGroup):
    start = State()
    choice_direction = State()


@instr_info.message(Command("instr_info"))
async def instruments_info(msg: Message, state: FSMContext, db: Repository, name_service: NameService):
    """Получить информацию об уровнях для определённого инструмента. """
    await state.clear()
    async with db.session_factory() as s:
        instruments = await db.list_instruments_checked(s)

    instruments = [i for (i, ai) in instruments]
    await state.update_data(instruments=instruments)
    await state.set_state(InstrumentInfo.start)
    await msg.answer("Выберите инструмент:", reply_markup=await kb_instr_info(instruments, name_service))


@instr_info.callback_query(InstrumentInfo.start, F.data.startswith("info:"))
async def instrument_info(call: CallbackQuery, state: FSMContext):
    id_i = call.data.removeprefix("info:")
    instruments: list[Instrument] = (await state.get_data())['instruments']
    instrument = next((i for i in instruments if i.instrument_id == id_i), None)
    if instrument is None:
        await call.message.answer("Что-то пошло не так, попробуйте еще раз", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        return
    await state.update_data(instrument=instrument)
    await state.set_state(InstrumentInfo.choice_direction)
    await call.message.edit_reply_markup(
        reply_markup=kb_short_long()
    )


@instr_info.callback_query(InstrumentInfo.choice_direction, F.data.in_(("short", "long")))
async def instrument_info_msg(call: CallbackQuery, state: FSMContext, name_service: NameService, tclient: TClient,
                              redis: RedisClient):
    instrument: Instrument = (await state.get_data())['instrument']
    # noinspection PyTypeChecker
    side: Literal["long", "short"] = call.data
    await call.message.delete()
    price_point_value = await tclient.get_min_price_increment_amount(instrument.instrument_id)
    if price_point_value:
        price_point_value = price_point(price_point_value)
    last_price = None
    data_last_price = await redis.get_last_price(instrument.instrument_id)
    if data_last_price:
        last_price = data_last_price['price']
        logging.debug(f"last_price: {last_price}")
    await call.message.answer(
        text=await text_favorites_breakout(
            instrument,
            side,
            name_service,
            price_point_value=price_point_value,
            last_price=float(last_price) if last_price else None,
            calculation_from_the_last_price=True
        )
    )
    await state.clear()


@instr_info.callback_query(InstrumentInfo.start, F.data == "cancel")
async def cancel_instrument_info(call, state: FSMContext):
    await call.message.delete()
    await state.clear()
    await call.message.answer("Отменено", reply_markup=ReplyKeyboardRemove())


@instr_info.callback_query(InstrumentInfo.choice_direction, F.data == "cancel")
async def cancel_instrument_info_(call, state: FSMContext):
    await call.message.delete()
    await state.clear()
    await call.message.answer("Отменено", reply_markup=ReplyKeyboardRemove())
