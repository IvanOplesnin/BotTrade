from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from application.candles import candle_rows_from_response


def test_candle_rows_from_response_maps_prices_and_filters_missing_time():
    candle_time = datetime(2026, 7, 20, tzinfo=timezone.utc)
    response = SimpleNamespace(
        candles=[
            SimpleNamespace(
                time=candle_time,
                open=SimpleNamespace(units=1, nano=500_000_000),
                high=Decimal("2.5"),
                low=2,
                close=3.25,
                volume=100,
                is_complete=True,
            ),
            SimpleNamespace(
                time=None,
                open=1,
                high=1,
                low=1,
                close=1,
                volume=1,
                is_complete=True,
            ),
        ]
    )

    rows = candle_rows_from_response(
        instrument_id="UID1",
        timeframe="day",
        candles_response=response,
    )

    assert rows == [
        {
            "instrument_id": "UID1",
            "timeframe": "day",
            "time": candle_time,
            "open": Decimal("1.5"),
            "high": Decimal("2.5"),
            "low": Decimal("2"),
            "close": Decimal("3.25"),
            "volume": 100,
            "is_complete": True,
        }
    ]
