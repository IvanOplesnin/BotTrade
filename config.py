from typing import Optional
import yaml

from pydantic import BaseModel, BaseConfig, Field, ConfigDict


class Config(BaseModel):
    class TinkoffClient(BaseModel):
        token: str = Field(...)

    class TgBot(BaseModel):
        token: str = Field(...)

    class DbPsql(BaseModel):
        address: str = Field(...)

    tinkoff_client: TinkoffClient = Field(..., alias="tinkoff-client")
    tg_bot: TgBot = Field(..., alias="tg-bot")
    db_pgsql: DbPsql = Field(..., alias="db-pgsql")

    model_config = ConfigDict(populate_by_name=True, extra='forbid')
