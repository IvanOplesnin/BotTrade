from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


class Config(BaseModel):
    class TinkoffClient(BaseModel):
        token: str = Field(...)
        sandbox_token: Optional[str] = Field(None, alias="sandbox-token")
        sandbox: bool = False
        app_name: Optional[str] = Field(None, alias="app-name")

        model_config = ConfigDict(populate_by_name=True, extra='forbid')

    class TgBot(BaseModel):
        token: str = Field(...)
        chat_id: int = Field(...)
        proxy: Optional[str] = None

    class DbPsql(BaseModel):
        address: str = Field(...)

    class SchedulerTrading(BaseModel):
        start: str = Field(...)
        close: str = Field(...)
        check_expiration_date: str = Field(...)

    class Redis(BaseModel):
        host: str = Field(...)
        port: int = Field(...)
        db: int = Field(...)
        password: Optional[str]
        ssl: bool = Field(...)
        decode_responses: bool = Field(...)
        socket_timeout: int = Field(...)
        retry_on_timeout: bool = Field(...)

    class NameCache(BaseModel):
        ttl: int = Field(...)
        namespace: str = Field(...)

    class MessageBus(BaseModel):
        backend: Literal["redis", "memory"] = "redis"
        stream_prefix: str = Field("bottrade:bus", alias="stream-prefix")
        group: str = "bottrade"
        consumer: Optional[str] = None
        start_id: str = Field("$", alias="start-id")
        batch_size: int = Field(10, alias="batch-size")
        block_ms: int = Field(1000, alias="block-ms")
        maxlen: int = 10000

        model_config = ConfigDict(populate_by_name=True, extra='forbid')

    tinkoff_client: TinkoffClient = Field(..., alias="tinkoff-client")
    tg_bot: TgBot = Field(..., alias="tg-bot")
    db_pgsql: DbPsql = Field(..., alias="db-pgsql")
    scheduler_trading: SchedulerTrading = Field(..., alias="scheduler-trading")
    redis: Redis = Field(..., alias="redis")
    name_cache: NameCache = Field(..., alias="name-cache")
    message_bus: MessageBus = Field(default_factory=MessageBus, alias="message-bus")

    logging: Optional[dict] = None

    model_config = ConfigDict(populate_by_name=True, extra='forbid')
