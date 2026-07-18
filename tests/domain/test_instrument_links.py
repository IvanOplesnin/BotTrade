from domain.instrument_links import tbank_instrument_link


def test_tbank_instrument_link_maps_sdk_types_to_tbank_sections():
    assert tbank_instrument_link("SBER", "share") == "https://www.tbank.ru/invest/stocks/SBER/"
    assert tbank_instrument_link("TMOS@", "etf") == "https://www.tbank.ru/invest/etfs/TMOS/"
    assert (
        tbank_instrument_link("RUB000UTSTOM", "currency")
        == "https://www.tbank.ru/invest/currencies/RUB000UTSTOM/"
    )
    assert tbank_instrument_link("SiZ6", "future") == "https://www.tbank.ru/invest/futures/SiZ6/"


def test_tbank_instrument_link_returns_empty_when_metadata_is_missing():
    assert tbank_instrument_link("", "share") == ""
    assert tbank_instrument_link("SBER", None) == ""
