import asyncio

from clients.tinkoff.streams import TinkoffStreamManager


class FakeLastPrice:
    def __init__(self):
        self.subscribed = []
        self.unsubscribed = []

    def subscribe(self, instruments):
        self.subscribed.append([instrument.instrument_id for instrument in instruments])

    def unsubscribe(self, instruments):
        self.unsubscribed.append([instrument.instrument_id for instrument in instruments])


class FakeMarketStream:
    def __init__(self):
        self.last_price = FakeLastPrice()
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_subscribe_before_market_stream_is_created_is_recorded_and_applied_later():
    streams = TinkoffStreamManager()

    streams.subscribe_to_instrument_last_price("UID1", "UID2")
    assert streams.subscribes["last_price"] == {"UID1", "UID2"}

    stream = FakeMarketStream()
    streams._stream_market = stream
    streams._apply_last_price_subscriptions()

    assert stream.last_price.subscribed == [["UID1", "UID2"]]


def test_subscribe_with_active_market_stream_sends_request_immediately():
    streams = TinkoffStreamManager()
    stream = FakeMarketStream()
    streams._stream_market = stream

    streams.subscribe_to_instrument_last_price("UID1")

    assert streams.subscribes["last_price"] == {"UID1"}
    assert stream.last_price.subscribed == [["UID1"]]


def test_unsubscribe_is_idempotent_and_sends_request_when_stream_is_active():
    streams = TinkoffStreamManager()
    stream = FakeMarketStream()
    streams._stream_market = stream
    streams.subscribes["last_price"] = {"UID1"}

    streams.unsubscribe_to_instrument_last_price("UID1", "UID2")
    streams.unsubscribe_to_instrument_last_price("UID1", "UID2")

    assert streams.subscribes["last_price"] == set()
    assert stream.last_price.unsubscribed == [["UID1", "UID2"], ["UID1", "UID2"]]


def test_sandbox_recreate_portfolio_stream_is_noop():
    streams = TinkoffStreamManager(sandbox=True)

    asyncio.run(streams.recreate_portfolio_stream(["ACC1"]))

    assert streams.portfolio_stream_task is None
