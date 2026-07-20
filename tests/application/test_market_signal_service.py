from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from application.dto import ActiveStrategyBinding
from application.market_signals import MarketSignalService
from domain.strategies import SignalKind
from domain.stream_events import LastPriceEvent

pytestmark = pytest.mark.asyncio


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeRepository:
    def __init__(self):
        self.bindings = []
        self.legacy_row = None
        self.legacy_calls = 0
        self.set_notify_calls = []
        self.strategy_signals = []
        self.sessions = []

    @asynccontextmanager
    async def session_factory(self):
        session = FakeSession()
        self.sessions.append(session)
        yield session

    async def list_active_strategy_bindings_for_instrument(self, instrument_id, session):
        return [
            binding
            for binding in self.bindings
            if binding.instrument_id == instrument_id
        ]

    async def get_instrument_with_positions(self, instrument_id, session):
        self.legacy_calls += 1
        return self.legacy_row

    async def set_notify(self, uid, notify, session):
        self.set_notify_calls.append((uid, notify))

    async def add_strategy_signal(self, item, session):
        self.strategy_signals.append(dict(item))


def _instrument(
        instrument_id: str = "UID1",
        *,
        check: bool = True,
        to_notify: bool = True,
        long55: float | None = None,
        short20: float | None = None,
):
    return SimpleNamespace(
        instrument_id=instrument_id,
        ticker="SBER",
        check=check,
        to_notify=to_notify,
        donchian_long_55=long55,
        donchian_short_55=None,
        donchian_long_20=None,
        donchian_short_20=short20,
        atr14=1.0,
    )


def _binding(instrument, **kwargs):
    return ActiveStrategyBinding(
        binding_id=kwargs.get("binding_id", 7),
        strategy_code=kwargs.get("strategy_code", "donchian_breakout"),
        version=kwargs.get("version", 1),
        instrument_id=instrument.instrument_id,
        account_id=kwargs.get("account_id"),
        mode=kwargs.get("mode", "notify"),
        params=kwargs.get("params", {}),
        instrument=instrument,
        position_direction=kwargs.get("position_direction"),
        state=kwargs.get("state", {}),
        state_timeframe=kwargs.get("state_timeframe"),
        state_status=kwargs.get("state_status"),
    )


def _event(instrument_id: str = "UID1", price: float = 151.0):
    return LastPriceEvent(
        instrument_id=instrument_id,
        price=Decimal(str(price)),
        time=datetime.now(timezone.utc),
    )


async def test_process_last_price_uses_active_strategy_binding_and_persists_signal():
    db = FakeRepository()
    instrument = _instrument(long55=150.0)
    db.bindings = [_binding(instrument)]

    decision = await MarketSignalService(db).process_last_price(_event(price=151.0))

    assert decision is not None
    assert decision.binding.binding_id == 7
    assert decision.signal.kind == SignalKind.BREAKOUT_LONG
    assert db.set_notify_calls == [("UID1", False)]
    assert db.strategy_signals[0]["binding_id"] == 7
    assert db.strategy_signals[0]["instrument_id"] == "UID1"
    assert db.strategy_signals[0]["kind"] == "breakout_long"
    assert db.strategy_signals[0]["price"] == Decimal("151.0")
    assert db.sessions[-1].commits == 1
    assert db.legacy_calls == 0


async def test_process_last_price_uses_strategy_state_from_binding():
    db = FakeRepository()
    instrument = _instrument(long55=None)
    db.bindings = [
        _binding(
            instrument,
            state={"donchian_long_55": 150.0, "donchian_short_55": 90.0},
            state_timeframe="day",
        )
    ]

    decision = await MarketSignalService(db).process_last_price(_event(price=151.0))

    assert decision is not None
    assert decision.signal.kind == SignalKind.BREAKOUT_LONG
    assert db.strategy_signals[0]["kind"] == "breakout_long"
    assert db.legacy_calls == 0


async def test_process_last_price_skips_warming_strategy_state():
    db = FakeRepository()
    instrument = _instrument(long55=150.0)
    db.bindings = [
        _binding(
            instrument,
            state={"donchian_long_55": 150.0},
            state_status="warming",
        )
    ]

    decision = await MarketSignalService(db).process_last_price(_event(price=151.0))

    assert decision is None
    assert db.set_notify_calls == []
    assert db.strategy_signals == []
    assert db.legacy_calls == 0


async def test_process_last_price_falls_back_to_legacy_instrument_without_bindings():
    db = FakeRepository()
    instrument = _instrument(short20=101.0)
    db.legacy_row = (instrument, SimpleNamespace(direction="long"))

    decision = await MarketSignalService(db).process_last_price(_event(price=100.0))

    assert decision is not None
    assert decision.binding is None
    assert decision.signal.kind == SignalKind.STOP_LONG
    assert db.set_notify_calls == [("UID1", False)]
    assert db.strategy_signals == []
    assert db.legacy_calls == 1
    assert db.sessions[-1].commits == 1


async def test_process_last_price_does_not_use_legacy_when_binding_has_no_signal():
    db = FakeRepository()
    instrument = _instrument(long55=150.0)
    db.bindings = [_binding(instrument)]
    db.legacy_row = (_instrument(short20=101.0), SimpleNamespace(direction="long"))

    decision = await MarketSignalService(db).process_last_price(_event(price=100.0))

    assert decision is None
    assert db.legacy_calls == 0
    assert db.set_notify_calls == []
    assert db.strategy_signals == []
    assert db.sessions[-1].commits == 0
