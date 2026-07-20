from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from application.dto import StrategyBindingConfig


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
