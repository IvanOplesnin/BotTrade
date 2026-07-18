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

