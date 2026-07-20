from dataclasses import dataclass

from domain.strategies import (
    CandleRequirement,
    MarketDataRequirements,
    SkippedStrategyBinding,
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
    assert plan.skipped_bindings == ()


def test_subscription_plan_normalizes_candle_timeframes_before_merge():
    registry = StrategyRegistry([
        FakeStrategy(
            code="sdk_timeframe",
            version=1,
            requirements_result=MarketDataRequirements(
                candles=(
                    CandleRequirement(
                        timeframe="CandleInterval.CANDLE_INTERVAL_DAY",
                        warmup=70,
                    ),
                ),
            ),
        ),
        FakeStrategy(
            code="internal_timeframe",
            version=1,
            requirements_result=MarketDataRequirements(
                candles=(CandleRequirement(timeframe="day", warmup=120),),
            ),
        ),
    ])

    plan = build_subscription_plan(
        [
            StrategyBindingSubscription("UID1", "sdk_timeframe"),
            StrategyBindingSubscription("UID1", "internal_timeframe"),
        ],
        registry,
    )

    assert [
        (subscription.instrument_id, subscription.timeframe, subscription.warmup)
        for subscription in plan.candle_subscriptions
    ] == [("UID1", "day", 120)]


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
    assert plan.skipped_bindings == ()


def test_subscription_plan_skips_unknown_strategy_with_diagnostic():
    registry = StrategyRegistry.with_defaults()

    plan = build_subscription_plan(
        [
            StrategyBindingSubscription("UID1", "unknown_strategy"),
            StrategyBindingSubscription("UID2", "donchian_breakout"),
        ],
        registry,
    )

    assert plan.last_price_instrument_ids == ("UID2",)
    assert plan.skipped_bindings == (
        SkippedStrategyBinding(
            instrument_id="UID1",
            strategy_code="unknown_strategy",
            strategy_version=1,
            reason="unknown_strategy",
        ),
    )


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
