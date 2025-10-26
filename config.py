from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class Config(BaseModel):
    class TinkoffClient(BaseModel):
        token: str = Field(...)

    class TgBot(BaseModel):
        token: str = Field(...)
        chat_id: int = Field(...)

    class DbPsql(BaseModel):
        address: str = Field(...)

    class SchedulerTrading(BaseModel):
        start: str = Field(...)
        close: str = Field(...)

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

    tinkoff_client: TinkoffClient = Field(..., alias="tinkoff-client")
    tg_bot: TgBot = Field(..., alias="tg-bot")
    db_pgsql: DbPsql = Field(..., alias="db-pgsql")
    scheduler_trading: SchedulerTrading = Field(..., alias="scheduler-trading")
    redis: Redis = Field(..., alias="redis")
    name_cache: NameCache = Field(..., alias="name-cache")

    model_config = ConfigDict(populate_by_name=True, extra='forbid')
