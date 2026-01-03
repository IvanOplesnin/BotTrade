import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from tinkoff.invest.utils import quotation_to_decimal as q2d, money_to_decimal as m2d

from clients.tinkoff.client import TClient
from database.redis.client import RedisClient


class PortfolioOut(BaseModel):
    account_id: str
    total_amount: Decimal
    expected_yield_percent: Decimal


class PortfolioService:
    def __init__(self, tclient: TClient, redis: RedisClient):
        self._redis = redis
        self._tclient = tclient
        self.log = logging.getLogger(self.__class__.__name__)

    async def get_portfolio(self, account_id: str) -> Optional[PortfolioOut]:
        data = await self._redis.get_portfolio_metrics(account_id)
        if data:
            result = PortfolioOut(
                account_id=account_id,
                total_amount=Decimal(data["total_amount"]),
                expected_yield_percent=Decimal(data["expected_yield_percent"]),
            )
            return result

        portfolio = None
        try:
            portfolio = await self._tclient.get_portfolio(account_id)
        except Exception as e:
            self.log.error(f"Tclient error: {e}", extra={"account_id": account_id})

        if portfolio:
            result = PortfolioOut(
                account_id=account_id,
                total_amount=m2d(portfolio.total_amount_portfolio),
                expected_yield_percent=q2d(portfolio.expected_yield),
            )
            try:
                await self._redis.set_portfolio_metrics(
                    account_id=account_id,
                    total_amount=str(result.total_amount),
                    expected_yield_percent=str(result.expected_yield_percent),
                    ts_ms=int(datetime.now().timestamp() * 1000)
                )
                return result
            except Exception as e:
                self.log.error(f"Redis error: {e}", extra={"account_id": account_id})
        return None
