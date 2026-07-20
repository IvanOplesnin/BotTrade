from __future__ import annotations

from config import Config


def _minimal_config(**overrides):
    data = {
        "tinkoff-client": {"token": "token"},
        "tg-bot": {"token": "token", "chat_id": 1},
        "db-pgsql": {"address": "postgresql+asyncpg://postgres:postgres@db:5432/db"},
        "scheduler-trading": {
            "start": "09:00",
            "close": "23:50",
            "check_expiration_date": "10:00",
        },
        "redis": {
            "host": "redis",
            "port": 6379,
            "db": 0,
            "password": None,
            "ssl": False,
            "decode_responses": True,
            "socket_timeout": 5,
            "retry_on_timeout": True,
        },
        "name-cache": {"ttl": 86400, "namespace": "names"},
    }
    data.update(overrides)
    return data


def test_telegram_storage_defaults_to_redis():
    config = Config(**_minimal_config())

    assert config.telegram_storage.backend == "redis"
    assert config.telegram_storage.key_prefix == "bottrade:tg:fsm"
    assert config.telegram_storage.state_ttl is None
    assert config.telegram_storage.data_ttl is None


def test_telegram_storage_can_be_configured_as_memory():
    config = Config(**_minimal_config(
        **{
            "telegram-storage": {
                "backend": "memory",
                "key-prefix": "bottrade:test:fsm",
                "state-ttl": 60,
                "data-ttl": 120,
            }
        }
    ))

    assert config.telegram_storage.backend == "memory"
    assert config.telegram_storage.key_prefix == "bottrade:test:fsm"
    assert config.telegram_storage.state_ttl == 60
    assert config.telegram_storage.data_ttl == 120


def test_runtime_defaults_to_monolith_telegram_consumers():
    config = Config(**_minimal_config())

    assert config.runtime.telegram_manage_streams is True
    assert config.runtime.telegram_consumers == [
        "market_data",
        "portfolio",
        "strategy_signals",
    ]


def test_runtime_telegram_consumers_can_disable_market_data():
    config = Config(**_minimal_config(
        **{
            "runtime": {
                "telegram-manage-streams": False,
                "telegram-consumers": [
                    "portfolio",
                    "strategy_signals",
                ],
            }
        }
    ))

    assert config.runtime.telegram_manage_streams is False
    assert config.runtime.telegram_consumers == [
        "portfolio",
        "strategy_signals",
    ]


def test_strategies_default_to_donchian_breakout_for_watchlist():
    config = Config(**_minimal_config())

    assert len(config.strategies.default_for_watchlist) == 1
    strategy = config.strategies.default_for_watchlist[0]
    assert strategy.code == "donchian_breakout"
    assert strategy.version == 1
    assert strategy.enabled is True
    assert strategy.mode == "notify"
    assert strategy.params == {
        "entry_period": 55,
        "exit_period": 20,
        "atr_period": 14,
        "timeframe": "day",
    }


def test_strategies_can_be_configured():
    config = Config(**_minimal_config(
        **{
            "strategies": {
                "default-for-watchlist": [
                    {
                        "code": "ma_cross",
                        "version": 2,
                        "enabled": True,
                        "mode": "sandbox_order",
                        "params": {
                            "fast": 20,
                            "slow": 50,
                            "timeframe": "hour",
                        },
                    }
                ]
            }
        }
    ))

    strategy = config.strategies.default_for_watchlist[0]
    assert strategy.code == "ma_cross"
    assert strategy.version == 2
    assert strategy.mode == "sandbox_order"
    assert strategy.params == {
        "fast": 20,
        "slow": 50,
        "timeframe": "hour",
    }
