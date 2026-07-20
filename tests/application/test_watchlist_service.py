from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from application.dto import InstrumentCandidate, PositionCandidate, StrategyBindingConfig
from application.watchlist import WatchlistService

pytestmark = pytest.mark.asyncio


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeRepository:
    def __init__(self, instruments=None):
        self.instruments = {i.instrument_id: i for i in (instruments or [])}
        self.upsert_accounts = []
        self.upsert_instruments = []
        self.positions = []
        self.account_positions = {}
        self.remaining_positions_by_id = {}
        self.deleted_accounts = []
        self.checked = []
        self.strategy_bindings = []
        self.strategy_binding_enabled_updates = []
        self.candles = []
        self.sessions = []

    @asynccontextmanager
    async def session_factory(self):
        session = FakeSession()
        self.sessions.append(session)
        yield session

    async def list_instruments_by_ids(self, ids, session):
        return [self.instruments[i] for i in ids if i in self.instruments]

    async def upsert_account(self, *, account_id, name, check, session):
        self.upsert_accounts.append(
            {"account_id": account_id, "name": name, "check": check}
        )

    async def upsert_instruments_bulk_data(self, items, session, update_ts=True):
        self.upsert_instruments.extend(items)

    async def set_position_bulk(self, positions, session):
        self.positions.extend(positions)

    async def set_checked_bulk(self, ids, session, check=True):
        self.checked.append((list(ids), check))

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

    async def list_positions_for_account(self, account_id, session):
        return self.account_positions.get(account_id, [])

    async def list_position_by_id(self, instrument_id, session):
        return self.remaining_positions_by_id.get(instrument_id, [])

    async def delete_account(self, account_id, session):
        self.deleted_accounts.append(account_id)


class FakeMarketDataClient:
    def __init__(self):
        self.candle_calls = []
        self.future_calls = []
        self.info_calls = []

    async def get_days_candles_for_2_months(self, instrument_id):
        self.candle_calls.append(instrument_id)
        return SimpleNamespace(instrument_id=instrument_id, candles=[_candle()])

    async def get_futures_response(self, instrument_id):
        self.future_calls.append(instrument_id)
        if not instrument_id.startswith("FUT"):
            return None
        return SimpleNamespace(
            instrument=SimpleNamespace(
                expiration_date=datetime(2026, 8, 1, tzinfo=timezone.utc)
            )
        )

    async def get_instrument_type(self, instrument_id):
        self.info_calls.append(instrument_id)
        return "share"


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


def _existing(instrument_id, *, last_update=None, ticker="OLD", to_notify=False):
    return SimpleNamespace(
        instrument_id=instrument_id,
        ticker=ticker,
        check=False,
        to_notify=to_notify,
        donchian_long_55=1.0,
        donchian_short_55=2.0,
        donchian_long_20=3.0,
        donchian_short_20=4.0,
        atr14=5.0,
        last_update=last_update or datetime.now(timezone.utc),
        expiration_date=None,
        type=None,
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
    import application.watchlist as module

    monkeypatch.setattr(module, "IndicatorCalculator", FakeIndicatorCalculator)


async def test_add_account_updates_new_instruments_and_links_positions(monkeypatch):
    _install_fake_indicator(monkeypatch)
    existing_today = _existing("UID2", last_update=datetime.now(timezone.utc))
    db = FakeRepository([existing_today])
    market_data = FakeMarketDataClient()

    result = await WatchlistService(db, market_data).add_account(
        account_id="ACC1",
        account_name="Main",
        positions=[
            PositionCandidate("UID1", "AAA", "long"),
            PositionCandidate("UID2", "BBB", "short"),
        ],
    )

    assert result.instrument_ids == ["UID1", "UID2"]
    assert db.upsert_accounts == [{"account_id": "ACC1", "name": "Main", "check": True}]
    assert [item["instrument_id"] for item in db.upsert_instruments] == ["UID1", "UID2"]
    assert db.upsert_instruments[0]["type"] == "share"
    assert db.upsert_instruments[1]["type"] == "share"
    assert db.checked == []
    assert db.positions == [
        {"account_id": "ACC1", "instrument_id": "UID1", "direction": "long"},
        {"account_id": "ACC1", "instrument_id": "UID2", "direction": "short"},
    ]
    assert db.strategy_bindings == [
        {
            "strategy_code": "donchian_breakout",
            "version": 1,
            "instrument_id": "UID1",
            "account_id": "ACC1",
            "enabled": True,
            "mode": "notify",
            "params": {
                "entry_period": 55,
                "exit_period": 20,
                "atr_period": 14,
                "timeframe": "day",
            },
        },
        {
            "strategy_code": "donchian_breakout",
            "version": 1,
            "instrument_id": "UID2",
            "account_id": "ACC1",
            "enabled": True,
            "mode": "notify",
            "params": {
                "entry_period": 55,
                "exit_period": 20,
                "atr_period": 14,
                "timeframe": "day",
            },
        },
    ]
    assert [item["instrument_id"] for item in db.candles] == ["UID1"]
    assert db.candles[0]["timeframe"] == "day"
    assert market_data.candle_calls == ["UID1"]
    assert market_data.future_calls == ["UID1"]
    assert market_data.info_calls == ["UID1", "UID2"]
    assert db.sessions[-1].commits == 1


async def test_add_favorites_marks_fresh_existing_instrument_without_recalculating(monkeypatch):
    _install_fake_indicator(monkeypatch)
    existing_today = _existing("UID9", last_update=datetime.now(timezone.utc), ticker="OLD")
    db = FakeRepository([existing_today])
    market_data = FakeMarketDataClient()

    result = await WatchlistService(db, market_data).add_favorites(
        [InstrumentCandidate("UID9", "NEW")]
    )

    assert result.instrument_ids == ["UID9"]
    assert [instrument.instrument_id for instrument in result.message_instruments] == ["UID9"]
    assert [item["instrument_id"] for item in db.upsert_instruments] == ["UID9"]
    assert db.upsert_instruments[0]["type"] == "share"
    assert db.checked == []
    assert db.strategy_bindings[0]["instrument_id"] == "UID9"
    assert db.strategy_bindings[0]["account_id"] is None
    assert db.strategy_bindings[0]["strategy_code"] == "donchian_breakout"
    assert market_data.candle_calls == []
    assert market_data.info_calls == ["UID9"]
    assert db.sessions[-1].commits == 1


async def test_add_favorites_quick_persists_without_loading_market_data(monkeypatch):
    _install_fake_indicator(monkeypatch)
    db = FakeRepository()
    market_data = FakeMarketDataClient()

    result = await WatchlistService(db, market_data).add_favorites_quick(
        [InstrumentCandidate("UID1", "SBER", instrument_type="share")]
    )

    assert result.instrument_ids == ["UID1"]
    assert [instrument.instrument_id for instrument in result.message_instruments] == ["UID1"]
    assert [item["instrument_id"] for item in db.upsert_instruments] == ["UID1"]
    assert db.upsert_instruments[0]["type"] == "share"
    assert result.message_instruments[0].instrument_type == "share"
    assert db.upsert_instruments[0]["last_update"] is None
    assert db.strategy_bindings[0]["instrument_id"] == "UID1"
    assert db.strategy_bindings[0]["account_id"] is None
    assert market_data.candle_calls == []
    assert market_data.future_calls == []
    assert db.sessions[-1].commits == 1


async def test_add_favorites_recalculates_stale_existing_instrument(monkeypatch):
    _install_fake_indicator(monkeypatch)
    stale = _existing(
        "UID7",
        last_update=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db = FakeRepository([stale])
    market_data = FakeMarketDataClient()

    result = await WatchlistService(db, market_data).add_favorites(
        [InstrumentCandidate("UID7", "STALE")]
    )

    assert result.instrument_ids == ["UID7"]
    assert [item["instrument_id"] for item in db.upsert_instruments] == ["UID7"]
    assert db.checked == []
    assert market_data.candle_calls == ["UID7"]
    assert market_data.future_calls == []
    assert market_data.info_calls == ["UID7"]


async def test_add_favorites_skips_future_lookup_for_new_non_future(monkeypatch):
    _install_fake_indicator(monkeypatch)
    db = FakeRepository()
    market_data = FakeMarketDataClient()

    await WatchlistService(db, market_data).add_favorites(
        [InstrumentCandidate("UID8", "SBER", instrument_type="share")]
    )

    assert market_data.candle_calls == ["UID8"]
    assert market_data.future_calls == []
    assert market_data.info_calls == []


async def test_add_favorites_loads_expiration_for_new_future(monkeypatch):
    _install_fake_indicator(monkeypatch)
    db = FakeRepository()
    market_data = FakeMarketDataClient()

    await WatchlistService(db, market_data).add_favorites(
        [InstrumentCandidate("FUT1", "FUT", instrument_type="future")]
    )

    assert market_data.candle_calls == ["FUT1"]
    assert market_data.future_calls == ["FUT1"]
    assert market_data.info_calls == []


async def test_add_favorites_uses_configured_strategy_bindings(monkeypatch):
    _install_fake_indicator(monkeypatch)
    db = FakeRepository()
    market_data = FakeMarketDataClient()

    await WatchlistService(
        db,
        market_data,
        default_strategy_configs=[
            StrategyBindingConfig(
                code="ma_cross",
                version=2,
                mode="sandbox_order",
                params={"fast": 20, "slow": 50},
            )
        ],
    ).add_favorites_quick(
        [InstrumentCandidate("UID1", "SBER", instrument_type="share")]
    )

    assert db.strategy_bindings == [
        {
            "strategy_code": "ma_cross",
            "version": 2,
            "instrument_id": "UID1",
            "account_id": None,
            "enabled": True,
            "mode": "sandbox_order",
            "params": {"fast": 20, "slow": 50},
        }
    ]


async def test_add_favorites_allows_empty_strategy_config():
    db = FakeRepository()
    market_data = FakeMarketDataClient()

    await WatchlistService(
        db,
        market_data,
        default_strategy_configs=[],
    ).add_favorites_quick(
        [InstrumentCandidate("UID1", "SBER", instrument_type="share")]
    )

    assert db.strategy_bindings == []


async def test_remove_account_unchecks_only_detached_instruments():
    db = FakeRepository()
    db.account_positions = {
        "ACC1": [
            (SimpleNamespace(instrument_id="UID1"), SimpleNamespace()),
            (SimpleNamespace(instrument_id="UID2"), SimpleNamespace()),
        ]
    }
    db.remaining_positions_by_id = {
        "UID1": [],
        "UID2": [(SimpleNamespace(account_id="ACC2"), SimpleNamespace())],
    }
    market_data = FakeMarketDataClient()

    result = await WatchlistService(db, market_data).remove_account("ACC1")

    assert result.instrument_ids == ["UID1", "UID2"]
    assert result.detached_instrument_ids == ["UID1"]
    assert db.deleted_accounts == ["ACC1"]
    assert db.checked == [(["UID1"], False)]
    assert db.sessions[-1].commits == 1


async def test_uncheck_instruments_disables_global_strategy_bindings():
    db = FakeRepository()
    market_data = FakeMarketDataClient()

    result = await WatchlistService(db, market_data).uncheck_instruments([
        SimpleNamespace(instrument_id="UID1"),
        SimpleNamespace(instrument_id="UID2"),
    ])

    assert result.instrument_ids == ["UID1", "UID2"]
    assert db.checked == [(["UID1", "UID2"], False)]
    assert db.strategy_binding_enabled_updates == [
        {
            "instrument_ids": ["UID1", "UID2"],
            "enabled": False,
            "account_id": None,
        }
    ]
    assert db.sessions[-1].commits == 1
