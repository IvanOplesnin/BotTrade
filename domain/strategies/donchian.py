from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from domain.strategies.models import (
    CandleRequirement,
    MarketDataRequirements,
    MarketSignal,
    SignalKind,
    StrategyContext,
)


@dataclass(frozen=True)
class DonchianBreakoutParams:
    entry_period: int = 55
    exit_period: int = 20
    atr_period: int = 14
    timeframe: str = "day"
    warmup: Optional[int] = None

    @property
    def warmup_candles(self) -> int:
        if self.warmup is not None:
            return self.warmup
        return max(self.entry_period, self.exit_period, self.atr_period) + self.atr_period


class DonchianBreakoutStrategy:
    code = "donchian_breakout"
    version = 1

    def requirements(self, params: Any = None) -> MarketDataRequirements:
        strategy_params = self._params(params)
        return MarketDataRequirements(
            candles=(
                CandleRequirement(
                    timeframe=strategy_params.timeframe,
                    warmup=strategy_params.warmup_candles,
                ),
            ),
            last_price=True,
        )

    def decide(
            self,
            context: StrategyContext,
            params: Any = None,
    ) -> Optional[MarketSignal]:
        strategy_params = self._params(params)
        indicators = context.instrument
        last_price = context.last_price

        if not getattr(indicators, "check", False) or not getattr(indicators, "to_notify", False):
            return None

        if context.position_direction == "long":
            boundary = _number(_indicator(indicators, "donchian_short", strategy_params.exit_period))
            if boundary is not None and last_price <= boundary:
                return self._signal(SignalKind.STOP_LONG, boundary, strategy_params)
            return None

        if context.position_direction == "short":
            boundary = _number(_indicator(indicators, "donchian_long", strategy_params.exit_period))
            if boundary is not None and last_price >= boundary:
                return self._signal(SignalKind.STOP_SHORT, boundary, strategy_params)
            return None

        long_boundary = _number(_indicator(indicators, "donchian_long", strategy_params.entry_period))
        if long_boundary is not None and last_price >= long_boundary:
            return self._signal(
                SignalKind.BREAKOUT_LONG,
                long_boundary,
                strategy_params,
                side="long",
            )

        short_boundary = _number(_indicator(indicators, "donchian_short", strategy_params.entry_period))
        if short_boundary is not None and last_price <= short_boundary:
            return self._signal(
                SignalKind.BREAKOUT_SHORT,
                short_boundary,
                strategy_params,
                side="short",
            )

        return None

    def _signal(
            self,
            kind: SignalKind,
            boundary: float,
            params: DonchianBreakoutParams,
            *,
            side: Optional[str] = None,
    ) -> MarketSignal:
        return MarketSignal(
            kind=kind,
            boundary=boundary,
            side=side,
            strategy_code=self.code,
            strategy_version=self.version,
            payload={
                "entry_period": params.entry_period,
                "exit_period": params.exit_period,
                "atr_period": params.atr_period,
                "timeframe": params.timeframe,
            },
        )

    @staticmethod
    def _params(params: Any) -> DonchianBreakoutParams:
        if params is None:
            return DonchianBreakoutParams()
        if isinstance(params, DonchianBreakoutParams):
            return params
        if isinstance(params, Mapping):
            return DonchianBreakoutParams(**dict(params))
        raise TypeError(f"Unsupported Donchian params: {params.__class__.__name__}")


def _indicator(indicators: Any, name: str, period: int) -> Any:
    return getattr(indicators, f"{name}_{period}", None)


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)

