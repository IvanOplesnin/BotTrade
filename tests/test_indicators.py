from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from clients.tinkoff.sdk import ti
from services.historic_service.indicators import IndicatorCalculator


def _quotation(value: float) -> ti.Quotation:
    units = int(value)
    nano = int(round((value - units) * 1_000_000_000))
    return ti.Quotation(units=units, nano=nano)


def test_indicator_calculator_returns_float_values():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        SimpleNamespace(
            is_complete=True,
            time=start + timedelta(days=day),
            high=_quotation(100 + day + 0.5),
            low=_quotation(90 + day + 0.25),
            close=_quotation(95 + day + 0.75),
        )
        for day in range(60)
    ]

    indicators = IndicatorCalculator(SimpleNamespace(candles=candles)).build_instrument_update()

    for value in indicators.values():
        assert isinstance(value, float)
