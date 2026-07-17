from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from bots.tg_bot.handlers.router import remove_account_id

pytestmark = pytest.mark.asyncio


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeRepository:
    def __init__(self):
        self.deleted_accounts = []
        self.checked = []
        self.sessions = []

    @asynccontextmanager
    async def session_factory(self):
        session = FakeSession()
        self.sessions.append(session)
        yield session

    async def list_positions_for_account(self, account_id, session):
        return [
            (SimpleNamespace(instrument_id="UID1"), SimpleNamespace()),
            (SimpleNamespace(instrument_id="UID2"), SimpleNamespace()),
        ]

    async def delete_account(self, account_id, session):
        self.deleted_accounts.append(account_id)

    async def list_position_by_id(self, instrument_id, session):
        return []

    async def set_checked_bulk(self, ids, session, check=True):
        self.checked.append((list(ids), check))

    async def list_accounts(self, session):
        return []


class FakeTClient:
    def __init__(self):
        self.market_stream_task = object()
        self.portfolio_stream_task = object()
        self.unsubscribed = []
        self.recreated_accounts = None

    async def get_portfolio(self, account_id):
        raise AssertionError("remove_account_id must not call get_portfolio")

    def unsubscribe_to_instrument_last_price(self, *instrument_ids):
        self.unsubscribed.append(instrument_ids)

    async def recreate_portfolio_stream(self, accounts):
        self.recreated_accounts = accounts


class FakeNameService:
    async def get_name(self, instrument_id):
        return f"name-{instrument_id}"


class FakeState:
    def __init__(self):
        self.clear_calls = 0

    async def clear(self):
        self.clear_calls += 1


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append({"chat_id": chat_id, "text": text})


class FakeMessage:
    def __init__(self):
        self.chat = SimpleNamespace(id=123)
        self.answers = []
        self.reply_markup_edits = []

    async def answer(self, text):
        self.answers.append(text)

    async def edit_reply_markup(self, reply_markup=None):
        self.reply_markup_edits.append(reply_markup)


async def test_remove_account_uses_local_positions_when_tbank_account_is_missing():
    bot = FakeBot()
    call = SimpleNamespace(data="ACC1", message=FakeMessage(), bot=bot)
    state = FakeState()
    db = FakeRepository()
    tclient = FakeTClient()

    await remove_account_id(
        call=call,
        state=state,
        tclient=tclient,
        db=db,
        name_service=FakeNameService(),
    )

    assert db.deleted_accounts == ["ACC1"]
    assert db.checked == [(["UID1", "UID2"], False)]
    assert db.sessions[0].commits == 1
    assert call.message.reply_markup_edits == [None]
    assert tclient.unsubscribed == [("UID1", "UID2")]
    assert tclient.recreated_accounts == []
    assert state.clear_calls == 1
    assert bot.sent == [
        {
            "chat_id": 123,
            "text": (
                "Аккаунт успешно удалён. Удалены подписки на последние цены:\n"
                "❌ <b>name-UID1</b>\n"
                "❌ <b>name-UID2</b>"
            ),
        }
    ]
