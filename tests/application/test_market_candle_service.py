from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from application.dto import StrategyStateRefreshResult
from application.market_candles import MarketCandleService
from domain.stream_events import CandleEvent

pytestmark = pytest.mark.asyncio


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeRepository:
    def __init__(self):
        self.rows = []
        self.sessions = []

    @asynccontextmanager
    async def session_factory(self):
        session = FakeSession()
        self.sessions.append(session)
        yield session

    async def upsert_candles(self, items, session):
        self.rows.extend(dict(item) for item in items)


class FakeStrategyStateService:
    def __init__(self):
        self.calls = []
        self.result = StrategyStateRefreshResult(
            refreshed_count=1,
            warming_count=0,
            skipped_count=0,
        )

    async def refresh_instruments(self, instrument_ids):
        self.calls.append(list(instrument_ids))
        return self.result


def _candle_event(*, is_complete: bool = True, time=None) -> CandleEvent:
    return CandleEvent(
        instrument_id="UID1",
        interval="CandleInterval.CANDLE_INTERVAL_DAY",
        open=Decimal("10.1"),
        high=Decimal("11.2"),
        low=Decimal("9.9"),
        close=Decimal("10.7"),
        time=time or datetime(2026, 7, 17, tzinfo=timezone.utc),
        volume=1200,
        is_complete=is_complete,
    )


async def test_process_candle_stores_complete_candle_and_refreshes_strategy_state():
    db = FakeRepository()
    strategy_state = FakeStrategyStateService()

    result = await MarketCandleService(db, strategy_state).process_candle(
        _candle_event(is_complete=True)
    )

    assert result.stored is True
    assert result.strategy_state == strategy_state.result
    assert strategy_state.calls == [["UID1"]]
    assert db.sessions[-1].commits == 1
    assert db.rows == [
        {
            "instrument_id": "UID1",
            "timeframe": "day",
            "time": datetime(2026, 7, 17, tzinfo=timezone.utc),
            "open": Decimal("10.1"),
            "high": Decimal("11.2"),
            "low": Decimal("9.9"),
            "close": Decimal("10.7"),
            "volume": 1200,
            "is_complete": True,
        }
    ]


async def test_process_candle_stores_incomplete_candle_without_strategy_refresh():
    db = FakeRepository()
    strategy_state = FakeStrategyStateService()

    result = await MarketCandleService(db, strategy_state).process_candle(
        _candle_event(is_complete=False)
    )

    assert result.stored is True
    assert result.strategy_state is None
    assert strategy_state.calls == []
    assert db.rows[0]["is_complete"] is False
    assert db.sessions[-1].commits == 1


async def test_process_candle_skips_event_without_time():
    db = FakeRepository()
    strategy_state = FakeStrategyStateService()
    event = CandleEvent(
        instrument_id="UID1",
        interval="day",
        open=Decimal("10.1"),
        high=Decimal("11.2"),
        low=Decimal("9.9"),
        close=Decimal("10.7"),
    )

    result = await MarketCandleService(db, strategy_state).process_candle(event)

    assert result.stored is False
    assert db.rows == []
    assert db.sessions == []
    assert strategy_state.calls == []
