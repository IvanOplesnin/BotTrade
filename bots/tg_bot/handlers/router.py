import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy import select
from tinkoff.invest import GetCandlesResponse

from bots.tg_bot.keyboards.kb_account import kb_list_accounts, kb_list_accounts_delete
from bots.tg_bot.messages.messages_const import (
    text_add_account_message,
    text_delete_account_message,
    START_TEXT,
    HELP_TEXT
)
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from database.pgsql.enums import Direction
from database.pgsql.models import Instrument, Account, AccountInstrument
from database.pgsql.repository import Repository
from services.historic_service.historic_service import IndicatorCalculator
from utils import is_updated_today

router = Router()
logger = logging.getLogger(__name__)
CONCURRENCY_CANDLES = 12


@router.message(CommandStart())
async def command_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.bot.send_message(chat_id=message.chat.id,
                                   text=START_TEXT)


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
async def add_account_id(call: types.CallbackQuery, state: FSMContext, tclient: TClient,
                         db: Repository, name_service: NameService):
    if call.data == "cancel":
        await call.message.delete()
        await state.clear()
        await call.message.answer(text="Отменено")
        return
    portfolio = await tclient.get_portfolio(account_id=call.data)
    name = (await state.get_data()).get("acc_map")[call.data]
    account_id = portfolio.account_id

    # Собираем данные по позициям
    positions = list(portfolio.positions) or []
    if not positions:
        await call.message.answer("У аккаунта нет открытых позиций.")
        await state.clear()
        return

    instruments_meta = {
        p.instrument_uid: {
            "ticker": p.ticker,
            "direction": (
                Direction.LONG.value if p.quantity_lots.units > 0 else Direction.SHORT.value),
        }
        for p in positions
    }
    instruments_ids = list(instruments_meta.keys())

    async with db.session_factory() as session:
        # 1) upsert аккаунта
        await db.upsert_account(account_id=account_id, name=name, check=True, session=session)
        # 2) вытащим текущие записи по инструментам одним запросом
        existing_by_id = {
            i.instrument_id: i
            for i in await db.list_instruments_by_ids(instruments_ids, session=session)
        }
        # 3) решаем, кому нужны свечи (новые или устаревшие)
        need_candles = [
            uid for uid in instruments_ids
            if (uid not in existing_by_id) or not is_updated_today(existing_by_id[uid].last_update)
        ]
        # 4) грузим свечи параллельно с ограничением
        candles_by_uid: dict[str, GetCandlesResponse] = {}

        async def _fetch(uid: str):
            candles_by_uid[uid] = await tclient.get_days_candles_for_2_months(uid)

        if need_candles:
            sem = asyncio.Semaphore(CONCURRENCY_CANDLES)

            async def _guarded(uid: str):
                async with sem:
                    await _fetch(uid)

            await asyncio.gather(*[_guarded(uid) for uid in need_candles])
        # 5) считаем индикаторы и готовим батч для upsert
        rows_for_upsert = []
        instruments_for_message = []  # чтобы красиво отправить пользователю

        now_utc = datetime.now(timezone.utc)
        for uid in instruments_ids:
            meta = instruments_meta[uid]
            existing = existing_by_id.get(uid)
            if uid in candles_by_uid:
                # пересчёт индикаторов
                indicator = IndicatorCalculator(
                    candles_resp=candles_by_uid[uid],
                ).build_instrument_update()
                row = {
                    "instrument_id": uid,
                    "ticker": meta["ticker"],
                    "check": True,
                    "to_notify": True,
                    "donchian_long_55": indicator.get("donchian_long_55"),
                    "donchian_short_55": indicator.get("donchian_short_55"),
                    "donchian_long_20": indicator.get("donchian_long_20"),
                    "donchian_short_20": indicator.get("donchian_short_20"),
                    "atr14": indicator.get("atr14"),
                    "last_update": now_utc,
                }
                instruments_for_message.append(Instrument.from_dict(row))
            else:
                # актуально — не пересчитываем; не перетираем существующие поля
                row = {
                    "instrument_id": uid,
                    "ticker": meta["ticker"],
                    "check": True,
                    "to_notify": existing.to_notify if existing else True,
                    "donchian_long_55": getattr(existing, "donchian_long_55", None),
                    "donchian_short_55": getattr(existing, "donchian_short_55", None),
                    "donchian_long_20": getattr(existing, "donchian_long_20", None),
                    "donchian_short_20": getattr(existing, "donchian_short_20", None),
                    "atr14": getattr(existing, "atr14", None),
                    "last_update": getattr(existing, "last_update", now_utc),
                }
                instruments_for_message.append(Instrument.from_dict(row))

            rows_for_upsert.append(row)

        # 6) один батч-upsert инструментов (ON CONFLICT DO UPDATE)
        await db.upsert_instruments_bulk_data(
            items=rows_for_upsert,
            session=session,
        )
        await session.commit()

        # 7) один батч по позициям аккаунта (account_instruments)
        rows_positions = [
            AccountInstrument(
                account_id=account_id,
                instrument_id=uid,
                in_position=True,
                direction=meta["direction"],
            )
            for uid in instruments_ids
        ]
        await db.set_position_bulk(rows_positions, session=session)

    # 8) подписка на цены (после фикса в БД)
    if instruments_ids and tclient.market_stream_task:
        tclient.subscribe_to_instrument_last_price(*instruments_ids)

    async with db.session_factory() as session:
        accounts_ids = [a.account_id for a in await db.list_accounts(session=session)]
    if tclient.portfolio_stream_task:
        await tclient.recreate_portfolio_stream(accounts_ids)

    # 9) ответ пользователю
    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=await text_add_account_message(instruments_for_message, name_service),
    )
    await state.clear()


class RemoveAccount(StatesGroup):
    start = State()


@router.message(Command('remove_account_check'))
async def remove_account_check(message: types.Message, state: FSMContext,
                               db: Repository):
    await state.clear()
    async with db.session_factory() as session:
        accounts = await db.list_accounts(session)
    await message.answer(text="Выберите аккаунт: \n",
                         reply_markup=kb_list_accounts_delete(accounts))
    await state.set_state(RemoveAccount.start)


@router.callback_query(F.data, RemoveAccount.start)
async def remove_account_id(call: types.CallbackQuery, state: FSMContext, tclient: TClient,
                            db: Repository, name_service: NameService):
    if call.data == "cancel":
        await call.message.answer(text="Отменено")
        await state.clear()
        return

    portfolio = await tclient.get_portfolio(account_id=call.data)
    instruments_id = []
    async with db.session_factory() as s:
        for position in portfolio.positions:
            await db.delete_position(account_id=position.instrument_uid,
                                     instrument_id=position.instrument_uid, session=s)
            instruments_id.append(position.instrument_uid)

        await db.delete_account(account_id=call.data, session=s)
        await s.commit()



    if tclient.market_stream_task:
        tclient.unsubscribe_to_instrument_last_price(*instruments_id)

    async with db.session_factory() as session:
        accounts_ids = [a.account_id for a in await db.list_accounts(session=session)]
    if tclient.portfolio_stream_task:
        await tclient.recreate_portfolio_stream(accounts_ids)

    await call.bot.send_message(
        chat_id=call.message.chat.id,
        text=await text_delete_account_message(portfolio, name_service=name_service)
    )
    await state.clear()
