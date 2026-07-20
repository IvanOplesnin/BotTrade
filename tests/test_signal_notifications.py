from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bots.tg_bot.signal_notifications import TelegramSignalNotificationHandler
from domain.stream_events import StrategySignalCreatedEvent
from tests.test_market_data_handler.fakes import (
    FakeBot,
    FakeNameService,
    FakePortfolioService,
    FakeRepository,
    FakeTClient,
)
from tests.test_market_data_handler.factories import quotation

pytestmark = pytest.mark.asyncio


async def test_telegram_signal_notification_handler_sends_signal_text(monkeypatch):
    import bots.tg_bot.signal_notifications as module

    async def _stub_long(indicators, last_price, name_service):
        return f"[STOP LONG] {indicators.instrument_id} @ {last_price}"

    monkeypatch.setattr(module, "text_stop_long_position", _stub_long)

    bot = FakeBot()
    handler = TelegramSignalNotificationHandler(
        bot,
        chat_id=123456,
        db=FakeRepository(),
        name_service=FakeNameService(),
        tclient=FakeTClient(quotation),
        portfolio_svc=FakePortfolioService(),
    )
    event = StrategySignalCreatedEvent(
        instrument_id="UID1",
        ticker="SBER",
        instrument_type="share",
        position_direction="long",
        last_price=Decimal("100.0"),
        signal_kind="stop_long",
        signal_side=None,
        signal_boundary=Decimal("99.0"),
        strategy_code="donchian_breakout",
        strategy_version=1,
        indicators={"donchian_short_20": 99.0},
        event_time=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )

    await handler.execute(event)

    assert bot.sent[0]["chat_id"] == 123456
    assert bot.sent[0]["text"] == "[STOP LONG] UID1 @ 100.0"
