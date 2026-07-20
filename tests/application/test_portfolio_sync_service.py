from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from application.portfolio_sync import PortfolioSyncService
from domain.stream_events import PortfolioPositionEvent, PortfolioSnapshotEvent

pytestmark = pytest.mark.asyncio


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeRepository:
    def __init__(self, instruments=None):
        self.instruments = {item.instrument_id: item for item in (instruments or [])}
        self.account_positions = {}
        self.upsert_instruments = []
        self.deleted_positions = []
        self.delete_all_positions = []
        self.positions = []
        self.strategy_bindings = []
        self.strategy_binding_enabled_updates = []
        self.candles = []
        self.sessions = []

    @asynccontextmanager
    async def session_factory(self):
        session = FakeSession()
        self.sessions.append(session)
        yield session

    async def list_positions_for_account(self, account_id, session):
        return self.account_positions.get(account_id, [])

    async def list_instruments_by_ids(self, ids, session):
        return [self.instruments[item] for item in ids if item in self.instruments]

    async def upsert_instruments_bulk_data(self, items, session, update_ts=True):
        self.upsert_instruments.extend(list(items))

    async def delete_all_positions_for_account(self, account_id, session):
        self.delete_all_positions.append(account_id)

    async def delete_positions_bulk(self, account_id, instrument_ids, session):
        self.deleted_positions.append(
            {
                "account_id": account_id,
                "instrument_ids": list(instrument_ids),
            }
        )

    async def set_position_bulk(self, positions, session):
        self.positions.extend(list(positions))

    async def upsert_strategy_bindings(self, items, session):
        self.strategy_bindings.extend(list(items))

    async def set_strategy_bindings_enabled(
            self,
            *,
            instrument_ids,
            enabled,
            session,
            account_id=None,
    ):
        self.strategy_binding_enabled_updates.append(
            {
                "instrument_ids": list(instrument_ids),
                "enabled": enabled,
                "account_id": account_id,
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
        self.calls = []

    async def refresh_instruments(self, instrument_ids):
        self.calls.append(list(instrument_ids))


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


def _position_row(instrument_id: str):
    return SimpleNamespace(instrument_id=instrument_id), SimpleNamespace(instrument_id=instrument_id)


def _instrument(instrument_id: str, *, last_update=None):
    return SimpleNamespace(
        instrument_id=instrument_id,
        last_update=last_update or datetime.now(timezone.utc),
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


def _snapshot(account_id: str, *positions: PortfolioPositionEvent):
    return PortfolioSnapshotEvent(account_id=account_id, positions=tuple(positions))


def _portfolio_position(instrument_id: str, *, ticker="SBER", quantity=1):
    return PortfolioPositionEvent(
        instrument_id=instrument_id,
        ticker=ticker,
        quantity_lots=quantity,
    )


def _install_fake_indicator(monkeypatch):
    import application.portfolio_sync as module

    monkeypatch.setattr(module, "IndicatorCalculator", FakeIndicatorCalculator)


async def test_sync_adds_and_deletes_positions_with_strategy_bindings(monkeypatch):
    _install_fake_indicator(monkeypatch)
    db = FakeRepository()
    db.account_positions["ACC1"] = [_position_row("OLD")]
    market_data = FakeMarketDataClient()

    result = await PortfolioSyncService(db, market_data).sync(
        _snapshot("ACC1", _portfolio_position("UID1", ticker="AAA", quantity=3))
    )

    assert [position.instrument_id for position in result.added_positions] == ["UID1"]
    assert result.deleted_instrument_ids == ["OLD"]
    assert db.deleted_positions == [{"account_id": "ACC1", "instrument_ids": ["OLD"]}]
    assert db.positions == [
        {"account_id": "ACC1", "instrument_id": "UID1", "direction": "long"}
    ]
    assert db.upsert_instruments[0]["instrument_id"] == "UID1"
    assert db.upsert_instruments[0]["ticker"] == "AAA"
    assert db.strategy_bindings[0]["instrument_id"] == "UID1"
    assert db.strategy_bindings[0]["account_id"] == "ACC1"
    assert [item["instrument_id"] for item in db.candles] == ["UID1"]
    assert db.candles[0]["timeframe"] == "day"
    assert db.strategy_binding_enabled_updates == [
        {
            "instrument_ids": ["OLD"],
            "enabled": False,
            "account_id": "ACC1",
        }
    ]
    assert market_data.candle_calls == ["UID1"]
    assert db.sessions[-1].commits == 1


async def test_sync_empty_portfolio_removes_positions_without_notification_payload():
    db = FakeRepository()
    db.account_positions["ACC1"] = [_position_row("UID1"), _position_row("UID2")]
    market_data = FakeMarketDataClient()

    result = await PortfolioSyncService(db, market_data).sync(_snapshot("ACC1"))

    assert result.added_positions == []
    assert result.deleted_instrument_ids == []
    assert db.delete_all_positions == ["ACC1"]
    assert db.strategy_binding_enabled_updates == [
        {
            "instrument_ids": ["UID1", "UID2"],
            "enabled": False,
            "account_id": "ACC1",
        }
    ]
    assert db.positions == []
    assert db.strategy_bindings == []
    assert market_data.candle_calls == []
    assert db.sessions[-1].commits == 1


async def test_sync_refreshes_existing_position_direction_without_candle_reload():
    db = FakeRepository([_instrument("UID1")])
    db.account_positions["ACC1"] = [_position_row("UID1")]
    market_data = FakeMarketDataClient()

    result = await PortfolioSyncService(db, market_data).sync(
        _snapshot("ACC1", _portfolio_position("UID1", quantity=-2))
    )

    assert result.added_positions == []
    assert result.deleted_instrument_ids == []
    assert db.positions == [
        {"account_id": "ACC1", "instrument_id": "UID1", "direction": "short"}
    ]
    assert db.upsert_instruments == []
    assert db.strategy_bindings[0]["instrument_id"] == "UID1"
    assert market_data.candle_calls == []


async def test_sync_refreshes_strategy_state_when_service_is_injected(monkeypatch):
    _install_fake_indicator(monkeypatch)
    db = FakeRepository()
    market_data = FakeMarketDataClient()
    strategy_state = FakeStrategyStateService()

    await PortfolioSyncService(
        db,
        market_data,
        strategy_state_svc=strategy_state,
    ).sync(
        _snapshot("ACC1", _portfolio_position("UID1", ticker="AAA"))
    )

    assert strategy_state.calls == [["UID1"]]
