from datetime import datetime, timezone
from importlib import import_module

from clients.tinkoff.sdk import (
    sdk_instrument_name,
    sdk_instrument_ticker,
    sdk_instrument_uid,
    ti,
)
from tests.test_market_data_handler.factories import quotation


def _sdk_schema_class(name: str):
    schemas = import_module(f"{ti.__name__}.schemas")
    return getattr(schemas, name)


def test_sdk_classes_expose_fields_used_by_service():
    fields_by_class = {
        ti.Account: {"id", "name"},
        ti.FavoriteInstrument: {"uid", "figi", "ticker", "name"},
        ti.GetFavoritesResponse: {"favorite_instruments", "group_id"},
        _sdk_schema_class("FavoriteGroup"): {"group_id", "group_name", "size"},
        _sdk_schema_class("GetFavoriteGroupsResponse"): {"groups"},
        ti.PortfolioResponse: {"account_id", "positions", "expected_yield"},
        ti.PortfolioPosition: {"figi", "instrument_uid", "ticker", "quantity_lots"},
        ti.Instrument: {"uid", "figi", "ticker", "name", "min_price_increment"},
        ti.Future: {
            "uid",
            "figi",
            "ticker",
            "name",
            "expiration_date",
            "min_price_increment",
            "min_price_increment_amount",
        },
        ti.GetFuturesMarginResponse: {
            "min_price_increment",
            "min_price_increment_amount",
        },
        ti.LastPrice: {"figi", "instrument_uid", "price", "time"},
        ti.Candle: {"figi", "instrument_uid", "ticker", "open", "high", "low", "close"},
        ti.Trade: {"figi", "instrument_uid", "price", "quantity"},
        ti.LastPriceInstrument: {"figi", "instrument_id"},
        ti.LastPriceSubscription: {"figi", "instrument_uid"},
    }

    for sdk_class, expected_fields in fields_by_class.items():
        assert expected_fields <= set(sdk_class.__annotations__)


def test_favorite_instrument_fields_used_by_bot_are_available():
    instrument = ti.FavoriteInstrument(
        uid="uid-1",
        figi="figi-1",
        ticker="TICK",
        name="Instrument Name",
    )

    assert sdk_instrument_uid(instrument) == "uid-1"
    assert sdk_instrument_ticker(instrument) == "TICK"
    assert sdk_instrument_name(instrument) == "Instrument Name"


def test_favorite_instrument_name_falls_back_to_ticker_when_unset():
    instrument = ti.FavoriteInstrument(uid="uid-1", ticker="TICK")

    assert sdk_instrument_name(instrument) == "TICK"


def test_portfolio_position_has_no_name_but_has_uid_and_ticker():
    position = ti.PortfolioPosition(
        figi="figi-1",
        instrument_uid="uid-1",
        ticker="TICK",
        quantity_lots=quotation(1, 0),
    )

    assert sdk_instrument_uid(position) == "uid-1"
    assert sdk_instrument_ticker(position) == "TICK"
    assert sdk_instrument_name(position) == "TICK"


def test_last_price_prefers_uid_and_falls_back_to_figi():
    by_uid = ti.LastPrice(
        instrument_uid="uid-1",
        figi="figi-1",
        price=quotation(100, 0),
        time=datetime.now(timezone.utc),
    )
    by_figi = ti.LastPrice(
        figi="figi-1",
        price=quotation(100, 0),
        time=datetime.now(timezone.utc),
    )

    assert sdk_instrument_uid(by_uid) == "uid-1"
    assert sdk_instrument_uid(by_figi) == "figi-1"
