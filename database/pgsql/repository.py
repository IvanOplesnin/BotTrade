from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from database.pgsql.models import Base, Instrument, Account


class Repository:

    def __init__(self, url):
        self._url = url

        self._async_engine = create_async_engine(
            url=self._url,
            echo=False
        )
        self._async_session = async_sessionmaker(
            bind=self._async_engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def remake_db(self):
        async with self._async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    async def create_db_if_exists(self):
        async with self._async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def check_exist_instrument(self, instrument: Instrument) -> bool:
        async with self._async_session() as session:
            stmt = select(Instrument).where(Instrument.instrument_id == instrument.instrument_id)
            result = await session.execute(stmt)
            instrument = result.scalar_one_or_none()
            return True if instrument else False

    async def add_instrument(self, instrument: Instrument) -> None:
        if await self.check_exist_instrument(instrument):
            return

        async with self._async_session() as session:
            session.add(instrument)
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
            for row in await session.execute(stmt):
                yield {
                    'account_id': row.account_id,
                    'balance': row.balance,
                    'currency': row.currency,
                    'portfolio': row.portfolio
                }




