from typing import Optional
import yaml

from pydantic import BaseModel, BaseConfig, Field, ConfigDict


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
        before_time: str = Field(...)

    tinkoff_client: TinkoffClient = Field(..., alias="tinkoff-client")
    tg_bot: TgBot = Field(..., alias="tg-bot")
    db_pgsql: DbPsql = Field(..., alias="db-pgsql")
    scheduler_trading: SchedulerTrading = Field(..., alias="scheduler-trading")

    model_config = ConfigDict(populate_by_name=True, extra='forbid')
