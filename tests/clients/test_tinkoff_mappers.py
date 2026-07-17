from types import SimpleNamespace

from clients.tinkoff.mappers import (
    flatten_favorite_groups,
    instruments_to_candidates,
    is_cash_like_position,
    portfolio_positions_to_candidates,
)


def test_portfolio_positions_to_candidates_uses_uid_ticker_and_direction():
    positions = [
        SimpleNamespace(
            instrument_uid="UID1",
            ticker="AAA",
            quantity_lots=SimpleNamespace(units=1),
        ),
        SimpleNamespace(
            instrument_uid="UID2",
            ticker="BBB",
            quantity_lots=SimpleNamespace(units=-1),
        ),
    ]

    result = portfolio_positions_to_candidates(positions)

    assert [(item.instrument_id, item.ticker, item.direction) for item in result] == [
        ("UID1", "AAA", "long"),
        ("UID2", "BBB", "short"),
    ]


def test_portfolio_positions_to_candidates_skips_cash_like_positions():
    positions = [
        SimpleNamespace(
            instrument_uid="RUB_UID",
            ticker="RUB000UTSTOM",
            instrument_type="currency",
            quantity_lots=SimpleNamespace(units=1000),
        ),
        SimpleNamespace(
            instrument_uid="TMON_UID",
            ticker="TMON@",
            instrument_type="etf",
            quantity_lots=SimpleNamespace(units=10),
        ),
        SimpleNamespace(
            instrument_uid="SBER_UID",
            ticker="SBER",
            instrument_type="share",
            quantity_lots=SimpleNamespace(units=1),
        ),
    ]

    result = portfolio_positions_to_candidates(positions)

    assert [(item.instrument_id, item.ticker, item.direction) for item in result] == [
        ("SBER_UID", "SBER", "long"),
    ]


def test_is_cash_like_position_detects_currency_and_money_market_ticker():
    assert is_cash_like_position(
        SimpleNamespace(ticker="RUB000UTSTOM", instrument_type="currency")
    )
    assert is_cash_like_position(
        SimpleNamespace(ticker="TMON@", instrument_type="etf")
    )
    assert not is_cash_like_position(
        SimpleNamespace(ticker="TRUR@", instrument_type="etf")
    )


def test_instruments_to_candidates_skips_items_without_uid():
    instruments = [
        SimpleNamespace(uid="UID1", ticker="AAA", instrument_type="share"),
        SimpleNamespace(uid="", ticker="EMPTY"),
    ]

    result = instruments_to_candidates(instruments)

    assert [(item.instrument_id, item.ticker, item.instrument_type) for item in result] == [
        ("UID1", "AAA", "share")
    ]


def test_flatten_favorite_groups_returns_group_instruments_in_order():
    groups = [
        SimpleNamespace(favorite_instruments=["A", "B"]),
        SimpleNamespace(favorite_instruments=["C"]),
    ]

    assert flatten_favorite_groups(groups) == ["A", "B", "C"]
