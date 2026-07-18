from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("SSL_TBANK_VERIFY", "true")

try:
    import t_tech.invest as ti
    from t_tech.invest import AioRequestError
    from t_tech.invest.async_services import AsyncServices
    from t_tech.invest.market_data_stream.async_market_data_stream_manager import (
        AsyncMarketDataStreamManager,
    )
    from t_tech.invest.schemas import (
        Account,
        FavoriteInstrument,
        FutureResponse,
        GetCandlesResponse,
        GetFavoriteGroupsRequest,
        GetFuturesMarginResponse,
        InstrumentIdType,
        LastPrice,
        MoneyValue,
        OpenSandboxAccountResponse,
        OrderDirection,
        OrderType,
        PortfolioPosition,
        PortfolioResponse,
        PostOrderResponse,
        Quotation,
        SandboxPayInResponse,
    )
    from t_tech.invest.utils import money_to_decimal as m2d
    from t_tech.invest.utils import quotation_to_decimal as q2d
except ModuleNotFoundError as exc:
    if exc.name != "t_tech":
        raise

    import tinkoff.invest as ti
    from tinkoff.invest import AioRequestError
    from tinkoff.invest.async_services import AsyncServices
    from tinkoff.invest.market_data_stream.async_market_data_stream_manager import (
        AsyncMarketDataStreamManager,
    )
    from tinkoff.invest.schemas import (
        Account,
        FavoriteInstrument,
        FutureResponse,
        GetCandlesResponse,
        GetFavoriteGroupsRequest,
        GetFuturesMarginResponse,
        InstrumentIdType,
        LastPrice,
        MoneyValue,
        OpenSandboxAccountResponse,
        OrderDirection,
        OrderType,
        PortfolioPosition,
        PortfolioResponse,
        PostOrderResponse,
        Quotation,
        SandboxPayInResponse,
    )
    from tinkoff.invest.utils import money_to_decimal as m2d
    from tinkoff.invest.utils import quotation_to_decimal as q2d


def sdk_text(obj: Any, *field_names: str, default: str = "") -> str:
    for field_name in field_names:
        value = getattr(obj, field_name, None)
        if isinstance(value, str) and value:
            return value
    return default


def sdk_instrument_uid(obj: Any, *, default: str = "") -> str:
    return sdk_text(obj, "instrument_uid", "uid", "instrument_id", "figi", default=default)


def sdk_instrument_ticker(obj: Any, *, default: str = "") -> str:
    return sdk_text(obj, "ticker", default=default)


def sdk_instrument_name(obj: Any, *, default: str = "") -> str:
    return sdk_text(obj, "name", "ticker", "uid", "instrument_uid", "figi", default=default)


__all__ = [
    "Account",
    "AioRequestError",
    "AsyncMarketDataStreamManager",
    "AsyncServices",
    "FavoriteInstrument",
    "FutureResponse",
    "GetCandlesResponse",
    "GetFavoriteGroupsRequest",
    "GetFuturesMarginResponse",
    "InstrumentIdType",
    "LastPrice",
    "MoneyValue",
    "OpenSandboxAccountResponse",
    "OrderDirection",
    "OrderType",
    "PortfolioPosition",
    "PortfolioResponse",
    "PostOrderResponse",
    "Quotation",
    "SandboxPayInResponse",
    "m2d",
    "q2d",
    "sdk_instrument_name",
    "sdk_instrument_ticker",
    "sdk_instrument_uid",
    "sdk_text",
    "ti",
]
