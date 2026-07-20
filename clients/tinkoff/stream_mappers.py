from __future__ import annotations

from typing import Optional

from clients.tinkoff.sdk import q2d, sdk_instrument_ticker, sdk_instrument_uid, ti
from domain.stream_events import (
    CandleEvent,
    LastPriceEvent,
    LastPriceSubscriptionEvent,
    MarketDataEvent,
    PortfolioPositionEvent,
    PortfolioSnapshotEvent,
    TradeEvent,
)


def market_data_response_to_event(resp: ti.MarketDataResponse) -> Optional[MarketDataEvent]:
    if last_price := getattr(resp, "last_price", None):
        return _last_price_to_event(last_price)
    if subscription := getattr(resp, "subscribe_last_price_response", None):
        return _last_price_subscription_to_event(subscription)
    if candle := getattr(resp, "candle", None):
        return _candle_to_event(candle)
    if trade := getattr(resp, "trade", None):
        return _trade_to_event(trade)
    return None


def portfolio_stream_response_to_event(
        resp: ti.PortfolioStreamResponse,
) -> Optional[PortfolioSnapshotEvent]:
    portfolio = getattr(resp, "portfolio", None)
    if portfolio is None:
        return None

    positions = []
    for position in getattr(portfolio, "positions", ()):
        uid = sdk_instrument_uid(position)
        if not uid:
            continue
        quantity_lots = getattr(position, "quantity_lots", None)
        positions.append(
            PortfolioPositionEvent(
                instrument_id=uid,
                ticker=sdk_instrument_ticker(position, default=uid),
                quantity_lots=int(getattr(quantity_lots, "units", 0)),
            )
        )
    return PortfolioSnapshotEvent(
        account_id=portfolio.account_id,
        positions=tuple(positions),
    )


def _last_price_to_event(last_price: ti.LastPrice) -> LastPriceEvent:
    return LastPriceEvent(
        instrument_id=sdk_instrument_uid(last_price),
        price=q2d(last_price.price),
        time=last_price.time,
    )


def _last_price_subscription_to_event(
        response: ti.SubscribeLastPriceResponse,
) -> LastPriceSubscriptionEvent:
    instrument_ids = tuple(
        uid
        for subscription in response.last_price_subscriptions
        if (uid := sdk_instrument_uid(subscription))
    )
    return LastPriceSubscriptionEvent(instrument_ids=instrument_ids)


def _candle_to_event(candle: ti.Candle) -> CandleEvent:
    volume = getattr(candle, "volume", None)
    return CandleEvent(
        instrument_id=sdk_instrument_uid(candle),
        interval=str(candle.interval),
        open=q2d(candle.open),
        high=q2d(candle.high),
        low=q2d(candle.low),
        close=q2d(candle.close),
        time=getattr(candle, "time", None),
        volume=int(volume) if volume is not None else None,
        is_complete=bool(getattr(candle, "is_complete", True)),
    )


def _trade_to_event(trade: ti.Trade) -> TradeEvent:
    return TradeEvent(
        instrument_id=sdk_instrument_uid(trade),
        price=q2d(trade.price),
        quantity=trade.quantity,
    )
