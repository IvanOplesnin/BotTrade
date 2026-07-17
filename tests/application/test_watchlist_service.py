from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from application.dto import InstrumentCandidate, PositionCandidate
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

    async def get_days_candles_for_2_months(self, instrument_id):
        self.candle_calls.append(instrument_id)
        return SimpleNamespace(instrument_id=instrument_id)

    async def get_futures_response(self, instrument_id):
        self.future_calls.append(instrument_id)
        return SimpleNamespace(
            instrument=SimpleNamespace(
                expiration_date=datetime(2026, 8, 1, tzinfo=timezone.utc)
            )
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
    assert [item["instrument_id"] for item in db.upsert_instruments] == ["UID1"]
    assert db.checked == [(["UID2"], True)]
    assert db.positions == [
        {"account_id": "ACC1", "instrument_id": "UID1", "direction": "long"},
        {"account_id": "ACC1", "instrument_id": "UID2", "direction": "short"},
    ]
    assert market_data.candle_calls == ["UID1"]
    assert market_data.future_calls == ["UID1"]
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
    assert db.upsert_instruments == []
    assert db.checked == [(["UID9"], True)]
    assert market_data.candle_calls == []
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
    assert db.upsert_instruments[0]["last_update"] is None
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


async def test_add_favorites_skips_future_lookup_for_new_non_future(monkeypatch):
    _install_fake_indicator(monkeypatch)
    db = FakeRepository()
    market_data = FakeMarketDataClient()

    await WatchlistService(db, market_data).add_favorites(
        [InstrumentCandidate("UID8", "SBER", instrument_type="share")]
    )

    assert market_data.candle_calls == ["UID8"]
    assert market_data.future_calls == []


async def test_add_favorites_loads_expiration_for_new_future(monkeypatch):
    _install_fake_indicator(monkeypatch)
    db = FakeRepository()
    market_data = FakeMarketDataClient()

    await WatchlistService(db, market_data).add_favorites(
        [InstrumentCandidate("FUT1", "FUT", instrument_type="future")]
    )

    assert market_data.candle_calls == ["FUT1"]
    assert market_data.future_calls == ["FUT1"]


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
