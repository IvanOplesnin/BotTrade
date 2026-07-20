from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from application.dto import StrategyBindingConfig
from domain.strategies import (
    StrategyBindingSubscription,
    StrategyRegistry,
    build_subscription_plan,
)
from domain.timeframes import normalize_timeframe


def default_watchlist_strategy_configs() -> list[StrategyBindingConfig]:
    return [
        StrategyBindingConfig(
            code="donchian_breakout",
            params={
                "entry_period": 55,
                "exit_period": 20,
                "atr_period": 14,
                "timeframe": "day",
            },
        )
    ]


def strategy_binding_payloads(
        instrument_ids: Sequence[str],
        strategy_configs: Sequence[StrategyBindingConfig],
        *,
        account_id: Optional[str],
) -> list[dict[str, Any]]:
    return [
        {
            "strategy_code": strategy.code,
            "version": strategy.version,
            "instrument_id": instrument_id,
            "account_id": account_id,
            "enabled": strategy.enabled,
            "mode": strategy.mode,
            "params": dict(strategy.params),
        }
        for instrument_id in instrument_ids
        for strategy in strategy_configs
    ]


def candle_warmup_for_timeframe(
        strategy_configs: Sequence[StrategyBindingConfig],
        timeframe: str,
        *,
        registry: StrategyRegistry | None = None,
) -> Optional[int]:
    registry = registry or StrategyRegistry.with_defaults()
    target_timeframe = normalize_timeframe(timeframe)
    plan = build_subscription_plan(
        [
            StrategyBindingSubscription(
                instrument_id="__instrument__",
                strategy_code=strategy.code,
                strategy_version=strategy.version,
                params=dict(strategy.params),
                enabled=strategy.enabled,
            )
            for strategy in strategy_configs
        ],
        registry,
    )
    warmups = [
        subscription.warmup
        for subscription in plan.candle_subscriptions
        if normalize_timeframe(subscription.timeframe) == target_timeframe
    ]
    if not warmups:
        return None
    return max(warmups)
