from __future__ import annotations

from collections.abc import Iterable

from domain.strategies.donchian import DonchianBreakoutStrategy
from domain.strategies.models import Strategy


class StrategyRegistry:
    def __init__(self, strategies: Iterable[Strategy]):
        self._strategies = {
            (strategy.code, strategy.version): strategy
            for strategy in strategies
        }

    @classmethod
    def with_defaults(cls) -> "StrategyRegistry":
        return cls([DonchianBreakoutStrategy()])

    def get(self, code: str, version: int = 1) -> Strategy:
        try:
            return self._strategies[(code, version)]
        except KeyError as exc:
            raise KeyError(f"Unknown strategy: {code}@{version}") from exc

