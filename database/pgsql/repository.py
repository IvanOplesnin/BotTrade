from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from database.pgsql.models import Base, Instrument, Position


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

    async def add_position(self, position: Position) -> None:
        pass



