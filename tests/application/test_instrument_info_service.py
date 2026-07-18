from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from application.instrument_info import InstrumentInfoService
from tests.test_market_data_handler.factories import quotation

pytestmark = pytest.mark.asyncio


class FakeRedis:
    def __init__(self, cached=None):
        self.cached = cached
        self.saved = []

    async def get_last_price(self, instrument_id):
        return self.cached

    async def set_last_price_if_newer(self, instrument_id, price, ts_ms):
        self.saved.append((instrument_id, price, ts_ms))


class FakeMarketDataClient:
    def __init__(self):
        self.last_price_calls = []

    async def get_min_price_increment_amount(self, instrument_id):
        return None

    async def get_last_price(self, instrument_id):
        self.last_price_calls.append(instrument_id)
        return SimpleNamespace(
            price=quotation(123, 450000000),
            time=datetime(2026, 7, 17, tzinfo=timezone.utc),
        )


class FakeDb:
    @asynccontextmanager
    async def session_factory(self):
        yield object()

    async def list_accounts(self, session):
        return [SimpleNamespace(account_id="ACC1", name="Main")]


class FakePortfolioService:
    def __init__(self):
        self.calls = []

    async def get_portfolio(self, account_id, name):
        self.calls.append((account_id, name))
        return SimpleNamespace(name=name, total_amount=Decimal("1000"), expected_yield_percent=0)


def _service(redis):
    portfolio_svc = FakePortfolioService()
    return (
        InstrumentInfoService(
            db=FakeDb(),
            market_data_client=FakeMarketDataClient(),
            redis=redis,
            portfolio_svc=portfolio_svc,
        ),
        portfolio_svc,
    )


async def test_instrument_info_service_uses_cached_last_price():
    redis = FakeRedis(cached={"price": "101.5"})
    service, portfolio_svc = _service(redis)
    instrument = SimpleNamespace(instrument_id="UID1")

    result = await service.build(instrument=instrument, side="long")

    assert result.instrument is instrument
    assert result.side == "long"
    assert result.last_price == 101.5
    assert result.price_point_value is None
    assert [portfolio.name for portfolio in result.portfolios] == ["Main"]
    assert portfolio_svc.calls == [("ACC1", "Main")]
    assert redis.saved == []


async def test_instrument_info_service_fetches_and_caches_last_price_when_missing():
    redis = FakeRedis()
    service, _ = _service(redis)
    instrument = SimpleNamespace(instrument_id="UID2")

    result = await service.build(instrument=instrument, side="short")

    assert result.last_price == 123.45
    expected_ts_ms = int(datetime(2026, 7, 17, tzinfo=timezone.utc).timestamp() * 1000)
    assert redis.saved == [("UID2", "123.45", expected_ts_ms)]
