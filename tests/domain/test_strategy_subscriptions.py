from dataclasses import dataclass

from domain.strategies import (
    CandleRequirement,
    MarketDataRequirements,
    StrategyBindingSubscription,
    StrategyRegistry,
    build_subscription_plan,
)


@dataclass(frozen=True)
class FakeStrategy:
    code: str
    version: int
    requirements_result: MarketDataRequirements

    def requirements(self, params=None):
        return self.requirements_result

    def decide(self, context, params=None):
        return None


def test_subscription_plan_merges_strategy_requirements_by_instrument():
    registry = StrategyRegistry([
        FakeStrategy(
            code="daily_breakout",
            version=1,
            requirements_result=MarketDataRequirements(
                candles=(CandleRequirement(timeframe="day", warmup=70),),
                last_price=True,
            ),
        ),
        FakeStrategy(
            code="daily_mean_reversion",
            version=1,
            requirements_result=MarketDataRequirements(
                candles=(CandleRequirement(timeframe="day", warmup=120),),
                last_price=True,
            ),
        ),
    ])

    plan = build_subscription_plan(
        [
            StrategyBindingSubscription("UID1", "daily_breakout"),
            StrategyBindingSubscription("UID1", "daily_mean_reversion"),
        ],
        registry,
    )

    assert plan.last_price_instrument_ids == ("UID1",)
    assert plan.candle_subscriptions[0].instrument_id == "UID1"
    assert plan.candle_subscriptions[0].timeframe == "day"
    assert plan.candle_subscriptions[0].warmup == 120
    assert plan.trade_instrument_ids == ()


def test_subscription_plan_skips_disabled_bindings():
    registry = StrategyRegistry.with_defaults()

    plan = build_subscription_plan(
        [
            StrategyBindingSubscription(
                "UID1",
                "donchian_breakout",
                enabled=False,
            )
        ],
        registry,
    )

    assert plan.last_price_instrument_ids == ()
    assert plan.candle_subscriptions == ()
    assert plan.trade_instrument_ids == ()


def test_default_strategy_registry_contains_donchian_breakout():
    plan = build_subscription_plan(
        [
            StrategyBindingSubscription(
                "UID2",
                "donchian_breakout",
                params={"entry_period": 20, "exit_period": 10, "atr_period": 5},
            )
        ],
        StrategyRegistry.with_defaults(),
    )

    assert plan.last_price_instrument_ids == ("UID2",)
    assert plan.candle_subscriptions[0].warmup == 25

