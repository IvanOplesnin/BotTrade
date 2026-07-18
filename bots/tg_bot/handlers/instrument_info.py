from typing import Literal

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, LinkPreviewOptions

from application.instrument_info import InstrumentInfoService
from bots.tg_bot.handlers.callbacks import clear_inline_keyboard
from bots.tg_bot.keyboards.kb_account import kb_instr_info, kb_short_long
from bots.tg_bot.messages.instruments import text_favorites_breakout
from bots.tg_bot.sending import answer_text
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from clients.tinkoff.portfolio_svc import PortfolioService
from database.pgsql.models import Instrument
from database.pgsql.repository import Repository
from database.redis.client import RedisClient

instr_info = Router()


class InstrumentInfo(StatesGroup):
    start = State()
    choice_account = State()
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
async def instrument_info(call: CallbackQuery, state: FSMContext, db: Repository):
    instrument_id = call.data.removeprefix("info:")
    instruments: list[Instrument] = (await state.get_data())["instruments"]
    instrument = next((i for i in instruments if i.instrument_id == instrument_id), None)

    if instrument is None:
        await clear_inline_keyboard(call)
        await call.message.answer("Что-то пошло не так, попробуйте еще раз")
        await state.clear()
        return

    await state.update_data(instrument=instrument)
    await state.set_state(InstrumentInfo.choice_direction)
    await call.message.edit_text("Выберите направление:", reply_markup=kb_short_long())


@instr_info.callback_query(InstrumentInfo.choice_direction, F.data.in_(("short", "long")))
async def instrument_info_msg(
    call: CallbackQuery,
    state: FSMContext,
    name_service: NameService,
    tclient: TClient,
    redis: RedisClient,
    db: Repository,
    portfolio_svc: PortfolioService,
):
    data = await state.get_data()
    instrument: Instrument = data["instrument"]
    # noinspection PyTypeChecker
    side: Literal["long", "short"] = call.data

    await clear_inline_keyboard(call)
    info = await InstrumentInfoService(
        db=db,
        market_data_client=tclient,
        redis=redis,
        portfolio_svc=portfolio_svc,
    ).build(instrument=instrument, side=side)

    await answer_text(
        call.message,
        text=await text_favorites_breakout(
            info.instrument,
            info.side,
            name_service,
            price_point_value=info.price_point_value,
            last_price=info.last_price,
            calculation_from_the_last_price=True,
            portfolios=info.portfolios,
        ),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await state.clear()


@instr_info.callback_query(InstrumentInfo.start, F.data == "cancel")
async def cancel_instrument_info(call, state: FSMContext):
    await clear_inline_keyboard(call)
    await state.clear()
    await call.message.answer("Отменено")


@instr_info.callback_query(InstrumentInfo.choice_direction, F.data == "cancel")
async def cancel_instrument_info_(call, state: FSMContext):
    await clear_inline_keyboard(call)
    await state.clear()
    await call.message.answer("Отменено")
