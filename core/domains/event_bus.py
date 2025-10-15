from __future__ import annotations
import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable, Dict, List, Any

Handler = Callable[[Any], Awaitable[None]]

class StreamBus:
    def __init__(self, maxsize: int = 10000):
        self.q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subs: Dict[str, List[Handler]] = defaultdict(list)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.log = logging.getLogger(self.__class__.__name__)

    def subscribe(self, topic: str, handler: Handler) -> None:
        """topic — строка/тип, например 'last_price', 'candle:1m', 'orderbook'."""
        self._subs[topic].append(handler)

    async def publish(self, topic: str, data: Any) -> None:
        try:
            self.log.debug(f"publish {topic} {data}")
            await self.q.put((topic, data))
        except asyncio.CancelledError:
            raise

    async def _loop(self) -> None:
        self.log.debug("_loop_start, %s", not self._stop.is_set())
        while not self._stop.is_set():
            topic, data = await self.q.get()
            self.log.debug(f"get {topic} {data}")
            try:
                for h in self._subs.get(topic, []):
                    self.log.debug(f"Go handler {topic} {data} {h.__name__}")
                    # параллельно, но без потери исключений
                    await h(data)
            except Exception as e:
                self.log.error(f"{e}", exc_info=True)
            finally:
                self.q.task_done()

    async def start(self):
        if not self._task:
            self._stop.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task:
            self._stop.set()
            await self.q.put(("_stop", None))
            await self._task
            self._task = None


def handler(bus: StreamBus, topic: str):
    def decorator(func: Handler):
        bus.subscribe(topic, func)
        return func
    return decorator