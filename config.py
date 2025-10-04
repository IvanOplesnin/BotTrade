from typing import Optional
import yaml

from pydantic import BaseModel, BaseConfig, Field, ConfigDict


class Config(BaseModel):
    class TinkoffClient(BaseModel):
        token: str = Field(...)
        account_id: Optional[str] = None

    class TgBot(BaseModel):
        token: str = Field(...)

    tinkoff_client: TinkoffClient = Field(..., alias="tinkoff-client")
    tg_bot: TgBot = Field(..., alias="tg-bot")

    model_config = ConfigDict(populate_by_name=True, extra='forbid')


with open('config.yaml', 'r', encoding='utf-8') as f:
    config_dict = yaml.load(f, Loader=yaml.FullLoader)

config: Config = Config(**config_dict)
