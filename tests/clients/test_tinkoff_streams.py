import asyncio

from clients.tinkoff.streams import TinkoffStreamManager
from domain.stream_events import LastPriceEvent
from tests.test_market_data_handler.factories import last_price, md_response_with_last_price


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


class FakeBus:
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


def test_market_response_is_published_as_domain_event():
    bus = FakeBus()
    streams = TinkoffStreamManager(stream_bus=bus)
    response = md_response_with_last_price(last_price("UID1", 100.0))

    asyncio.run(streams._publish_market_response(response))

    assert len(bus.published) == 1
    topic, event = bus.published[0]
    assert topic == "market_data_stream"
    assert isinstance(event, LastPriceEvent)
    assert event.instrument_id == "UID1"
