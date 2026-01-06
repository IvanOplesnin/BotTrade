import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Set, Dict, List, Sequence, Optional
from zoneinfo import ZoneInfo

from aiogram import Bot
import tinkoff.invest as ti
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tinkoff.invest import GetCandlesResponse, PortfolioResponse, PortfolioPosition
from tinkoff.invest.utils import money_to_decimal as m2d, quotation_to_decimal as q2d

from bots.tg_bot.messages.messages_const import msg_portfolio_notify
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from clients.tinkoff.portfolio_svc import PortfolioOut, PortfolioService
from database.pgsql.enums import Direction
from database.pgsql.models import AccountInstrument, Instrument
from database.pgsql.repository import Repository
from database.pgsql.schemas import InstrumentIn
from services.historic_service.indicators import IndicatorCalculator
from utils import is_updated_today
from utils.utils import price_point

TZ_MOSCOW = ZoneInfo("Europe/Moscow")
RUB000UTSTOM = "a92e2e25-a698-45cc-a781-167cf465257c"


@dataclass(frozen=True)
class PositionState:
    instrument_id: str
    direction: str
    lots: int
    unit_size: Optional[int] = None


@dataclass(frozen=True)
class PortfolioDiff:
    added: List[PositionState]
    removed: List[PositionState]
    changed: List[tuple[PositionState, PositionState]]  # (old, new)

    def is_empty(self) -> bool:
        return not self.added and not self.removed and not self.changed


class PortfolioHandler:
    def __init__(self, bot: Bot, chat_id: int, db: Repository, name_service: NameService,
                 tclient: TClient, portfolio_svc: PortfolioService):
        self._bot = bot
        self._chat_id = chat_id
        self.log = logging.getLogger(self.__class__.__name__)
        self._db = db
        self._name_service = name_service
        self._tclient = tclient
        self._portfolio_svc = portfolio_svc

    async def execute(self, resp: ti.PortfolioStreamResponse) -> None:
        self.log.debug("Executing %s", resp.__class__.__name__)
        if resp.portfolio:
            await self._on_portfolio_response(resp.portfolio)

    async def _on_portfolio_response(self, portfolio: ti.PortfolioResponse) -> None:
        """
        1) считаем актуальное состояние из стрима
        2) читаем состояние из БД
        3) diff
        4) применяем изменения в БД
        5) если были изменения — отправляем сообщение
        """
        position_map: Dict[str, ti.PortfolioPosition] = {
            p.instrument_uid: p
            for p in portfolio.positions
            if p.instrument_uid and p.instrument_uid != RUB000UTSTOM
        }
        ids_portfolio: Set[str] = set(position_map.keys())
        async with self._db.session_factory() as s:
            if not ids_portfolio:
                # (опционально) достать старые позиции, чтобы показать что удалилось
                old = await self._load_db_positions(portfolio.account_id, s)
                await self._db.delete_all_positions_for_account(portfolio.account_id, s)
                await s.commit()

                if old:
                    diff = PortfolioDiff(
                        added=[],
                        removed=list(old.values()),
                        changed=[],
                    )
                    await self._notify_changes(diff)
                return

            atr_map = await self._ensure_instruments_and_get_atr(position_map, s)
            db_positions = await self._load_db_positions(portfolio.account_id, s)

            new_positions = await self._build_new_positions(
                portfolio=portfolio,
                position_map=position_map,
                atr_map=atr_map,
                session=s,
            )
            diff = self._diff_positions(db_positions, new_positions)
            await self._apply_positions(portfolio.account_id, diff, new_positions, s)
            await s.commit()
        if not diff.is_empty():
            await self._notify_changes(diff)

    async def _apply_positions(
            self,
            account_id: str,
            diff: PortfolioDiff,
            new_positions: Dict[str, PositionState],
            s: AsyncSession,
    ) -> None:
        # Удаления
        if diff.removed:
            await self._db.delete_positions_bulk(
                account_id=account_id,
                instrument_ids={p.instrument_id for p in diff.removed},
                session=s,
            )

        # Добавления + изменения: можно одним bulk set (upsert в linking-таблицу)
        # Если твой set_position_bulk делает upsert — отлично. Если только insert — раздели.
        upsert_rows: List[dict[str, Any]] = []

        for p in diff.added:
            upsert_rows.append({
                "account_id": account_id,
                "instrument_id": p.instrument_id,
                "direction": p.direction,
                "lots": p.lots,
                "unit_size": p.unit_size,
            })

        for old_p, new_p in diff.changed:
            upsert_rows.append({
                "account_id": account_id,
                "instrument_id": new_p.instrument_id,
                "direction": new_p.direction,
                "lots": new_p.lots,
            })

        if upsert_rows:
            await self._db.set_position_bulk(upsert_rows, s)

    def _diff_positions(
            self,
            old: Dict[str, PositionState],
            new: Dict[str, PositionState],
    ) -> PortfolioDiff:
        old_ids = set(old.keys())
        new_ids = set(new.keys())

        added = [new[i] for i in sorted(new_ids - old_ids)]
        removed = [old[i] for i in sorted(old_ids - new_ids)]

        changed: List[tuple[PositionState, PositionState]] = []
        for i in sorted(old_ids & new_ids):
            o = old[i]
            n = new[i]
            if (o.direction != n.direction) or (o.lots != n.lots):
                changed.append((o, n))

        return PortfolioDiff(added=added, removed=removed, changed=changed)

    async def _build_new_positions(
            self,
            portfolio: PortfolioResponse,
            position_map: Dict[str, PortfolioPosition],
            atr_map: Dict[str, float],
            session: AsyncSession,
    ) -> Dict[str, PositionState]:
        account = await self._db.get_account(portfolio.account_id, session)

        base_portfolio = PortfolioOut(
            account_id=portfolio.account_id,
            name=str(account.name),
            total_amount=m2d(portfolio.total_amount_portfolio),
            expected_yield_percent=q2d(portfolio.expected_yield),
        )

        async def _unit_size_for(pos: PortfolioPosition) -> Optional[int]:
            # unit_size считаем только если ATR есть
            atr = atr_map.get(pos.instrument_uid)
            if not atr:
                return None

            price_p = 1.0
            if pos.instrument_type == "futures":
                futures_margin = await self._tclient.get_min_price_increment_amount(pos.instrument_uid)
                if futures_margin:
                    price_p = float(price_point(futures_margin))

            return _calc_count_contracts(base_portfolio, atr=float(atr), price_point=float(price_p))

        # Считаем unit_size параллельно, но аккуратно (если захотишь — добавим семафор)
        unit_sizes = await asyncio.gather(*[_unit_size_for(p) for p in position_map.values()])

        new_state: Dict[str, PositionState] = {}
        for pos, unit_size in zip(position_map.values(), unit_sizes):
            direction = Direction.LONG.value if pos.quantity_lots.units > 0 else Direction.SHORT.value
            new_state[pos.instrument_uid] = PositionState(
                instrument_id=pos.instrument_uid,
                direction=direction,
                lots=int(q2d(pos.quantity_lots)),
                unit_size=unit_size,
            )
        return new_state

    async def _notify_changes(self, diff: PortfolioDiff) -> None:
        add_rows = [
            {"instrument_id": p.instrument_id, "direction": p.direction, "lots": p.lots, "unit_size": p.unit_size}
            for p in diff.added
        ]
        del_ids = {p.instrument_id for p in diff.removed}

        text = await msg_portfolio_notify(add_rows, del_ids, self._name_service)

        if diff.changed:
            lines = ["", "Изменения позиций:"]
            for old_p, new_p in diff.changed:
                # можно красиво подставить тикер/название через name_service
                name = await self._name_service.get_name(new_p.instrument_id)  # если метод иначе — замени
                parts = [f"• {name}"]
                if old_p.direction != new_p.direction:
                    parts.append(f"направление: {old_p.direction} → {new_p.direction}")
                if old_p.lots != new_p.lots:
                    parts.append(f"лоты: {old_p.lots} → {new_p.lots}")
                if old_p.unit_size != new_p.unit_size:
                    parts.append(f"unit_size: {old_p.unit_size} → {new_p.unit_size}")
                lines.append(" | ".join(parts))
            text += "\n" + "\n".join(lines)

        await self._bot.send_message(chat_id=self._chat_id, text=text)

    async def _load_db_positions(self, account_id: str, s: AsyncSession) -> Dict[str, PositionState]:
        res = await s.execute(
            select(
                AccountInstrument.instrument_id,
                AccountInstrument.direction,
                AccountInstrument.lots,
                AccountInstrument.unit_size,
            ).where(AccountInstrument.account_id == account_id)
        )
        out: Dict[str, PositionState] = {}
        for instrument_id, direction, lots, unit_size in res.all():
            out[instrument_id] = PositionState(
                instrument_id=instrument_id,
                direction=str(direction),
                lots=int(lots) if lots is not None else 0,
                unit_size=int(unit_size) if unit_size is not None else None,
            )
        return out

    async def _ensure_instruments_and_get_atr(
            self,
            position_map: Dict[str, ti.PortfolioPosition],
            s: AsyncSession,
    ) -> Dict[str, float]:
        """
        Гарантирует, что Instrument есть в БД для всех uid.
        Возвращает map uid -> atr14 (0.0 если нет).
        """
        uids = list(position_map.keys())

        res_ins: Sequence[Instrument] = (await s.execute(
            select(Instrument).where(Instrument.instrument_id.in_(uids))
        )).scalars().all()

        existing_by_id = {i.instrument_id: i for i in res_ins}
        need_add = [uid for uid in uids if uid not in existing_by_id]

        candles: Dict[str, GetCandlesResponse] = {}
        expiration_dates: Dict[str, Any] = {}
        types: Dict[str, str] = {}
        ticker_map: Dict[str, str] = {}

        async def _fetch_one(uid: str):
            candles[uid] = await self._tclient.get_days_candles_for_2_months(uid)

            # тип/тикер/экспирация — только для новых
            response = await self._tclient.get_futures_response(uid)
            if response:
                expiration_dates[uid] = response.instrument.expiration_date
                types[uid] = "futures"
                ticker_map[uid] = response.instrument.ticker
            else:
                i_info = await self._tclient.get_info(uid)
                if i_info:
                    types[uid] = i_info.instrument.instrument_type
                    ticker_map[uid] = i_info.instrument.ticker

        if need_add:
            await asyncio.gather(*[_fetch_one(uid) for uid in need_add])

            now_utc = datetime.now(timezone.utc)
            rows_for_upsert: List[InstrumentIn] = []
            for uid in need_add:
                ind = IndicatorCalculator(candles[uid]).build_instrument_update()
                rows_for_upsert.append(
                    InstrumentIn(
                        instrument_id=uid,
                        ticker=ticker_map.get(uid) or position_map[uid].ticker,
                        check=True,
                        to_notify=True,
                        donchian_long_55=ind.get("donchian_long_55"),
                        donchian_short_55=ind.get("donchian_short_55"),
                        donchian_long_20=ind.get("donchian_long_20"),
                        donchian_short_20=ind.get("donchian_short_20"),
                        atr14=ind.get("atr14"),
                        last_update=now_utc,
                        expiration_date=expiration_dates.get(uid),
                        type=types.get(uid),
                    )
                )

            await self._db.upsert_instruments_bulk_data(rows_for_upsert, session=s)

            # добавим их в existing_by_id для построения atr_map
            for r in rows_for_upsert:
                existing_by_id[r.instrument_id] = Instrument(instrument_id=r.instrument_id, atr14=r.atr14)

        atr_map: Dict[str, float] = {}
        for uid in uids:
            inst = existing_by_id.get(uid)
            atr_map[uid] = float(inst.atr14) if inst and inst.atr14 else 0.0
        return atr_map


def _calc_count_contracts(portfolio: PortfolioOut, atr: float, price_point: float = 1) -> int:
    if not portfolio or not atr or not price_point:
        return 0

    atr_d = Decimal(str(atr))
    pp_d = Decimal(str(price_point))

    denom = atr_d * pp_d
    if denom <= 0:
        return 0

    # profit (руб) из относительной доходности (%)
    p = portfolio.expected_yield_percent
    if p <= 0:
        profit = Decimal(0)
    else:
        k = Decimal(1) + p / Decimal(100)
        initial_sum = portfolio.total_amount / k
        profit = portfolio.total_amount - initial_sum

        if profit < 0:
            profit = Decimal(0)

    # формула: (текущая стоимость - прибыль (или 0)) / (atr * price_point * 100) , округление вниз
    value = (portfolio.total_amount - profit) / (denom * 100)

    if value <= 0:
        return 0

    # округление вниз
    count = int(value.to_integral_value(rounding=ROUND_FLOOR))
    return count
