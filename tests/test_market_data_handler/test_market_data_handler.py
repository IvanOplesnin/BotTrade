import pytest
import importlib
from types import SimpleNamespace

from tests.test_market_data_handler.fakes import FakeBot, FakeRepository, FakeNameService, \
    FakeTClient, FakeRedis, FakePortfolioService
from tests.test_market_data_handler.factories import quotation, last_price_event

pytestmark = pytest.mark.asyncio


def _mk_indicators(
        instrument_id: str,
        *,
        check: bool = True,
        to_notify: bool = True,
        dsh20: float = None,
        dlg20: float = None,
        dlg55: float = None,
        dsh55: float = None,
):
    """
    Минимальная «структура» индикаторов, удовлетворяющая обращениям из кода.
    """
    return SimpleNamespace(
        instrument_id=instrument_id,
        check=check,
        to_notify=to_notify,
        donchian_short_20=dsh20,
        donchian_long_20=dlg20,
        donchian_long_55=dlg55,
        donchian_short_55=dsh55,
    )


def _mk_position(direction):
    return SimpleNamespace(direction=direction)


def _mk_handler(monkeypatch, monkey_direction):
    """
    Создаём MarketDataHandler, подложив фейковые зависимости.
    """
    handler_mod = importlib.import_module("core.schemas.market_proc")
    bot = FakeBot()
    db = FakeRepository()
    ns = FakeNameService()
    tclient = FakeTClient(quotation)
    redis = FakeRedis()
    portfolio_svc = FakePortfolioService()
    handler = handler_mod.MarketDataHandler(
        bot=bot,
        chat_id=123456,
        db=db,
        name_service=ns,
        portfolio_svc=portfolio_svc,
        tclient=tclient,
        redis=redis,
        acc_id=None,
    )
    return handler, bot, db, ns, tclient, handler_mod


async def test_no_instrument_in_db(monkeypatch, monkey_direction, patch_text_generators):
    handler, bot, db, ns, tclient, handler_mod = _mk_handler(monkeypatch, monkey_direction)

    async def _get(uid, s):
        return None

    db.set_get_row_callable(_get)

    await handler.execute(last_price_event("UID1", 100.0))

    assert bot.sent == []
    assert db.set_notify_calls == []


async def test_skip_when_check_false(monkeypatch, monkey_direction, patch_text_generators):
    Direction = monkey_direction
    handler, bot, db, ns, tclient, handler_mod = _mk_handler(monkeypatch, Direction)

    async def _get(uid, s):
        indicators = _mk_indicators(uid, check=False, to_notify=True)
        position = _mk_position(Direction.LONG)
        return indicators, position

    db.set_get_row_callable(_get)

    await handler.execute(last_price_event("UID2", 100.0))

    assert bot.sent == []
    assert db.set_notify_calls == []


async def test_stop_long_when_price_breaks_short20(monkeypatch, monkey_direction,
                                                   patch_text_generators):
    Direction = monkey_direction
    handler, bot, db, ns, tclient, handler_mod = _mk_handler(monkeypatch, Direction)

    async def _get(uid, s):
        indicators = _mk_indicators(uid, check=True, to_notify=True, dsh20=101.0)
        position = _mk_position(Direction.LONG.value)
        return indicators, position

    db.set_get_row_callable(_get)

    # Цена <= donchian_short_20 (101.0) => стоп длинной позиции
    await handler.execute(last_price_event("UID3", 100.0))

    assert len(bot.sent) == 1
    assert "[STOP LONG]" in bot.sent[0]["text"]
    # set_notify(False) + commit должны быть вызваны
    assert db.set_notify_calls == [("UID3", False)]


async def test_stop_short_when_price_breaks_long20(monkeypatch, monkey_direction,
                                                   patch_text_generators):
    Direction = monkey_direction
    handler, bot, db, ns, tclient, handler_mod = _mk_handler(monkeypatch, Direction)

    async def _get(uid, s):
        indicators = _mk_indicators(uid, check=True, to_notify=True, dlg20=99.0)
        position = _mk_position(Direction.SHORT.value)
        return indicators, position

    db.set_get_row_callable(_get)

    # Цена >= donchian_long_20 (99.0) => стоп короткой позиции
    await handler.execute(last_price_event("UID4", 100.0))

    assert len(bot.sent) == 1
    assert "[STOP SHORT]" in bot.sent[0]["text"]
    assert db.set_notify_calls == [("UID4", False)]


async def test_breakout_long_when_no_position_and_notify(monkeypatch, monkey_direction,
                                                         patch_text_generators):
    Direction = monkey_direction
    handler, bot, db, ns, tclient, handler_mod = _mk_handler(monkeypatch, Direction)

    async def _get(uid, s):
        indicators = _mk_indicators(uid, check=True, to_notify=True, dlg55=150.0)
        position = None  # нет позиции
        return indicators, position

    db.set_get_row_callable(_get)

    # Цена >= donchian_long_55 (150) => сигнал LONG breakout
    await handler.execute(last_price_event("UID5", 150.0))

    assert len(bot.sent) == 1
    assert "[BREAKOUT LONG]" in bot.sent[0]["text"]
    assert db.set_notify_calls == [("UID5", False)]
    # Проверим вызов tclient
    assert tclient.calls == [("get_min_price_increment_amount", "UID5")]


async def test_breakout_short_when_no_position_and_notify(monkeypatch, monkey_direction,
                                                          patch_text_generators):
    Direction = monkey_direction
    handler, bot, db, ns, tclient, handler_mod = _mk_handler(monkeypatch, Direction)

    async def _get(uid, s):
        indicators = _mk_indicators(uid, check=True, to_notify=True, dsh55=50.0, dlg55=150.0)
        position = None
        return indicators, position

    db.set_get_row_callable(_get)

    # Цена <= donchian_short_55 (50) => сигнал SHORT breakout
    await handler.execute(last_price_event("UID6", 49.5))

    assert len(bot.sent) == 1
    assert "[BREAKOUT SHORT]" in bot.sent[0]["text"]
    assert db.set_notify_calls == [("UID6", False)]
    assert tclient.calls == [("get_min_price_increment_amount", "UID6")]
