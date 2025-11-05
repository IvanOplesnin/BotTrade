import asyncio
import types
import pytest
from types import SimpleNamespace

# Важный момент: pytest-asyncio >=0.21 по умолчанию использует новый event_loop_scope
# Я принудительно делаю session-скоуп, чтобы не плодить циклы
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def monkey_direction(monkeypatch):
    """
    Подменяем Direction в модуле твоего хэндлера, чтобы не тянуть твои внутренние enum-ы.
    """
    from enum import Enum

    class Direction(Enum):
        LONG = "long"
        SHORT = "short"

    import importlib

    # Замените путь на реальный модуль, где лежит MarketDataHandler
    # Например: from mypkg.market.handler import MarketDataHandler
    # Везде ниже этот модуль будет называться handler_mod
    handler_mod = importlib.import_module("core.schemas.market_proc")  # <-- ПОПРАВЬ
    monkeypatch.setattr(handler_mod, "Direction", Direction)
    return Direction


@pytest.fixture
def patch_text_generators(monkeypatch):
    """
    Подменяем async-функции генерации текста, чтобы не зависеть от их внутренней логики.
    """
    async def _stub_long(indicators, last_price, name_service):
        return f"[STOP LONG] {indicators.instrument_id} @ {last_price}"

    async def _stub_short(indicators, last_price, name_service):
        return f"[STOP SHORT] {indicators.instrument_id} @ {last_price}"

    async def _stub_breakout(indicators, side, last_price, name_service, price_point_value):
        return f"[BREAKOUT {side.upper()}] {indicators.instrument_id} @ {last_price} (ppv={price_point_value})"

    import importlib
    handler_mod = importlib.import_module("core.schemas.market_proc")  # <-- ПОПРАВЬ

    monkeypatch.setattr(handler_mod, "text_stop_long_position", _stub_long, raising=True)
    monkeypatch.setattr(handler_mod, "text_stop_short_position", _stub_short, raising=True)
    monkeypatch.setattr(handler_mod, "text_favorites_breakout", _stub_breakout, raising=True)


# @pytest.fixture
# def patched_logger(monkeypatch):
#     """Чтобы логи не шумели и не мешали проверкам."""
#     import importlib
#     handler_mod = importlib.import_module("core.schemas.market_proc")  # <-- ПОПРАВЬ
#     class _DummyLogger:
#         def debug(self, *a, **k): pass
#         def info(self, *a, **k): pass
#         def warning(self, *a, **k): pass
#         def error(self, *a, **k): pass
#
#     monkeypatch.setattr(handler_mod, "getLogger", lambda name: _DummyLogger())
