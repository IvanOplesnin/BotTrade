from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from domain.stream_events import (
    CandleEvent,
    LastPriceEvent,
    LastPriceSubscriptionEvent,
    PortfolioPositionEvent,
    PortfolioSnapshotEvent,
    StreamEvent,
    TradeEvent,
)

EVENT_TYPE_FIELD = "event_type"
VERSION_FIELD = "version"
PAYLOAD_FIELD = "payload"
EVENT_VERSION = "1"

LAST_PRICE_EVENT = "market.last_price"
LAST_PRICE_SUBSCRIPTION_EVENT = "market.last_price_subscription"
CANDLE_EVENT = "market.candle"
TRADE_EVENT = "market.trade"
PORTFOLIO_SNAPSHOT_EVENT = "portfolio.snapshot"


def encode_event(event: StreamEvent) -> dict[str, str]:
    event_type, payload = _event_to_payload(event)
    return {
        EVENT_TYPE_FIELD: event_type,
        VERSION_FIELD: EVENT_VERSION,
        PAYLOAD_FIELD: json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }


def decode_event(fields: Mapping[Any, Any]) -> StreamEvent:
    event_type = _field(fields, EVENT_TYPE_FIELD)
    version = _field(fields, VERSION_FIELD)
    payload_raw = _field(fields, PAYLOAD_FIELD)

    if version != EVENT_VERSION:
        raise ValueError(f"Unsupported event version: {version}")

    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Redis stream event payload is not valid JSON") from exc

    return _payload_to_event(event_type, payload)


def _event_to_payload(event: StreamEvent) -> tuple[str, dict[str, Any]]:
    if isinstance(event, LastPriceEvent):
        return LAST_PRICE_EVENT, {
            "instrument_id": event.instrument_id,
            "price": str(event.price),
            "time": event.time.isoformat(),
        }
    if isinstance(event, LastPriceSubscriptionEvent):
        return LAST_PRICE_SUBSCRIPTION_EVENT, {
            "instrument_ids": list(event.instrument_ids),
        }
    if isinstance(event, CandleEvent):
        return CANDLE_EVENT, {
            "instrument_id": event.instrument_id,
            "interval": event.interval,
            "open": str(event.open),
            "high": str(event.high),
            "low": str(event.low),
            "close": str(event.close),
        }
    if isinstance(event, TradeEvent):
        return TRADE_EVENT, {
            "instrument_id": event.instrument_id,
            "price": str(event.price),
            "quantity": event.quantity,
        }
    if isinstance(event, PortfolioSnapshotEvent):
        return PORTFOLIO_SNAPSHOT_EVENT, {
            "account_id": event.account_id,
            "positions": [
                {
                    "instrument_id": position.instrument_id,
                    "ticker": position.ticker,
                    "quantity_lots": position.quantity_lots,
                }
                for position in event.positions
            ],
        }

    raise TypeError(f"Unsupported stream event: {event.__class__.__name__}")


def _payload_to_event(event_type: str, payload: dict[str, Any]) -> StreamEvent:
    if event_type == LAST_PRICE_EVENT:
        return LastPriceEvent(
            instrument_id=str(payload["instrument_id"]),
            price=Decimal(str(payload["price"])),
            time=datetime.fromisoformat(str(payload["time"])),
        )
    if event_type == LAST_PRICE_SUBSCRIPTION_EVENT:
        return LastPriceSubscriptionEvent(
            instrument_ids=tuple(str(item) for item in payload["instrument_ids"]),
        )
    if event_type == CANDLE_EVENT:
        return CandleEvent(
            instrument_id=str(payload["instrument_id"]),
            interval=str(payload["interval"]),
            open=Decimal(str(payload["open"])),
            high=Decimal(str(payload["high"])),
            low=Decimal(str(payload["low"])),
            close=Decimal(str(payload["close"])),
        )
    if event_type == TRADE_EVENT:
        return TradeEvent(
            instrument_id=str(payload["instrument_id"]),
            price=Decimal(str(payload["price"])),
            quantity=int(payload["quantity"]),
        )
    if event_type == PORTFOLIO_SNAPSHOT_EVENT:
        return PortfolioSnapshotEvent(
            account_id=str(payload["account_id"]),
            positions=tuple(
                PortfolioPositionEvent(
                    instrument_id=str(position["instrument_id"]),
                    ticker=str(position["ticker"]),
                    quantity_lots=int(position["quantity_lots"]),
                )
                for position in payload["positions"]
            ),
        )

    raise ValueError(f"Unsupported event type: {event_type}")


def _field(fields: Mapping[Any, Any], name: str) -> str:
    value = fields.get(name)
    if value is None:
        value = fields.get(name.encode("utf-8"))
    if value is None:
        raise ValueError(f"Redis stream message has no {name} field")
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
