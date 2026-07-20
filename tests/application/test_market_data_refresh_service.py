from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from application.dto import StrategyStateRefreshResult
from application.market_data_refresh import MarketDataRefreshService

pytestmark = pytest.mark.asyncio


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeRepository:
    def __init__(self, instruments):
        self.instruments = instruments
        self.patches = []
        self.candles = []
        self.sessions = []

    @asynccontextmanager
    async def session_factory(self):
        session = FakeSession()
        self.sessions.append(session)
        yield session

    async def list_instruments(self, session):
        return list(self.instruments)

    async def update_instrument_from_patch(
            self,
            instrument_id,
            patch,
            session,
            touch_ts=True,
    ):
        self.patches.append(
            {
                "instrument_id": instrument_id,
                "patch": dict(patch),
                "touch_ts": touch_ts,
            }
        )

    async def upsert_candles(self, items, session):
        self.candles.extend(list(items))


class FakeMarketDataClient:
    def __init__(self):
        self.candle_calls = []

    async def get_days_candles_for_2_months(self, instrument_id):
        self.candle_calls.append(instrument_id)
        return SimpleNamespace(instrument_id=instrument_id, candles=[_candle()])

    async def get_futures_response(self, instrument_id):
        return None

    async def get_instrument_type(self, instrument_id):
        return "share"


class FakeStrategyStateService:
    def __init__(self):
        self.calls = 0

    async def refresh_all(self):
        self.calls += 1
        return StrategyStateRefreshResult(
            refreshed_count=1,
            warming_count=0,
            skipped_count=0,
        )


class FakeIndicatorCalculator:
    def __init__(self, candles_resp):
        self.candles_resp = candles_resp

    def build_instrument_update(self):
        return {
            "donchian_long_55": 110.0,
            "donchian_short_55": 90.0,
            "donchian_long_20": 105.0,
            "donchian_short_20": 95.0,
            "atr14": 2.5,
        }


def _instrument(
        instrument_id: str,
        *,
        check: bool,
        last_update,
):
    return SimpleNamespace(
        instrument_id=instrument_id,
        check=check,
        last_update=last_update,
    )


def _candle():
    return SimpleNamespace(
        time=datetime(2026, 7, 20, tzinfo=timezone.utc),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100,
        is_complete=True,
    )


def _install_fake_indicator(monkeypatch):
    import application.market_data_refresh as module

    monkeypatch.setattr(module, "IndicatorCalculator", FakeIndicatorCalculator)


async def test_refresh_updates_stale_instruments_and_strategy_state(monkeypatch):
    _install_fake_indicator(monkeypatch)
    tz = ZoneInfo("Europe/Moscow")
    db = FakeRepository(
        [
            _instrument(
                "STALE",
                check=True,
                last_update=datetime.now(tz) - timedelta(days=1),
            ),
            _instrument("FRESH", check=False, last_update=datetime.now(tz)),
        ]
    )
    market_data = FakeMarketDataClient()
    strategy_state = FakeStrategyStateService()

    result = await MarketDataRefreshService(
        db,
        market_data,
        strategy_state,
        tz=tz,
    ).refresh(update_notify=True)

    assert result.refreshed_instrument_ids == ["STALE"]
    assert result.active_instrument_ids == ["STALE"]
    assert result.strategy_state.refreshed_count == 1
    assert market_data.candle_calls == ["STALE"]
    assert db.patches == [
        {
            "instrument_id": "STALE",
            "patch": {
                "donchian_long_55": 110.0,
                "donchian_short_55": 90.0,
                "donchian_long_20": 105.0,
                "donchian_short_20": 95.0,
                "atr14": 2.5,
                "to_notify": True,
            },
            "touch_ts": True,
        }
    ]
    assert db.candles[0]["instrument_id"] == "STALE"
    assert strategy_state.calls == 1
    assert db.sessions[-1].commits == 1


async def test_refresh_skips_fresh_instruments_but_returns_active_ids(monkeypatch):
    _install_fake_indicator(monkeypatch)
    tz = ZoneInfo("Europe/Moscow")
    db = FakeRepository([
        _instrument("FRESH", check=True, last_update=datetime.now(tz)),
    ])
    market_data = FakeMarketDataClient()
    strategy_state = FakeStrategyStateService()

    result = await MarketDataRefreshService(
        db,
        market_data,
        strategy_state,
        tz=tz,
    ).refresh()

    assert result.refreshed_instrument_ids == []
    assert result.active_instrument_ids == ["FRESH"]
    assert market_data.candle_calls == []
    assert db.patches == []
    assert db.candles == []
    assert strategy_state.calls == 1
    assert db.sessions[-1].commits == 1
