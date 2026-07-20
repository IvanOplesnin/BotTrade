from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from application.dto import ActiveStrategyBinding
from application.strategy_subscriptions import StrategySubscriptionService
from domain.strategies import CandleRequirement, MarketDataRequirements, StrategyRegistry

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class FakeStrategy:
    code: str
    version: int
    requirements_result: MarketDataRequirements

    def requirements(self, params=None):
        return self.requirements_result

    def decide(self, context, params=None):
        return None


class FakeRepository:
    def __init__(self):
        self.bindings = []
        self.sessions = 0

    @asynccontextmanager
    async def session_factory(self):
        self.sessions += 1
        yield object()

    async def list_active_strategy_bindings(self, session):
        return list(self.bindings)


def _binding(**kwargs) -> ActiveStrategyBinding:
    instrument_id = kwargs.get("instrument_id", "UID1")
    return ActiveStrategyBinding(
        binding_id=kwargs.get("binding_id", 1),
        strategy_code=kwargs.get("strategy_code", "daily_breakout"),
        version=kwargs.get("version", 1),
        instrument_id=instrument_id,
        account_id=None,
        mode="notify",
        params=kwargs.get("params", {"timeframe": "day"}),
        instrument=SimpleNamespace(instrument_id=instrument_id),
    )


async def test_build_plan_reads_bindings_and_merges_strategy_requirements():
    db = FakeRepository()
    db.bindings = [
        _binding(binding_id=1, instrument_id="UID1", strategy_code="daily_breakout"),
        _binding(binding_id=2, instrument_id="UID1", strategy_code="daily_reversion"),
    ]
    registry = StrategyRegistry([
        FakeStrategy(
            code="daily_breakout",
            version=1,
            requirements_result=MarketDataRequirements(
                candles=(CandleRequirement(timeframe="day", warmup=70),),
                last_price=True,
            ),
        ),
        FakeStrategy(
            code="daily_reversion",
            version=1,
            requirements_result=MarketDataRequirements(
                candles=(CandleRequirement(timeframe="day", warmup=120),),
                last_price=True,
                trades=True,
            ),
        ),
    ])

    plan = await StrategySubscriptionService(db, strategy_registry=registry).build_plan()

    assert db.sessions == 1
    assert plan.last_price_instrument_ids == ("UID1",)
    assert [(item.instrument_id, item.timeframe, item.warmup) for item in plan.candle_subscriptions] == [
        ("UID1", "day", 120),
    ]
    assert plan.trade_instrument_ids == ("UID1",)
