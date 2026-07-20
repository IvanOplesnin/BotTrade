from types import SimpleNamespace

import pytest

from domain.strategies import (
    DonchianBreakoutParams,
    DonchianBreakoutStrategy,
    SignalKind,
    StrategyContext,
)


def _instrument(
        *,
        check=True,
        to_notify=True,
        long55=None,
        short55=None,
        long20=None,
        short20=None,
):
    return SimpleNamespace(
        check=check,
        to_notify=to_notify,
        donchian_long_55=long55,
        donchian_short_55=short55,
        donchian_long_20=long20,
        donchian_short_20=short20,
    )


def test_donchian_strategy_declares_market_data_requirements():
    requirements = DonchianBreakoutStrategy().requirements()

    assert requirements.last_price is True
    assert requirements.trades is False
    assert requirements.candles[0].timeframe == "day"
    assert requirements.candles[0].warmup == 69


def test_donchian_strategy_accepts_custom_params_for_requirements():
    requirements = DonchianBreakoutStrategy().requirements(
        DonchianBreakoutParams(
            entry_period=20,
            exit_period=10,
            atr_period=5,
            timeframe="hour",
        )
    )

    assert requirements.candles[0].timeframe == "hour"
    assert requirements.candles[0].warmup == 25


@pytest.mark.parametrize(
    ("position_direction", "last_price", "expected_kind", "expected_side"),
    [
        ("long", 94, SignalKind.STOP_LONG, None),
        ("short", 106, SignalKind.STOP_SHORT, None),
        (None, 121, SignalKind.BREAKOUT_LONG, "long"),
        (None, 89, SignalKind.BREAKOUT_SHORT, "short"),
    ],
)
def test_donchian_strategy_returns_signal_metadata(
        position_direction,
        last_price,
        expected_kind,
        expected_side,
):
    signal = DonchianBreakoutStrategy().decide(
        StrategyContext(
            instrument=_instrument(
                long55=120,
                short55=90,
                long20=105,
                short20=95,
            ),
            position_direction=position_direction,
            last_price=last_price,
        )
    )

    assert signal.kind == expected_kind
    assert signal.side == expected_side
    assert signal.strategy_code == "donchian_breakout"
    assert signal.strategy_version == 1
    assert signal.payload == {
        "entry_period": 55,
        "exit_period": 20,
        "atr_period": 14,
        "timeframe": "day",
    }


def test_donchian_strategy_returns_no_signal_inside_channel():
    signal = DonchianBreakoutStrategy().decide(
        StrategyContext(
            instrument=_instrument(long55=120, short55=90),
            position_direction=None,
            last_price=100,
        )
    )

    assert signal is None

