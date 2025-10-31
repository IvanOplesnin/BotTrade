import asyncio
from datetime import datetime, timezone
from typing import Sequence, Optional

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from database.pgsql.models import Base, Instrument, Account


class Repository:

    def __init__(self, url):
        self._url = url
        self._async_engine = create_async_engine(url=self._url, echo=False)
        self._async_session = async_sessionmaker(bind=self._async_engine,
                                                 expire_on_commit=False, class_=AsyncSession)

    async def remake_db(self):
        async with self._async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    async def create_db_if_exists(self):
        async with self._async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def check_exist_instrument(self, instrument: Instrument,
                                     session: AsyncSession = None) -> bool:
        stmt = select(Instrument).where(Instrument.instrument_id == instrument.instrument_id)
        if session:
            result = await session.execute(stmt)
            instrument = result.scalar_one_or_none()
        else:
            async with self._async_session() as session:
                result = await session.execute(stmt)
                instrument = result.scalar_one_or_none()
        return True if instrument else False

    async def add_instrument(self, instrument: Instrument) -> None:
        async with self._async_session() as session:
            if await self.check_exist_instrument(instrument, session):
                return
            session.add(instrument)
            await session.commit()

    async def add_instrument_or_update(self, *instrument: Instrument):
        async with self._async_session() as session:
            for instr in instrument:
                if await self.check_exist_instrument(instr, session):
                    instr_in_position = (
                        await session.execute(
                            select(Instrument).where(
                                Instrument.instrument_id == instr.instrument_id
                            ).where(Instrument.in_position == True)
                        )
                    ).scalar_one_or_none()
                    stmt = (
                        update(Instrument)
                        .where(Instrument.instrument_id == instr.instrument_id)
                        .values(
                            in_position=True if instr_in_position else instr.in_position,
                            check=True if instr_in_position else instr.check,
                            donchian_long_55=instr.donchian_long_55,
                            donchian_short_55=instr.donchian_short_55,
                            donchian_long_20=instr.donchian_long_20,
                            donchian_short_20=instr.donchian_short_20,
                            atr14=instr.atr14,
                            last_update=datetime.now(timezone.utc),
                            direction=(instr_in_position.direction if
                                       instr_in_position else instr.direction),
                        )
                        .execution_options(synchronize_session=False)
                    )
                    await session.execute(stmt)
                else:
                    session.add(instr)
            await session.commit()

    async def check_exist_account(self, account: Account) -> bool:
        async with self._async_session() as session:
            stmt = select(Account).where(Account.account_id == account.account_id)
            result = await session.execute(stmt)
            acc = result.scalar_one_or_none()
            return True if acc else False

    async def add_portfolio(self, account: Account) -> None:
        if await self.check_exist_account(account):
            return

        async with self._async_session() as session:
            session.add(account)
            await session.commit()

    async def get_accounts(self):
        stmt = select(Account).order_by(Account.account_id)
        async with self._async_session() as session:
            result = await session.execute(stmt)
            res: Sequence[Account] = result.scalars().all()
            return res

    async def delete_account(self, account_id: str):
        async with self._async_session() as session:
            stmt = delete(Account).where(Account.account_id == account_id)
            await session.execute(stmt)
            await session.commit()

    async def delete_instrument(self, instrument_uid):
        if instrument_uid:
            async with self._async_session() as session:
                stmt = delete(Instrument).where(Instrument.instrument_id == instrument_uid)
                await session.execute(stmt)
                await session.commit()

    async def check_to_false(self, *instrument_uid):
        async with self._async_session() as session:
            stmt = (
                update(Instrument)
                .where(Instrument.instrument_id.in_(instrument_uid))
                .values(check=False, in_position=False, direction=None)
                .execution_options(synchronize_session=False)
            )
            await session.execute(stmt)
            await session.commit()

    async def get_checked_instruments(self, session=None):
        result = None
        stmt = select(Instrument).where(Instrument.check == True).where(
            Instrument.in_position == False)
        if session:
            result = await session.execute(stmt)
        else:
            async with self._async_session() as session:
                result = await session.execute(stmt)
        instruments = result.scalars().all()
        return instruments

    async def get_indicators_by_uid(self, uid, session=None) -> Optional[Instrument]:
        stmt = select(Instrument).where(Instrument.instrument_id == uid)
        if session:
            result = (await session.execute(stmt)).scalar_one_or_none()
            return result
        else:
            async with self._async_session() as session:
                result = (await session.execute(stmt)).scalar_one_or_none()
                return result

    async def get_instruments(self, session=None) -> Sequence[Instrument]:
        stmt = select(Instrument)
        result = []
        if session:
            result = await session.execute(stmt)
        else:
            async with self._async_session() as session:
                result = await session.execute(stmt)
        return result.scalars().all()

    async def update_instrument_indicators(self, uid: str, indicators: dict[str, float],
                                           session=None):
        stmt = (
            update(Instrument).where(Instrument.instrument_id == uid)
            .values(**indicators, last_update=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        if session:
            await session.execute(stmt)
            await session.commit()
        else:
            async with self._async_session() as session:
                await session.execute(stmt)
                await session.commit()

    async def all_notify_to_true(self):
        async with self._async_session() as session:
            instruments: Sequence[Instrument] = await self.get_instruments(session)
            for instrument in instruments:
                await session.execute(
                    update(Instrument)
                    .where(Instrument.instrument_id == instrument.instrument_id)
                    .values(to_notify=True)
                    .execution_options(synchronize_session=False)
                )
                await session.commit()

    async def notify_to_false(self, instrument_id, session=None):
        async with self._async_session() as session:
            await session.execute(
                update(Instrument)
                .where(Instrument.instrument_id == instrument_id)
                .values(to_notify=False)
            )
            await session.commit()

    async def notify_to_true(self, instrument_id, session=None):
        async with self._async_session() as session:
            await session.execute(
                update(Instrument)
                .where(Instrument.instrument_id == instrument_id)
                .values(to_notify=True)
            )
            await session.commit()


if __name__ == '__main__':
    async def main():
        url = 'postgresql+asyncpg://postgres:postgres@localhost:5437/data_positions'
        repo = Repository(url)
        await repo.remake_db()

    asyncio.run(main())
