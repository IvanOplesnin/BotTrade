from contextlib import asynccontextmanager


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append({"chat_id": chat_id, "text": text})


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

    def set_get_row_callable(self, fn):
        self._get_row = fn

    async def get_instrument_with_positions(self, uid, session):
        if self._get_row is None:
            return None
        return await self._get_row(uid, session)

    @asynccontextmanager
    async def session_factory(self):
        sess = FakeSession()
        try:
            yield sess
        finally:
            pass

    async def set_notify(self, instrument_id, notify, session):
        self.set_notify_calls.append((instrument_id, notify))


class FakeNameService:
    pass


class FakeTClient:
    def __init__(self, quotation_factory):
        self._quotation_factory = quotation_factory
        self.calls = []

    async def get_min_price_increment_amount(self, uid: str):
        self.calls.append(("get_min_price_increment_amount", uid))
        # Возвращаем Quotation(1, 0) — 1.0
        return self._quotation_factory(1, 0)
