from __future__ import annotations

from types import SimpleNamespace

import pytest

from bots.tg_bot.handlers import add_favorite_instruments as handler_mod

pytestmark = pytest.mark.asyncio


class FakeMessage:
    def __init__(self):
        self.chat = SimpleNamespace(id=123)
        self.answers = []
        self.reply_markup_edits = []

    async def answer(self, text):
        self.answers.append(text)

    async def edit_reply_markup(self, reply_markup=None):
        self.reply_markup_edits.append(reply_markup)


class FakeCall:
    def __init__(self):
        self.message = FakeMessage()


class FakeState:
    def __init__(self):
        self.clear_calls = 0

    async def clear(self):
        self.clear_calls += 1


class FakeTClient:
    def __init__(self):
        self.market_stream_task = object()
        self.subscribed = []

    def subscribe_to_instrument_last_price(self, *instrument_ids):
        self.subscribed.append(instrument_ids)


class FakeNameService:
    async def get_name(self, instrument_id):
        return f"name-{instrument_id}"


class FailingNameService:
    async def get_name(self, instrument_id):
        raise RuntimeError("name service down")


def _favorite(uid: str, ticker: str):
    return SimpleNamespace(instrument_uid=uid, ticker=ticker)


async def test_add_favorites_instruments_sends_progress_and_result(monkeypatch):
    created_candidates = []
    scheduled_candidates = []

    class FakeWatchlistService:
        def __init__(self, db, tclient):
            pass

        async def add_favorites_quick(self, instruments):
            created_candidates.extend(instruments)
            return SimpleNamespace(
                instrument_ids=["UID1"],
                message_instruments=[
                    SimpleNamespace(instrument_id="UID1", ticker="SBER")
                ],
            )

    monkeypatch.setattr(handler_mod, "WatchlistService", FakeWatchlistService)
    monkeypatch.setattr(
        handler_mod,
        "_schedule_favorites_refresh",
        lambda db, tclient, instruments: scheduled_candidates.extend(instruments),
    )

    call = FakeCall()
    state = FakeState()
    tclient = FakeTClient()

    await handler_mod.add_favorites_instruments(
        call=call,
        db=object(),
        instruments=[_favorite("UID1", "SBER")],
        state=state,
        tclient=tclient,
        name_service=FakeNameService(),
    )

    assert [candidate.instrument_id for candidate in created_candidates] == ["UID1"]
    assert [candidate.instrument_id for candidate in scheduled_candidates] == ["UID1"]
    assert call.message.reply_markup_edits == [None]
    assert call.message.answers[0] == "Добавляю инструменты в отслеживание..."
    assert call.message.answers[1] == "Добавлены инструменты:\n✅ <b>name-UID1</b> — SBER"
    assert tclient.subscribed == [("UID1",)]
    assert state.clear_calls == 1


async def test_add_favorites_instruments_uses_fallback_message_when_name_service_fails(
        monkeypatch,
):
    class FakeWatchlistService:
        def __init__(self, db, tclient):
            pass

        async def add_favorites_quick(self, instruments):
            return SimpleNamespace(
                instrument_ids=["UID1"],
                message_instruments=[
                    SimpleNamespace(instrument_id="UID1", ticker="SBER")
                ],
            )

    monkeypatch.setattr(handler_mod, "WatchlistService", FakeWatchlistService)
    monkeypatch.setattr(handler_mod, "_schedule_favorites_refresh", lambda *args: None)

    call = FakeCall()
    state = FakeState()

    await handler_mod.add_favorites_instruments(
        call=call,
        db=object(),
        instruments=[_favorite("UID1", "SBER")],
        state=state,
        tclient=FakeTClient(),
        name_service=FailingNameService(),
    )

    assert call.message.answers[1] == "Добавлены инструменты:\n✅ <b>SBER</b> — UID1"
    assert state.clear_calls == 1


async def test_add_favorites_instruments_reports_use_case_error(monkeypatch):
    class FailingWatchlistService:
        def __init__(self, db, tclient):
            pass

        async def add_favorites_quick(self, instruments):
            raise RuntimeError("boom")

    monkeypatch.setattr(handler_mod, "WatchlistService", FailingWatchlistService)

    call = FakeCall()
    state = FakeState()
    tclient = FakeTClient()

    await handler_mod.add_favorites_instruments(
        call=call,
        db=object(),
        instruments=[_favorite("UID1", "SBER")],
        state=state,
        tclient=tclient,
        name_service=FakeNameService(),
    )

    assert call.message.reply_markup_edits == [None]
    assert call.message.answers[0] == "Добавляю инструменты в отслеживание..."
    assert call.message.answers[1] == (
        "Не удалось добавить инструменты в отслеживание. Ошибка: boom"
    )
    assert tclient.subscribed == []
    assert state.clear_calls == 1
