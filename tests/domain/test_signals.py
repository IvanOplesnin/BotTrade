from types import SimpleNamespace

from domain.signals import SignalKind, decide_market_signal


def _indicators(
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


def test_no_signal_when_instrument_is_disabled():
    signal = decide_market_signal(
        _indicators(check=False, to_notify=True, long55=100),
        position_direction=None,
        last_price=110,
    )

    assert signal is None


def test_no_signal_when_instrument_already_notified():
    signal = decide_market_signal(
        _indicators(check=True, to_notify=False, long55=100),
        position_direction=None,
        last_price=110,
    )

    assert signal is None


def test_stop_long_uses_short_20_boundary():
    signal = decide_market_signal(
        _indicators(short20=99),
        position_direction="long",
        last_price=98.5,
    )

    assert signal.kind == SignalKind.STOP_LONG
    assert signal.boundary == 99


def test_stop_short_uses_long_20_boundary():
    signal = decide_market_signal(
        _indicators(long20=105),
        position_direction="short",
        last_price=106,
    )

    assert signal.kind == SignalKind.STOP_SHORT
    assert signal.boundary == 105


def test_breakout_long_without_position():
    signal = decide_market_signal(
        _indicators(long55=120, short55=90),
        position_direction=None,
        last_price=121,
    )

    assert signal.kind == SignalKind.BREAKOUT_LONG
    assert signal.side == "long"
    assert signal.boundary == 120


def test_breakout_short_without_position_does_not_require_long_boundary():
    signal = decide_market_signal(
        _indicators(short55=90),
        position_direction=None,
        last_price=89,
    )

    assert signal.kind == SignalKind.BREAKOUT_SHORT
    assert signal.side == "short"
    assert signal.boundary == 90


def test_no_signal_inside_channel():
    signal = decide_market_signal(
        _indicators(long55=120, short55=90),
        position_direction=None,
        last_price=100,
    )

    assert signal is None
