from __future__ import annotations

from config import Config
from core.domains.event_bus import StreamBus
from core.domains.redis_stream_bus import RedisStreamBus
from database.redis.client import RedisClient
from runtime.context import (
    build_app_context,
    build_stream_bus,
    load_config_dict,
    watchlist_strategy_configs,
)


def _config_data(**overrides):
    data = {
        "tinkoff-client": {"token": "token", "sandbox-token": "sandbox", "sandbox": True},
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


def test_load_config_dict_reads_yaml(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
tinkoff-client:
  token: token
tg-bot:
  token: token
  chat_id: 1
db-pgsql:
  address: postgresql+asyncpg://postgres:postgres@db:5432/db
scheduler-trading:
  start: "09:00"
  close: "23:50"
  check_expiration_date: "10:00"
redis:
  host: redis
  port: 6379
  db: 0
  password:
  ssl: false
  decode_responses: true
  socket_timeout: 5
  retry_on_timeout: true
name-cache:
  ttl: 86400
  namespace: names
""",
        encoding="utf-8",
    )

    config_dict = load_config_dict(str(config_path))

    assert config_dict["tinkoff-client"]["token"] == "token"
    assert config_dict["tg-bot"]["chat_id"] == 1


def test_build_stream_bus_uses_memory_backend():
    config = Config(**_config_data(**{"message-bus": {"backend": "memory"}}))
    redis = RedisClient(config.redis)

    assert isinstance(build_stream_bus(config, redis), StreamBus)


def test_build_stream_bus_uses_redis_backend_by_default():
    config = Config(**_config_data())
    redis = RedisClient(config.redis)

    assert isinstance(build_stream_bus(config, redis), RedisStreamBus)


def test_build_stream_bus_can_override_consumer_name():
    config = Config(**_config_data(**{
        "message-bus": {
            "backend": "redis",
            "consumer": "telegram-test",
        },
    }))
    redis = RedisClient(config.redis)

    bus = build_stream_bus(config, redis, consumer_name="market-worker-test")

    assert isinstance(bus, RedisStreamBus)
    assert bus._consumer_name == "market-worker-test"


def test_watchlist_strategy_configs_are_read_from_config():
    config = Config(**_config_data(**{
        "strategies": {
            "default-for-watchlist": [
                {
                    "code": "donchian_breakout",
                    "version": 2,
                    "enabled": False,
                    "mode": "sandbox_order",
                    "params": {"timeframe": "hour", "entry_period": 20},
                },
            ],
        },
    }))

    result = watchlist_strategy_configs(config)

    assert len(result) == 1
    strategy = result[0]
    assert strategy.code == "donchian_breakout"
    assert strategy.version == 2
    assert strategy.enabled is False
    assert strategy.mode == "sandbox_order"
    assert strategy.params == {"timeframe": "hour", "entry_period": 20}


def test_build_app_context_wires_core_dependencies(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
tinkoff-client:
  token: token
  sandbox-token: sandbox
  sandbox: true
tg-bot:
  token: token
  chat_id: 1
db-pgsql:
  address: postgresql+asyncpg://postgres:postgres@db:5432/db
scheduler-trading:
  start: "09:00"
  close: "23:50"
  check_expiration_date: "10:00"
redis:
  host: redis
  port: 6379
  db: 0
  password:
  ssl: false
  decode_responses: true
  socket_timeout: 5
  retry_on_timeout: true
name-cache:
  ttl: 86400
  namespace: names
message-bus:
  backend: memory
telegram-storage:
  backend: memory
""",
        encoding="utf-8",
    )

    context = build_app_context(str(config_path))

    assert context.config.tinkoff_client.sandbox is True
    assert context.db_repo is context.watchlist_svc._db
    assert context.tclient is context.watchlist_svc._market_data_client
    assert context.strategy_state_svc is context.watchlist_svc._strategy_state_svc
    assert context.market_subscription_svc._tclient is context.tclient
    assert context.market_subscription_svc._db is context.db_repo
    assert context.market_subscription_refresh_publisher._bus is context.stream_bus
    assert context.tclient is context.portfolio_sync_svc._market_data_client
    assert isinstance(context.stream_bus, StreamBus)
