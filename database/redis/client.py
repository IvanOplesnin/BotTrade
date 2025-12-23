import json
from typing import Optional, Any

from config import Config
from redis.asyncio import Redis

from database.redis.scripts_lua import LUA_SET_IF_NEWER
from utils.logger import get_logger


class RedisClient:
    """
    Обёртка над redis.asyncio.Redis с JSON-хелперами и неймспейсом.
    """

    def __init__(self, cfg: Config.Redis, namespace: str = "bottrade"):
        self._cfg = cfg
        self._ns = namespace.rstrip(":")
        self._redis: Optional[Redis] = None
        self.log = get_logger(self.__class__.__name__)

    async def connect(self):
        if self._redis is None:
            self._redis = Redis(
                host=self._cfg.host,
                port=self._cfg.port,
                db=self._cfg.db,
                password=self._cfg.password,
                ssl=self._cfg.ssl,
                decode_responses=self._cfg.decode_responses,
                socket_timeout=self._cfg.socket_timeout,
                retry_on_timeout=self._cfg.retry_on_timeout
            )
            pong = await self._redis.ping()
            self.log.info("Redis connected", extra={"pong": pong})

    async def close(self):
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    def _k(self, *parts: str) -> str:
        return ":".join([self._ns, *[p.strip(":") for p in parts]])

    async def set_json(self, key: str, value: Any, ttl_sec: Optional[int] = None) -> None:
        assert self._redis is not None, "Call connect() first"
        s = json.dumps(value, ensure_ascii=False)
        if ttl_sec and ttl_sec > 0:
            await self._redis.set(key, s, ex=ttl_sec)
        else:
            await self._redis.set(key, s)

    async def get_json(self, key: str) -> Optional[Any]:
        assert self._redis is not None, "Call connect() first"
        s = await self._redis.get(key)
        if s is None:
            return None
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None

    async def delete(self, key: str) -> int:
        assert self._redis is not None, "Call connect() first"
        return await self._redis.delete(key)

    # ---- специализация под имена инструментов ----
    def name_key(self, instrument_uid: str, namespace: str = "names") -> str:
        return self._k(namespace, instrument_uid)

    async def set_name(self, instrument_uid: str, name: str, ttl_sec: int,
                       namespace: str = "names") -> None:
        await self.set_json(self.name_key(instrument_uid, namespace),
                            {"name": name}, ttl_sec)

    async def get_name(self, instrument_uid: str, namespace: str = "names") -> Optional[str]:
        val = await self.get_json(self.name_key(instrument_uid, namespace))
        return (val or {}).get("name")

    # ---- специализация под последние цены ----
    def last_price_key(self, instrument_uid: str) -> str:
        return self._k("md", "last_price", instrument_uid)

    async def set_last_price_if_newer(self, instrument_uid: str, price_str: str, ts_ms: int) -> Optional[bool]:
        if self._redis is None:
            self.log.error("Call redis.connect() first", extra={"instrument_id": instrument_uid})
            return None
        key = self.last_price_key(instrument_uid)
        res = await self._redis.eval(
            LUA_SET_IF_NEWER,
            1,  # numkeys
            key,  # KEYS[1]
            price_str,  # ARGV[1]
            str(ts_ms)  # ARGV[2]
        )
        self.log.debug(
            "set_last_price_if_newer",
            extra={"instrument_uid": instrument_uid, "last_price": price_str, "ts_ms": ts_ms, "updated": bool(res)}
        )
        return bool(res)

    async def get_last_price(self, instrument_uid: str) -> Optional[dict]:
        if self._redis is None:
            self.log.error("Call redis.connect() first", extra={"instrument_id": instrument_uid})
            return None
        key = self.last_price_key(instrument_uid)
        data = await self._redis.hgetall(key)
        self.log.debug("get_last_price", extra={"instrument_uid": instrument_uid, "data": data})
        return data or None
