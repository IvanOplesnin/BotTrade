from datetime import datetime, timezone
from typing import Sequence, Optional, Iterable, Union, Mapping, Any, List

from sqlalchemy import select, delete, update, func, or_, and_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.pgsql.models import Base, Instrument, Account, AccountInstrument
from database.pgsql.schemas import InstrumentIn, InstrumentPatch

InstrumentLike = Union[Mapping[str, Any], InstrumentIn]


def _to_payload(data: InstrumentLike, *, require_id: bool = True) -> dict:
    """Привести dict/Pydantic к dict с нужными ключами. exclude_unset=True — мягкий upsert."""
    if isinstance(data, InstrumentIn):
        payload = data.model_dump(exclude_unset=True)
    else:
        payload = dict(data)

    if require_id and not payload.get("instrument_id"):
        raise ValueError("instrument_id is required")
    return payload


class Repository:
    """
    CRUD-репозиторий.
    """

    def __init__(self, url: str, echo: bool = False):
        self._engine = create_async_engine(url=url, echo=echo, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self._engine, expire_on_commit=False,
                                                  class_=AsyncSession)

    # ---------- create schema ----------
    async def create_schema_if_not_exists(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # ---------- Instruments ----------
    @staticmethod
    async def upsert_instrument_data(
            data: InstrumentLike,
            session: AsyncSession,
            update_ts: bool = True,
    ) -> None:
        """
        Upsert одного инструмента. Принимает dict или InstrumentIn.
        Не затирает NULL-ами существующие значения, обновляет только при реальных изменениях.
        """
        payload = _to_payload(data)
        if update_ts and "last_update" not in payload:
            payload["last_update"] = datetime.now(timezone.utc)

        ins = pg_insert(Instrument).values(**payload)

        set_map = {
            "ticker": func.coalesce(ins.excluded.ticker, Instrument.ticker),
            "check": func.coalesce(ins.excluded.check, Instrument.check),
            "to_notify": func.coalesce(ins.excluded.to_notify, Instrument.to_notify),
            "donchian_long_55": func.coalesce(ins.excluded.donchian_long_55,
                                              Instrument.donchian_long_55),
            "donchian_short_55": func.coalesce(ins.excluded.donchian_short_55,
                                               Instrument.donchian_short_55),
            "donchian_long_20": func.coalesce(ins.excluded.donchian_long_20,
                                              Instrument.donchian_long_20),
            "donchian_short_20": func.coalesce(ins.excluded.donchian_short_20,
                                               Instrument.donchian_short_20),
            "atr14": func.coalesce(ins.excluded.atr14, Instrument.atr14),
            "last_update": func.coalesce(ins.excluded.last_update, Instrument.last_update),
            "expiration_date": func.coalesce(ins.excluded.expiration_date, Instrument.expiration_date),
        }

        changed = or_(
            Instrument.ticker.is_distinct_from(ins.excluded.ticker),
            Instrument.check.is_distinct_from(ins.excluded.check),
            Instrument.to_notify.is_distinct_from(ins.excluded.to_notify),
            Instrument.donchian_long_55.is_distinct_from(ins.excluded.donchian_long_55),
            Instrument.donchian_short_55.is_distinct_from(ins.excluded.donchian_short_55),
            Instrument.donchian_long_20.is_distinct_from(ins.excluded.donchian_long_20),
            Instrument.donchian_short_20.is_distinct_from(ins.excluded.donchian_short_20),
            Instrument.atr14.is_distinct_from(ins.excluded.atr14),
            Instrument.last_update.is_distinct_from(ins.excluded.last_update),
            Instrument.expiration_date.is_distinct_from(ins.excluded.expiration_date),
        )

        stmt = ins.on_conflict_do_update(
            index_elements=[Instrument.instrument_id],
            set_=set_map,
            where=changed,
        )
        await session.execute(stmt)

    @staticmethod
    async def upsert_instruments_bulk_data(
            items: Iterable[InstrumentLike],
            session: AsyncSession,
            update_ts: bool = True,
    ) -> None:
        """
        Батч-upsert инструментов. На вход — iterable dict/InstrumentIn.
        Не затирает NULL-ами, UPDATE только при реальных изменениях.
        """
        rows = []
        now_utc = datetime.now(timezone.utc)
        for it in items:
            row = _to_payload(it)
            if update_ts and "last_update" not in row:
                row["last_update"] = now_utc
            rows.append(row)
        if not rows:
            return

        ins = pg_insert(Instrument).values(rows)

        set_map = {
            "ticker": func.coalesce(ins.excluded.ticker, Instrument.ticker),
            "check": func.coalesce(ins.excluded.check, Instrument.check),
            "to_notify": func.coalesce(ins.excluded.to_notify, Instrument.to_notify),
            "donchian_long_55": func.coalesce(ins.excluded.donchian_long_55,
                                              Instrument.donchian_long_55),
            "donchian_short_55": func.coalesce(ins.excluded.donchian_short_55,
                                               Instrument.donchian_short_55),
            "donchian_long_20": func.coalesce(ins.excluded.donchian_long_20,
                                              Instrument.donchian_long_20),
            "donchian_short_20": func.coalesce(ins.excluded.donchian_short_20,
                                               Instrument.donchian_short_20),
            "atr14": func.coalesce(ins.excluded.atr14, Instrument.atr14),
            "last_update": func.coalesce(ins.excluded.last_update, Instrument.last_update),
            "expiration_date": func.coalesce(ins.excluded.expiration_date, Instrument.expiration_date),
        }

        changed = or_(
            Instrument.ticker.is_distinct_from(ins.excluded.ticker),
            Instrument.check.is_distinct_from(ins.excluded.check),
            Instrument.to_notify.is_distinct_from(ins.excluded.to_notify),
            Instrument.donchian_long_55.is_distinct_from(ins.excluded.donchian_long_55),
            Instrument.donchian_short_55.is_distinct_from(ins.excluded.donchian_short_55),
            Instrument.donchian_long_20.is_distinct_from(ins.excluded.donchian_long_20),
            Instrument.donchian_short_20.is_distinct_from(ins.excluded.donchian_short_20),
            Instrument.atr14.is_distinct_from(ins.excluded.atr14),
            Instrument.last_update.is_distinct_from(ins.excluded.last_update),
            Instrument.expiration_date.is_distinct_from(ins.excluded.expiration_date),
        )

        stmt = ins.on_conflict_do_update(
            index_elements=[Instrument.instrument_id],
            set_=set_map,
            where=changed,
        )
        await session.execute(stmt)

    @staticmethod
    async def get_instrument(instrument_id: str, session: AsyncSession) -> Optional[Instrument]:
        stmt = select(Instrument).where(Instrument.instrument_id == instrument_id)
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def list_instruments(session: AsyncSession) -> Sequence[Instrument]:
        stmt = select(Instrument)
        return (await session.execute(stmt)).scalars().all()

    @staticmethod
    async def list_instruments_by_ids(ids: list[str], session: AsyncSession) -> Sequence[
        Instrument
    ]:
        stmt = select(Instrument).where(Instrument.instrument_id.in_(ids))
        return (await session.execute(stmt)).scalars().all()

    @staticmethod
    async def list_instruments_checked(session: AsyncSession) -> Sequence[
        tuple[Instrument, Optional[AccountInstrument]]
    ]:
        stmt = (
            select(Instrument, AccountInstrument)
            .outerjoin(AccountInstrument,
                       AccountInstrument.instrument_id == Instrument.instrument_id)
            .where(Instrument.check.is_(True))
        )
        return (await session.execute(stmt)).unique().all()

    @staticmethod
    async def delete_instrument(instrument_id: str, session: AsyncSession) -> None:
        stmt = delete(Instrument).where(Instrument.instrument_id == instrument_id)
        await session.execute(stmt)

    @staticmethod
    async def update_instrument_from_patch(
            instrument_id: str,
            patch: Union[Mapping[str, Any], InstrumentPatch],
            session: AsyncSession,
            touch_ts: bool = True,
    ) -> None:
        if isinstance(patch, InstrumentPatch):
            values = patch.model_dump(exclude_unset=True)
        else:
            values = dict(patch)

        if not values:
            return

        if touch_ts and "last_update" not in values:
            values["last_update"] = datetime.now(timezone.utc)

        stmt = (
            update(Instrument)
            .where(Instrument.instrument_id == instrument_id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await session.execute(stmt)

    @staticmethod
    async def set_checked_bulk(ids: list[str], session: AsyncSession, check: bool = True) -> None:
        if not ids:
            return
        stmt = (
            update(Instrument)
            .where(Instrument.instrument_id.in_(ids))
            .values(check=check)
            .execution_options(synchronize_session=False)
        )
        await session.execute(stmt)

    @staticmethod
    async def set_notify(uid: str, notify: bool, session: AsyncSession) -> None:
        stmt = (
            update(Instrument)
            .where(Instrument.instrument_id == uid)
            .values(to_notify=notify)
        )
        await session.execute(stmt)

    # ---------- Accounts ----------
    @staticmethod
    async def upsert_account(
            account_id: str,
            name: str,
            check: bool,
            session: AsyncSession,
    ) -> None:
        ins = (
            pg_insert(Account)
            .values(account_id=account_id, name=name, check=check)
            .on_conflict_do_update(
                index_elements=[Account.account_id],
                set_={"name": name, "check": check},
            )
        )
        await session.execute(ins)

    @staticmethod
    async def list_accounts(session: AsyncSession) -> Sequence[Account]:
        stmt = select(Account).order_by(Account.account_id)
        return (await session.execute(stmt)).scalars().all()

    @staticmethod
    async def delete_account(account_id: str, session: AsyncSession) -> None:
        stmt = delete(Account).where(Account.account_id == account_id)
        await session.execute(stmt)
        return

        # ---------- Positions (AccountInstrument) ----------

    @staticmethod
    async def set_position(
            account_id: str,
            instrument_id: str,
            session: AsyncSession,
            direction: Optional[str] = None,
    ) -> None:
        stmt = (
            pg_insert(AccountInstrument)
            .values(account_id=account_id, instrument_id=instrument_id,
                    direction=direction)
            .on_conflict_do_update(
                index_elements=[AccountInstrument.account_id, AccountInstrument.instrument_id],
                set_={"direction": direction},
            )
        )
        await session.execute(stmt)

    @staticmethod
    async def set_position_bulk(
            positions: List[Union[Mapping[str, Any], AccountInstrument]],
            session: AsyncSession,
    ) -> None:
        if not positions:
            return
        if isinstance(positions[0], AccountInstrument):
            rows = [
                {
                    "account_id": p.account_id,
                    "instrument_id": p.instrument_id,
                    "direction": p.direction,
                    "lots": p.lots,
                    "unit_size": p.unit_size,
                }
                for p in positions
            ]
        else:
            rows = positions

        ins_ai = pg_insert(AccountInstrument).values(rows)

        changed = or_(
            AccountInstrument.direction.is_distinct_from(ins_ai.excluded.direction),
            AccountInstrument.lots.is_distinct_from(ins_ai.excluded.lots),
        )
        need_fill_unit_size = and_(
            AccountInstrument.unit_size.is_(None),
            ins_ai.excluded.unit_size.is_not(None),
        )
        stmt = ins_ai.on_conflict_do_update(
            index_elements=[AccountInstrument.account_id, AccountInstrument.instrument_id],
            set_={
                "direction": ins_ai.excluded.direction,
                "lots": ins_ai.excluded.lots,
                # ✅ заполняем только если в БД NULL
                "unit_size": func.coalesce(AccountInstrument.unit_size, ins_ai.excluded.unit_size),
            },
            where=or_(changed, need_fill_unit_size),
        )

        await session.execute(stmt)

    @staticmethod
    async def unset_position(account_id: str, instrument_id: str, session: AsyncSession) -> None:
        stmt = (
            update(AccountInstrument)
            .where(AccountInstrument.account_id == account_id,
                   AccountInstrument.instrument_id == instrument_id)
            .values(direction=None)
        )
        await session.execute(stmt)

    @staticmethod
    async def list_positions_for_account(
            account_id: str,
            session: Optional[AsyncSession] = None,
    ) -> Sequence[tuple[AccountInstrument, Instrument]]:
        stmt = (
            select(AccountInstrument)
            .join(Instrument,
                  AccountInstrument.instrument_id == Instrument.instrument_id)
            .where(AccountInstrument.account_id == account_id)
        )
        return (await session.execute(stmt)).unique().all()

    @staticmethod
    async def list_position_by_id(instrument_id: str, session: AsyncSession) -> Sequence[
        tuple[AccountInstrument, Instrument]
    ]:
        stmt = (
            select(AccountInstrument)
            .join(Instrument,
                  AccountInstrument.instrument_id == Instrument.instrument_id)
            .where(AccountInstrument.instrument_id == instrument_id)
        )
        return (await session.execute(stmt)).unique().all()

    @staticmethod
    async def list_positions(session: AsyncSession) -> Sequence[
        tuple[AccountInstrument, Instrument]
    ]:
        stmt = (select(AccountInstrument, Instrument)
                .join(Instrument,
                      AccountInstrument.instrument_id == Instrument.instrument_id))
        return (await session.execute(stmt)).unique().all()

    @staticmethod
    async def delete_position(account_id: str, instrument_id: str, session: AsyncSession) -> None:
        stmt = delete(AccountInstrument).where(
            AccountInstrument.account_id == account_id,
            AccountInstrument.instrument_id == instrument_id,
        )
        await session.execute(stmt)

    @staticmethod
    async def delete_positions_bulk(
            account_id: str,
            instrument_ids: Iterable[str],
            session: AsyncSession
    ) -> None:
        if not instrument_ids:
            return
        stmt = (
            delete(AccountInstrument)
            .where(AccountInstrument.account_id == account_id,
                   AccountInstrument.instrument_id.in_(instrument_ids))
        )
        await session.execute(stmt)

    @staticmethod
    async def delete_all_positions_for_account(account_id: str, session: AsyncSession) -> None:
        stmt = delete(AccountInstrument).where(AccountInstrument.account_id == account_id)
        await session.execute(stmt)

    @staticmethod
    async def get_instrument_with_positions(instrument_id: str, session: AsyncSession) -> Optional[
        tuple[Instrument, AccountInstrument]
    ]:
        stmt = (
            select(Instrument, AccountInstrument)
            .outerjoin(
                AccountInstrument,
                and_(
                    AccountInstrument.instrument_id == Instrument.instrument_id,
                )
            )
            .where(Instrument.instrument_id == instrument_id)
            .limit(1)
        )
        return (await session.execute(stmt)).unique().first()

    @staticmethod
    async def get_account(account_id: str, s: AsyncSession) -> Optional[Account]:
        stmt = (select(Account).where(Account.account_id == account_id))
        return (await s.execute(stmt)).scalar_one_or_none()
