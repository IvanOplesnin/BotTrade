from __future__ import annotations

from application.dto import ActiveStrategyBinding
from application.ports import StrategySubscriptionRepository
from domain.strategies import (
    MarketSubscriptionPlan,
    StrategyBindingSubscription,
    StrategyRegistry,
    build_subscription_plan,
)


class StrategySubscriptionService:
    """Application use case for deriving market data subscriptions from active strategies."""

    def __init__(
            self,
            db: StrategySubscriptionRepository,
            *,
            strategy_registry: StrategyRegistry | None = None,
    ):
        self._db = db
        self._strategy_registry = strategy_registry or StrategyRegistry.with_defaults()

    async def build_plan(self) -> MarketSubscriptionPlan:
        async with self._db.session_factory() as session:
            bindings = await self._db.list_active_strategy_bindings(session=session)

        return build_subscription_plan(
            [_subscription_from_binding(binding) for binding in bindings],
            self._strategy_registry,
        )


def _subscription_from_binding(binding: ActiveStrategyBinding) -> StrategyBindingSubscription:
    return StrategyBindingSubscription(
        instrument_id=binding.instrument_id,
        strategy_code=binding.strategy_code,
        strategy_version=binding.version,
        params=dict(binding.params),
        enabled=True,
    )
