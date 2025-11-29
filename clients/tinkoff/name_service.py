from typing import Optional

from clients.tinkoff.client import TClient
from config import Config
from database.redis.client import RedisClient
from utils.logger import get_logger


class NameService:
    """
        Резолвит имя инструмента по UID в порядке:
        Redis -> Tinkoff API, с записью обратно в Redis.
        """

    def __init__(self, redis_client: RedisClient, tclient: TClient, cfg: Config.NameCache):
        self.redis_client = redis_client
        self.tclient = tclient
        self.cfg = cfg
        self.log = get_logger(self.__class__.__name__)

    async def get_name(self, instrument_uid: str) -> Optional[str]:
        try:
            name = await self.redis_client.get_name(instrument_uid, self.cfg.namespace)
            if name:
                self.log.debug("Got name from cache", extra={"instrument_name": name})
                return name
        except Exception as e:
            self.log.error("Error while GETTING name from cache", extra={"exception": e})

        name = await self.tclient.get_name_by_id(instrument_uid)
        try:
            await self.redis_client.set_name(instrument_uid, name, self.cfg.ttl, self.cfg.namespace)
            self.log.debug("Got name from Tinkoff API and put Redis", extra={"instrument_name": name})
        except Exception as e:
            self.log.error("Error while SETTING name to cache", extra={"exception": e})
        return name
