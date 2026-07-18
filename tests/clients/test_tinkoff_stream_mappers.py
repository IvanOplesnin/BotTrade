from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from clients.tinkoff.stream_mappers import (
    market_data_response_to_event,
    portfolio_stream_response_to_event,
)
from domain.stream_events import LastPriceEvent, PortfolioSnapshotEvent
from tests.test_market_data_handler.factories import last_price, md_response_with_last_price


def test_market_data_response_to_event_maps_last_price_to_domain_event():
    response = md_response_with_last_price(last_price("UID1", 123.45))

    event = market_data_response_to_event(response)

    assert isinstance(event, LastPriceEvent)
    assert event.instrument_id == "UID1"
    assert event.price == Decimal("123.45")


def test_portfolio_stream_response_to_event_maps_positions_to_domain_snapshot():
    response = SimpleNamespace(
        portfolio=SimpleNamespace(
            account_id="ACC1",
            positions=[
                SimpleNamespace(
                    instrument_uid="UID1",
                    ticker="SBER",
                    quantity_lots=SimpleNamespace(units=2),
                ),
                SimpleNamespace(
                    figi="FIGI2",
                    ticker="AFLT",
                    quantity_lots=SimpleNamespace(units=-1),
                ),
                SimpleNamespace(
                    instrument_uid="",
                    ticker="EMPTY",
                    quantity_lots=SimpleNamespace(units=1),
                ),
            ],
        )
    )

    event = portfolio_stream_response_to_event(response)

    assert isinstance(event, PortfolioSnapshotEvent)
    assert event.account_id == "ACC1"
    assert [
        (position.instrument_id, position.ticker, position.quantity_lots)
        for position in event.positions
    ] == [
        ("UID1", "SBER", 2),
        ("FIGI2", "AFLT", -1),
    ]


def test_portfolio_stream_response_to_event_skips_non_portfolio_messages():
    event = portfolio_stream_response_to_event(SimpleNamespace(portfolio=None))

    assert event is None
