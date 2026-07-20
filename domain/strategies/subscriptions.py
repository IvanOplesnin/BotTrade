from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from domain.strategies.registry import StrategyRegistry


@dataclass(frozen=True)
class StrategyBindingSubscription:
    instrument_id: str
    strategy_code: str
    strategy_version: int = 1
    params: Mapping[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True)
class CandleSubscription:
    instrument_id: str
    timeframe: str
    warmup: int


@dataclass(frozen=True)
class MarketSubscriptionPlan:
    last_price_instrument_ids: tuple[str, ...] = ()
    candle_subscriptions: tuple[CandleSubscription, ...] = ()
    trade_instrument_ids: tuple[str, ...] = ()


def build_subscription_plan(
        bindings: list[StrategyBindingSubscription],
        registry: StrategyRegistry,
) -> MarketSubscriptionPlan:
    last_price_ids: set[str] = set()
    trade_ids: set[str] = set()
    candles: dict[tuple[str, str], int] = {}

    for binding in bindings:
        if not binding.enabled:
            continue

        strategy = registry.get(binding.strategy_code, binding.strategy_version)
        requirements = strategy.requirements(binding.params)

        if requirements.last_price:
            last_price_ids.add(binding.instrument_id)
        if requirements.trades:
            trade_ids.add(binding.instrument_id)
        for candle in requirements.candles:
            key = (binding.instrument_id, candle.timeframe)
            candles[key] = max(candles.get(key, 0), candle.warmup)

    return MarketSubscriptionPlan(
        last_price_instrument_ids=tuple(sorted(last_price_ids)),
        candle_subscriptions=tuple(
            CandleSubscription(
                instrument_id=instrument_id,
                timeframe=timeframe,
                warmup=warmup,
            )
            for (instrument_id, timeframe), warmup in sorted(candles.items())
        ),
        trade_instrument_ids=tuple(sorted(trade_ids)),
    )

