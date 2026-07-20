from contextlib import asynccontextmanager
from types import SimpleNamespace


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        payload = {"chat_id": chat_id, "text": text}
        if kwargs:
            payload["kwargs"] = kwargs
        self.sent.append(payload)


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeRepository:
    """
    - session_factory: асинхронный контекст-менеджер, возвращает FakeSession
    - get_instrument_with_positions: подменяем в тесте через лямбду/функцию
    - set_notify: записываем вызовы для assert
    """

    def __init__(self):
        self._get_row = None
        self.set_notify_calls = []
        self.strategy_bindings = []
        self.strategy_signals = []

    def set_get_row_callable(self, fn):
        self._get_row = fn

    async def get_instrument_with_positions(self, uid, session):
        if self._get_row is None:
            return None
        return await self._get_row(uid, session)

    async def list_active_strategy_bindings_for_instrument(self, instrument_id, session):
        return [
            binding
            for binding in self.strategy_bindings
            if binding.instrument_id == instrument_id
        ]

    @asynccontextmanager
    async def session_factory(self):
        sess = FakeSession()
        try:
            yield sess
        finally:
            pass

    async def set_notify(self, instrument_id, notify, session):
        self.set_notify_calls.append((instrument_id, notify))

    async def add_strategy_signal(self, item, session):
        self.strategy_signals.append(dict(item))

    async def list_accounts(self, session):
        return []


class FakeNameService:
    pass


class FakeTClient:
    def __init__(self, quotation_factory):
        self._quotation_factory = quotation_factory
        self.calls = []

    async def get_min_price_increment_amount(self, uid: str):
        self.calls.append(("get_min_price_increment_amount", uid))
        return SimpleNamespace(
            min_price_increment_amount=self._quotation_factory(1, 0),
            min_price_increment=self._quotation_factory(1, 0),
        )


class FakeRedis:
    def __init__(self):
        self.last_prices = []

    async def set_last_price_if_newer(self, instrument_uid: str, price_str: str, ts_ms: int):
        self.last_prices.append((instrument_uid, price_str, ts_ms))
        return True


class FakeMessageBus:
    def __init__(self):
        self.published = []

    def subscribe(self, topic, handler):
        pass

    async def publish(self, topic, data):
        self.published.append((topic, data))

    async def start(self):
        pass

    async def stop(self):
        pass


class FakePortfolioService:
    async def get_portfolio(self, acc_id: str, name: str):
        return None
