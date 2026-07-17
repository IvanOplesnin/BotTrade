from types import SimpleNamespace

from clients.tinkoff.mappers import (
    flatten_favorite_groups,
    instruments_to_candidates,
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


def test_instruments_to_candidates_skips_items_without_uid():
    instruments = [
        SimpleNamespace(uid="UID1", ticker="AAA"),
        SimpleNamespace(uid="", ticker="EMPTY"),
    ]

    result = instruments_to_candidates(instruments)

    assert [(item.instrument_id, item.ticker) for item in result] == [("UID1", "AAA")]


def test_flatten_favorite_groups_returns_group_instruments_in_order():
    groups = [
        SimpleNamespace(favorite_instruments=["A", "B"]),
        SimpleNamespace(favorite_instruments=["C"]),
    ]

    assert flatten_favorite_groups(groups) == ["A", "B", "C"]
