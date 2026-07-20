from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.domains.event_codec import (
    CANDLE_EVENT,
    EVENT_TYPE_FIELD,
    EVENT_VERSION,
    LAST_PRICE_EVENT,
    PAYLOAD_FIELD,
    VERSION_FIELD,
    decode_event,
    encode_event,
)
from domain.stream_events import (
    CandleEvent,
    LastPriceEvent,
    PortfolioPositionEvent,
    PortfolioSnapshotEvent,
)


def test_event_codec_encodes_json_envelope():
    event = LastPriceEvent(
        instrument_id="UID1",
        price=Decimal("123.45"),
        time=datetime(2026, 7, 17, 12, 30, tzinfo=timezone.utc),
    )

    fields = encode_event(event)

    assert fields[EVENT_TYPE_FIELD] == LAST_PRICE_EVENT
    assert fields[VERSION_FIELD] == EVENT_VERSION
    assert json.loads(fields[PAYLOAD_FIELD]) == {
        "instrument_id": "UID1",
        "price": "123.45",
        "time": "2026-07-17T12:30:00+00:00",
    }


def test_event_codec_roundtrips_last_price_event():
    event = LastPriceEvent(
        instrument_id="UID1",
        price=Decimal("123.45"),
        time=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )

    decoded = decode_event(encode_event(event))

    assert decoded == event


def test_event_codec_roundtrips_candle_event():
    event = CandleEvent(
        instrument_id="UID1",
        interval="day",
        open=Decimal("10.1"),
        high=Decimal("11.2"),
        low=Decimal("9.9"),
        close=Decimal("10.7"),
        time=datetime(2026, 7, 17, tzinfo=timezone.utc),
        volume=1200,
        is_complete=True,
    )

    fields = encode_event(event)
    decoded = decode_event(fields)

    assert fields[EVENT_TYPE_FIELD] == CANDLE_EVENT
    assert decoded == event


def test_event_codec_roundtrips_portfolio_snapshot_event():
    event = PortfolioSnapshotEvent(
        account_id="ACC1",
        positions=(
            PortfolioPositionEvent("UID1", "SBER", 2),
            PortfolioPositionEvent("UID2", "AFLT", -1),
        ),
    )

    decoded = decode_event(encode_event(event))

    assert decoded == event


def test_event_codec_decodes_bytes_fields():
    event = LastPriceEvent(
        instrument_id="UID1",
        price=Decimal("123.45"),
        time=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )
    fields = {
        key.encode("utf-8"): value.encode("utf-8")
        for key, value in encode_event(event).items()
    }

    decoded = decode_event(fields)

    assert decoded == event


def test_event_codec_rejects_unknown_version():
    fields = encode_event(
        LastPriceEvent(
            instrument_id="UID1",
            price=Decimal("123.45"),
            time=datetime(2026, 7, 17, tzinfo=timezone.utc),
        )
    )
    fields[VERSION_FIELD] = "2"

    with pytest.raises(ValueError, match="Unsupported event version"):
        decode_event(fields)
