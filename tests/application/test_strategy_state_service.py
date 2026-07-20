from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from application.dto import ActiveStrategyBinding
from application.strategy_state import StrategyStateService

pytestmark = pytest.mark.asyncio


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeRepository:
    def __init__(self):
        self.bindings = []
        self.candles_by_key = {}
        self.states = []
        self.sessions = []

    @asynccontextmanager
    async def session_factory(self):
        session = FakeSession()
        self.sessions.append(session)
        yield session

    async def list_active_strategy_bindings(self, session):
        return list(self.bindings)

    async def list_candles(self, *, instrument_id, timeframe, limit, session):
        candles = self.candles_by_key.get((instrument_id, timeframe), [])
        return candles[-limit:]

    async def upsert_strategy_state(self, item, session):
        self.states.append(dict(item))


def _binding(**kwargs):
    instrument_id = kwargs.get("instrument_id", "UID1")
    return ActiveStrategyBinding(
        binding_id=kwargs.get("binding_id", 7),
        strategy_code=kwargs.get("strategy_code", "donchian_breakout"),
        version=kwargs.get("version", 1),
        instrument_id=instrument_id,
        account_id=kwargs.get("account_id"),
        mode="notify",
        params=kwargs.get(
            "params",
            {
                "entry_period": 5,
                "exit_period": 3,
                "atr_period": 2,
                "timeframe": "day",
            },
        ),
        instrument=SimpleNamespace(instrument_id=instrument_id, check=True),
    )


def _candles(count: int):
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return [
        SimpleNamespace(
            time=start + timedelta(days=index),
            high=float(index + 1),
            low=float(100 - index),
            close=float(index + 1),
            is_complete=True,
        )
        for index in range(count)
    ]


async def test_refresh_all_calculates_ready_state_from_candles():
    db = FakeRepository()
    db.bindings = [_binding()]
    db.candles_by_key[("UID1", "day")] = _candles(7)

    result = await StrategyStateService(db).refresh_all()

    assert result.refreshed_count == 1
    assert result.warming_count == 0
    assert result.skipped_count == 0
    assert db.states[0]["binding_id"] == 7
    assert db.states[0]["timeframe"] == "day"
    assert db.states[0]["status"] == "ready"
    assert db.states[0]["state_json"]["donchian_long_5"] == 7.0
    assert db.states[0]["state_json"]["warmup_required"] == 7
    assert db.states[0]["state_json"]["candles_loaded"] == 7
    assert db.states[0]["last_market_event_time"] == db.candles_by_key[("UID1", "day")][-1].time
    assert db.sessions[-1].commits == 1


async def test_refresh_all_marks_state_as_warming_when_candles_are_missing():
    db = FakeRepository()
    db.bindings = [_binding()]
    db.candles_by_key[("UID1", "day")] = _candles(2)

    result = await StrategyStateService(db).refresh_all()

    assert result.refreshed_count == 0
    assert result.warming_count == 1
    assert result.skipped_count == 0
    assert db.states[0]["status"] == "warming"
    assert db.states[0]["state_json"]["candles_loaded"] == 2
    assert db.sessions[-1].commits == 1


async def test_refresh_all_skips_unknown_strategy():
    db = FakeRepository()
    db.bindings = [_binding(strategy_code="unknown")]

    result = await StrategyStateService(db).refresh_all()

    assert result.refreshed_count == 0
    assert result.warming_count == 0
    assert result.skipped_count == 1
    assert db.states == []
    assert db.sessions[-1].commits == 1
