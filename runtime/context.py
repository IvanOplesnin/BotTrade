from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from application.dto import StrategyBindingConfig
from application.market_candles import MarketCandleService
from application.market_data_refresh import MarketDataRefreshService
from application.portfolio_sync import PortfolioSyncService
from application.strategy_state import StrategyStateService
from application.strategy_subscriptions import StrategySubscriptionService
from application.watchlist import WatchlistService
from clients.tinkoff.client import TClient
from clients.tinkoff.name_service import NameService
from clients.tinkoff.portfolio_svc import PortfolioService
from config import Config
from core.domains.event_bus import StreamBus
from core.domains.message_bus import MessageBus
from core.domains.redis_stream_bus import RedisStreamBus
from database.pgsql.repository import Repository
from database.redis.client import RedisClient
from services.scheduler.scheduler import TZ_DEFAULT


@dataclass(frozen=True)
class AppContext:
    config: Config
    config_dict: dict[str, Any]
    db_repo: Repository
    redis: RedisClient
    stream_bus: MessageBus
    tclient: TClient
    name_service: NameService
    portfolio_svc: PortfolioService
    strategy_state_svc: StrategyStateService
    market_candle_svc: MarketCandleService
    strategy_subscription_svc: StrategySubscriptionService
    watchlist_svc: WatchlistService
    portfolio_sync_svc: PortfolioSyncService
    market_data_refresh_svc: MarketDataRefreshService


def load_config_dict(path: str = "config.yaml") -> dict[str, Any]:
    if not path:
        path = "config.yaml"

    with open(path, "r", encoding="utf-8") as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_config(path: str = "config.yaml") -> tuple[Config, dict[str, Any]]:
    config_dict = load_config_dict(path)
    return Config(**config_dict), config_dict


def build_stream_bus(config: Config, redis: RedisClient) -> MessageBus:
    bus_cfg = config.message_bus
    if bus_cfg.backend == "memory":
        return StreamBus()

    return RedisStreamBus(
        redis,
        stream_prefix=bus_cfg.stream_prefix,
        group_name=bus_cfg.group,
        consumer_name=bus_cfg.consumer,
        start_id=bus_cfg.start_id,
        batch_size=bus_cfg.batch_size,
        block_ms=bus_cfg.block_ms,
        maxlen=bus_cfg.maxlen,
    )


def watchlist_strategy_configs(config: Config) -> list[StrategyBindingConfig]:
    return [
        StrategyBindingConfig(
            code=strategy.code,
            version=strategy.version,
            enabled=strategy.enabled,
            mode=strategy.mode,
            params=dict(strategy.params),
        )
        for strategy in config.strategies.default_for_watchlist
    ]


def build_app_context(config_path: str = "config.yaml") -> AppContext:
    config, config_dict = load_config(config_path)
    db_repo = Repository(config.db_pgsql.address)
    redis = RedisClient(config.redis)
    stream_bus = build_stream_bus(config, redis)
    tclient = TClient(
        token=config.tinkoff_client.token,
        sandbox_token=config.tinkoff_client.sandbox_token,
        sandbox=config.tinkoff_client.sandbox,
        app_name=config.tinkoff_client.app_name,
        stream_bus=stream_bus,
    )
    name_service = NameService(redis, tclient, config.name_cache)
    portfolio_svc = PortfolioService(tclient, redis)
    strategy_state_svc = StrategyStateService(db_repo)
    market_candle_svc = MarketCandleService(db_repo, strategy_state_svc)
    strategy_subscription_svc = StrategySubscriptionService(db_repo)
    default_strategy_configs = watchlist_strategy_configs(config)
    watchlist_svc = WatchlistService(
        db_repo,
        tclient,
        default_strategy_configs=default_strategy_configs,
        strategy_state_svc=strategy_state_svc,
    )
    portfolio_sync_svc = PortfolioSyncService(
        db_repo,
        tclient,
        default_strategy_configs=default_strategy_configs,
        strategy_state_svc=strategy_state_svc,
    )
    market_data_refresh_svc = MarketDataRefreshService(
        db_repo,
        tclient,
        strategy_state_svc,
        tz=TZ_DEFAULT,
    )

    return AppContext(
        config=config,
        config_dict=config_dict,
        db_repo=db_repo,
        redis=redis,
        stream_bus=stream_bus,
        tclient=tclient,
        name_service=name_service,
        portfolio_svc=portfolio_svc,
        strategy_state_svc=strategy_state_svc,
        market_candle_svc=market_candle_svc,
        strategy_subscription_svc=strategy_subscription_svc,
        watchlist_svc=watchlist_svc,
        portfolio_sync_svc=portfolio_sync_svc,
        market_data_refresh_svc=market_data_refresh_svc,
    )
