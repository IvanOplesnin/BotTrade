from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from clients.tinkoff.portfolio_svc import PortfolioOut
from clients.tinkoff.sdk import q2d
from database.pgsql.models import Instrument
from utils.utils import price_point


@dataclass(frozen=True)
class InstrumentInfoResult:
    instrument: Instrument
    side: Literal["long", "short"]
    price_point_value: Optional[float]
    last_price: Optional[float]
    portfolios: list[PortfolioOut]


class InstrumentInfoService:
    def __init__(
            self,
            *,
            db: Any,
            market_data_client: Any,
            redis: Any,
            portfolio_svc: Any,
    ):
        self._db = db
        self._market_data_client = market_data_client
        self._redis = redis
        self._portfolio_svc = portfolio_svc

    async def build(
            self,
            *,
            instrument: Instrument,
            side: Literal["long", "short"],
    ) -> InstrumentInfoResult:
        price_point_value = await self._price_point_value(instrument.instrument_id)
        last_price = await self._last_price(instrument.instrument_id)
        portfolios = await self._portfolios()

        return InstrumentInfoResult(
            instrument=instrument,
            side=side,
            price_point_value=price_point_value,
            last_price=last_price,
            portfolios=portfolios,
        )

    async def _price_point_value(self, instrument_id: str) -> Optional[float]:
        response = await self._market_data_client.get_min_price_increment_amount(instrument_id)
        if not response:
            return None
        return price_point(response)

    async def _last_price(self, instrument_id: str) -> Optional[float]:
        cached = await self._redis.get_last_price(instrument_id)
        if cached:
            return float(cached["price"])

        last_price_obj = await self._market_data_client.get_last_price(instrument_id)
        if not last_price_obj:
            return None

        last_price = float(q2d(last_price_obj.price))
        await self._redis.set_last_price_if_newer(
            instrument_id,
            str(last_price),
            ts_ms=int(last_price_obj.time.timestamp() * 1000),
        )
        return last_price

    async def _portfolios(self) -> list[PortfolioOut]:
        portfolios: list[PortfolioOut] = []
        async with self._db.session_factory() as session:
            accounts = await self._db.list_accounts(session)

        for account in accounts:
            portfolios.append(
                await self._portfolio_svc.get_portfolio(account.account_id, account.name)
            )
        return portfolios
