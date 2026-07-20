from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

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
        last_price = context.last_price

        if not getattr(context.instrument, "check", False) or not getattr(context.instrument, "to_notify", False):
            return None

        if context.position_direction == "long":
            boundary = _number(_indicator(context, "donchian_short", strategy_params.exit_period))
            if boundary is not None and last_price <= boundary:
                return self._signal(SignalKind.STOP_LONG, boundary, strategy_params)
            return None

        if context.position_direction == "short":
            boundary = _number(_indicator(context, "donchian_long", strategy_params.exit_period))
            if boundary is not None and last_price >= boundary:
                return self._signal(SignalKind.STOP_SHORT, boundary, strategy_params)
            return None

        long_boundary = _number(_indicator(context, "donchian_long", strategy_params.entry_period))
        if long_boundary is not None and last_price >= long_boundary:
            return self._signal(
                SignalKind.BREAKOUT_LONG,
                long_boundary,
                strategy_params,
                side="long",
            )

        short_boundary = _number(_indicator(context, "donchian_short", strategy_params.entry_period))
        if short_boundary is not None and last_price <= short_boundary:
            return self._signal(
                SignalKind.BREAKOUT_SHORT,
                short_boundary,
                strategy_params,
                side="short",
            )

        return None

    def calculate_state(
            self,
            candles: Sequence[Any],
            params: Any = None,
    ) -> Mapping[str, Any]:
        strategy_params = self._params(params)
        completed = sorted(
            (candle for candle in candles if getattr(candle, "is_complete", True)),
            key=lambda candle: candle.time,
        )
        highs = [_price(getattr(candle, "high")) for candle in completed]
        lows = [_price(getattr(candle, "low")) for candle in completed]
        closes = [_price(getattr(candle, "close")) for candle in completed]

        return {
            f"donchian_long_{strategy_params.entry_period}": _last_window_max(
                highs,
                strategy_params.entry_period - 1,
            ),
            f"donchian_short_{strategy_params.entry_period}": _last_window_min(
                lows,
                strategy_params.entry_period - 1,
            ),
            f"donchian_long_{strategy_params.exit_period}": _last_window_max(
                highs,
                strategy_params.exit_period - 1,
            ),
            f"donchian_short_{strategy_params.exit_period}": _last_window_min(
                lows,
                strategy_params.exit_period - 1,
            ),
            f"atr{strategy_params.atr_period}": _atr(highs, lows, closes, strategy_params.atr_period),
            "timeframe": strategy_params.timeframe,
            "candles_count": len(completed),
        }

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


def _indicator(context: StrategyContext, name: str, period: int) -> Any:
    key = f"{name}_{period}"
    if context.state.get(key) is not None:
        return context.state[key]
    return getattr(context.instrument, key, None)


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _price(value: Any) -> float:
    units = getattr(value, "units", None)
    nano = getattr(value, "nano", None)
    if units is not None and nano is not None:
        return float(units) + float(nano) / 1_000_000_000.0
    return float(value)


def _last_window_max(values: list[float], window: int) -> Optional[float]:
    if window <= 0 or len(values) < window:
        return None
    return max(values[-window:])


def _last_window_min(values: list[float], window: int) -> Optional[float]:
    if window <= 0 or len(values) < window:
        return None
    return min(values[-window:])


def _atr(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int,
) -> Optional[float]:
    if len(closes) < period + 1:
        return None

    true_ranges = []
    for index in range(1, len(closes)):
        high = highs[index]
        low = lows[index]
        previous_close = closes[index - 1]
        true_ranges.append(
            max(high - low, abs(high - previous_close), abs(low - previous_close))
        )

    atr = sum(true_ranges[:period]) / period
    for true_range in true_ranges[period:]:
        atr = (atr * (period - 1) + true_range) / period
    return atr
